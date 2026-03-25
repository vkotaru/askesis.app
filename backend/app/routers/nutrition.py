import io
import uuid
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date, datetime
from PIL import Image, ImageOps

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from app.config import get_settings
from app.database import get_db
from app.models import (
    User,
    Meal,
    MealTemplate,
    UserSettings,
    DailyNutrition,
    FoodItem,
    MealFoodItem,
)
from app.routers.auth import get_current_user, check_view_permission
from app.encryption import get_refresh_token
from app import google_drive

router = APIRouter()

# Temp directory for Gemini analysis (photos are stored in Google Drive)
TEMP_DIR = Path(__file__).parent.parent.parent / "uploads" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def require_drive_access(user: User):
    """Ensure user has Google Drive access configured."""
    if not user.google_refresh_token:
        raise HTTPException(
            status_code=403,
            detail="Google Drive access not configured. Please log out and log in again to grant Drive permissions.",
        )


class MealFoodItemCreate(BaseModel):
    food_item_id: int
    quantity: float = Field(1.0, gt=0, le=100)
    notes: str | None = None


class MealFoodItemResponse(BaseModel):
    id: int
    food_item_id: int
    food_item_name: str
    serving_size: float
    serving_unit: str
    quantity: float
    calories: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


class MealCreate(BaseModel):
    date: date
    label: str = Field(..., min_length=1, max_length=50)
    time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")  # HH:MM format
    calories: int | None = Field(None, ge=0, le=10000)
    description: str | None = Field(None, max_length=2000)
    food_items: list[MealFoodItemCreate] = Field(default_factory=list)


class MealResponse(BaseModel):
    id: int
    user_id: int
    date: date
    label: str
    time: str | None = None
    calories: int | None = None
    description: str | None = None
    photo_path: str | None = None
    drive_file_id: str | None = None
    ai_analysis: str | None = None
    photo_url: str | None = None
    food_items: list[MealFoodItemResponse] = []
    computed_calories: int | None = None
    computed_protein_g: float | None = None
    computed_carbs_g: float | None = None
    computed_fat_g: float | None = None

    class Config:
        from_attributes = True


# Food Item schemas
class FoodItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    brand: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=100)
    serving_size: float = Field(1.0, gt=0)
    serving_unit: str = Field("g", max_length=20)
    calories: int | None = Field(None, ge=0, le=10000)
    protein_g: float | None = Field(None, ge=0)
    carbs_g: float | None = Field(None, ge=0)
    fat_g: float | None = Field(None, ge=0)
    fiber_g: float | None = Field(None, ge=0)
    is_shared: bool = True


class FoodItemResponse(FoodItemCreate):
    id: int
    user_id: int | None = None
    source: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class FoodAnalysis(BaseModel):
    calories: int | None = None
    description: str | None = None
    foods: list[str] = []
    macros: dict | None = None


def process_meal_image_bytes(
    content: bytes, max_size: int = 800, quality: int = 80
) -> bytes:
    """Process uploaded meal image: resize, optimize, convert to JPEG. Returns bytes."""
    img = Image.open(io.BytesIO(content))

    # Fix rotation based on EXIF
    img = ImageOps.exif_transpose(img)

    # Convert to RGB if needed
    if img.mode in ("RGBA", "P", "CMYK"):
        img = img.convert("RGB")

    # Resize if too large (maintain aspect ratio)
    if img.size[0] > max_size or img.size[1] > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Save as optimized JPEG to bytes
    output = io.BytesIO()
    img.save(output, "JPEG", quality=quality, optimize=True)
    output.seek(0)
    return output.read()


async def analyze_food_with_gemini(image_content: bytes) -> FoodAnalysis | None:
    """Use Gemini to analyze food in image."""
    if not GEMINI_AVAILABLE:
        return None

    import os

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Load image from bytes
        img = Image.open(io.BytesIO(image_content))

        prompt = """Analyze this food image and provide:
1. Estimated total calories
2. A brief description of the food items
3. List of individual food items identified
4. Estimated macros (protein_g, carbs_g, fat_g)

Respond in JSON format:
{
    "calories": <number>,
    "description": "<brief description>",
    "foods": ["item1", "item2", ...],
    "macros": {"protein_g": <number>, "carbs_g": <number>, "fat_g": <number>}
}

Be conservative with calorie estimates. If you can't identify the food clearly, make your best estimate."""

        response = model.generate_content([prompt, img])

        # Parse JSON from response
        text = response.text
        # Extract JSON from markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        data = json.loads(text.strip())
        return FoodAnalysis(**data)

    except Exception as e:
        print(f"Gemini analysis failed: {e}")
        return None


def _compute_meal_nutrition(meal: Meal) -> dict:
    """Compute total nutrition from food items."""
    totals = {"calories": 0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    if not meal.food_items:
        return {k: None for k in totals}
    for mfi in meal.food_items:
        fi = mfi.food_item
        if fi.calories:
            totals["calories"] += round(fi.calories * mfi.quantity)
        if fi.protein_g:
            totals["protein_g"] += round(fi.protein_g * mfi.quantity, 1)
        if fi.carbs_g:
            totals["carbs_g"] += round(fi.carbs_g * mfi.quantity, 1)
        if fi.fat_g:
            totals["fat_g"] += round(fi.fat_g * mfi.quantity, 1)
    return totals


def _food_item_response(mfi: MealFoodItem) -> dict:
    """Convert MealFoodItem to response dict with computed nutrition."""
    fi = mfi.food_item
    return {
        "id": mfi.id,
        "food_item_id": fi.id,
        "food_item_name": fi.name,
        "serving_size": fi.serving_size,
        "serving_unit": fi.serving_unit,
        "quantity": mfi.quantity,
        "calories": round(fi.calories * mfi.quantity) if fi.calories else None,
        "protein_g": round(fi.protein_g * mfi.quantity, 1) if fi.protein_g else None,
        "carbs_g": round(fi.carbs_g * mfi.quantity, 1) if fi.carbs_g else None,
        "fat_g": round(fi.fat_g * mfi.quantity, 1) if fi.fat_g else None,
        "notes": mfi.notes,
    }


def meal_to_response(meal: Meal) -> dict:
    """Convert Meal to response dict with photo URL and food items."""
    has_photo = meal.drive_file_id or meal.photo_path
    computed = _compute_meal_nutrition(meal)
    return {
        "id": meal.id,
        "user_id": meal.user_id,
        "date": meal.date,
        "label": meal.label,
        "time": meal.time,
        "calories": meal.calories,
        "description": meal.description,
        "photo_path": meal.photo_path,
        "drive_file_id": meal.drive_file_id,
        "ai_analysis": meal.ai_analysis,
        "photo_url": f"/api/nutrition/meals/{meal.id}/photo" if has_photo else None,
        "food_items": [_food_item_response(mfi) for mfi in meal.food_items],
        "computed_calories": computed["calories"],
        "computed_protein_g": computed["protein_g"],
        "computed_carbs_g": computed["carbs_g"],
        "computed_fat_g": computed["fat_g"],
    }


class MealTemplateCreate(BaseModel):
    name: str
    label: str
    calories: int | None = None
    description: str | None = None


class MealTemplateResponse(MealTemplateCreate):
    id: int

    class Config:
        from_attributes = True


# Daily Nutrition models
class DailyNutritionCreate(BaseModel):
    date: date
    protein_g: float | None = Field(None, ge=0, le=1000)
    carbs_g: float | None = Field(None, ge=0, le=2000)
    fat_g: float | None = Field(None, ge=0, le=1000)
    notes: str | None = Field(None, max_length=2000)


class DailyNutritionResponse(BaseModel):
    id: int
    user_id: int
    date: date
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


# Daily Nutrition endpoints
@router.get("/daily/{nutrition_date}", response_model=DailyNutritionResponse)
def get_daily_nutrition(
    nutrition_date: date,
    user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get daily nutrition totals for a specific date."""
    target_user = check_view_permission(user_id, "nutrition", db, current_user)
    nutrition = (
        db.query(DailyNutrition)
        .filter(
            DailyNutrition.user_id == target_user.id,
            DailyNutrition.date == nutrition_date,
        )
        .first()
    )

    if not nutrition:
        raise HTTPException(status_code=404, detail="Daily nutrition not found")

    return nutrition


@router.post("/daily", response_model=DailyNutritionResponse)
def save_daily_nutrition(
    data: DailyNutritionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create or update daily nutrition totals."""
    # Check if nutrition exists for this date
    existing = (
        db.query(DailyNutrition)
        .filter(
            DailyNutrition.user_id == current_user.id,
            DailyNutrition.date == data.date,
        )
        .first()
    )

    if existing:
        # Update only provided fields
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key != "date":
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    # Create new
    nutrition = DailyNutrition(user_id=current_user.id, **data.model_dump())
    db.add(nutrition)
    db.commit()
    db.refresh(nutrition)
    return nutrition


@router.get("/daily", response_model=list[DailyNutritionResponse])
def get_daily_nutrition_history(
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get daily nutrition history over a date range."""
    target_user = check_view_permission(user_id, "nutrition", db, current_user)
    query = db.query(DailyNutrition).filter(DailyNutrition.user_id == target_user.id)

    if start_date:
        query = query.filter(DailyNutrition.date >= start_date)
    if end_date:
        query = query.filter(DailyNutrition.date <= end_date)

    return query.order_by(DailyNutrition.date.desc()).limit(limit).all()


@router.get("/meals")
def get_meals(
    meal_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "nutrition", db, current_user)
    query = (
        db.query(Meal)
        .filter(Meal.user_id == target_user.id)
        .filter(Meal.deleted_at.is_(None))
    )

    if meal_date:
        query = query.filter(Meal.date == meal_date)
    else:
        if start_date:
            query = query.filter(Meal.date >= start_date)
        if end_date:
            query = query.filter(Meal.date <= end_date)

    meals = (
        query.order_by(Meal.date.desc(), Meal.time).offset(offset).limit(limit).all()
    )
    return [meal_to_response(m) for m in meals]


@router.post("/meals")
def create_meal(
    meal_data: MealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    food_items_data = meal_data.food_items
    meal_dict = meal_data.model_dump(exclude={"food_items"})

    meal = Meal(user_id=current_user.id, **meal_dict)
    db.add(meal)
    db.flush()

    for fi_data in food_items_data:
        mfi = MealFoodItem(meal_id=meal.id, **fi_data.model_dump())
        db.add(mfi)

    # Auto-compute calories from food items if not manually set
    if food_items_data and not meal.calories:
        db.flush()
        db.refresh(meal)
        computed = _compute_meal_nutrition(meal)
        if computed["calories"]:
            meal.calories = computed["calories"]

    db.commit()
    db.refresh(meal)
    return meal_to_response(meal)


@router.put("/meals/{meal_id}")
def update_meal(
    meal_id: int,
    meal_data: MealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = (
        db.query(Meal)
        .filter(Meal.id == meal_id, Meal.user_id == current_user.id)
        .filter(Meal.deleted_at.is_(None))
        .first()
    )

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    for key, value in meal_data.model_dump(exclude={"food_items"}).items():
        setattr(meal, key, value)

    # Replace food items
    db.query(MealFoodItem).filter(MealFoodItem.meal_id == meal_id).delete()
    for fi_data in meal_data.food_items:
        mfi = MealFoodItem(meal_id=meal.id, **fi_data.model_dump())
        db.add(mfi)

    # Auto-compute calories from food items if not manually set
    if meal_data.food_items and not meal.calories:
        db.flush()
        db.refresh(meal)
        computed = _compute_meal_nutrition(meal)
        if computed["calories"]:
            meal.calories = computed["calories"]

    db.commit()
    db.refresh(meal)
    return meal_to_response(meal)


@router.post("/meals/{meal_id}/photo")
async def upload_meal_photo(
    meal_id: int,
    file: UploadFile = File(...),
    analyze: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a photo for a meal and optionally analyze with Gemini."""
    settings = get_settings()
    require_drive_access(current_user)

    meal = (
        db.query(Meal)
        .filter(Meal.id == meal_id, Meal.user_id == current_user.id)
        .first()
    )

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Validate file type
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Read and validate file size
    content = await file.read()
    if len(content) > settings.max_image_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_image_size // (1024 * 1024)}MB",
        )

    # Process image (resize, optimize, convert to JPEG)
    try:
        processed_content = process_meal_image_bytes(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}")

    # Generate unique filename for Drive
    filename = f"meal_{current_user.id}_{meal_id}_{uuid.uuid4().hex[:8]}.jpg"

    # Get user's Drive folder setting
    user_settings = (
        db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    )
    parent_folder_id = user_settings.drive_parent_folder_id if user_settings else None

    # Upload to Google Drive
    try:
        drive_file_id = google_drive.upload_meal_photo(
            get_refresh_token(current_user),
            processed_content,
            filename,
            parent_folder_id=parent_folder_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to upload to Google Drive: {e}"
        )

    # Delete old photo from Drive if replacing
    if meal.drive_file_id:
        try:
            google_drive.delete_photo(
                get_refresh_token(current_user), meal.drive_file_id
            )
        except Exception:
            pass  # Ignore errors deleting old file

    # Update meal with Drive file ID
    meal.drive_file_id = drive_file_id
    meal.photo_path = None  # Clear legacy path

    # Analyze with Gemini if requested
    analysis = None
    if analyze:
        analysis = await analyze_food_with_gemini(processed_content)
        if analysis:
            meal.ai_analysis = json.dumps(analysis.model_dump())
            # Auto-fill calories and description if not set
            if not meal.calories and analysis.calories:
                meal.calories = analysis.calories
            if not meal.description and analysis.description:
                meal.description = analysis.description

    db.commit()
    db.refresh(meal)

    return {
        **meal_to_response(meal),
        "analysis": analysis.model_dump() if analysis else None,
    }


@router.get("/meals/{meal_id}/photo")
def get_meal_photo(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get photo for a meal."""
    meal = db.query(Meal).filter(Meal.id == meal_id).first()

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    if not meal.drive_file_id and not meal.photo_path:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Check permission - allow owner or shared users
    if meal.user_id != current_user.id:
        check_view_permission(meal.user_id, "nutrition", db, current_user)

    # Get the meal owner for their refresh token
    owner = db.query(User).filter(User.id == meal.user_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Meal owner not found")

    # Download from Google Drive
    if meal.drive_file_id:
        if not owner.google_refresh_token:
            raise HTTPException(
                status_code=500, detail="Meal owner's Drive access expired"
            )

        try:
            content = google_drive.download_photo(
                get_refresh_token(owner), meal.drive_file_id
            )
            return Response(content=content, media_type="image/jpeg")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to download from Google Drive: {e}"
            )

    # Legacy: file stored locally (should not happen for new photos)
    if meal.photo_path:
        file_path = Path(meal.photo_path)
        if file_path.exists():
            return Response(content=file_path.read_bytes(), media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="Photo file not found")


@router.post("/analyze-photo")
async def analyze_food_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Analyze a food photo without creating a meal (preview)."""
    settings = get_settings()

    if not GEMINI_AVAILABLE:
        raise HTTPException(status_code=503, detail="Gemini API not available")

    # Validate file type
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
        "image/webp",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Read and validate file size
    content = await file.read()
    if len(content) > settings.max_image_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.max_image_size // (1024 * 1024)}MB",
        )

    # Process image in memory (no temp files needed)
    try:
        processed_content = process_meal_image_bytes(content)
        analysis = await analyze_food_with_gemini(processed_content)
        return analysis.model_dump() if analysis else {"error": "Analysis failed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}")


@router.delete("/meals/{meal_id}")
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = (
        db.query(Meal)
        .filter(Meal.id == meal_id, Meal.user_id == current_user.id)
        .filter(Meal.deleted_at.is_(None))
        .first()
    )

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    meal.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/meals/copy-yesterday")
def copy_meals_from_yesterday(
    target_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import timedelta

    yesterday = target_date - timedelta(days=1)

    yesterday_meals = (
        db.query(Meal)
        .filter(Meal.user_id == current_user.id, Meal.date == yesterday)
        .filter(Meal.deleted_at.is_(None))
        .all()
    )

    new_meals = []
    for meal in yesterday_meals:
        new_meal = Meal(
            user_id=current_user.id,
            date=target_date,
            label=meal.label,
            time=meal.time,
            calories=meal.calories,
            description=meal.description,
        )
        db.add(new_meal)
        db.flush()

        # Copy food items
        for mfi in meal.food_items:
            new_mfi = MealFoodItem(
                meal_id=new_meal.id,
                food_item_id=mfi.food_item_id,
                quantity=mfi.quantity,
                notes=mfi.notes,
            )
            db.add(new_mfi)

        new_meals.append(new_meal)

    db.commit()
    return {"copied": len(new_meals)}


# Templates
@router.get("/templates", response_model=list[MealTemplateResponse])
def get_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(MealTemplate).filter(MealTemplate.user_id == current_user.id).all()


@router.post("/templates", response_model=MealTemplateResponse)
def create_template(
    template_data: MealTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    template = MealTemplate(user_id=current_user.id, **template_data.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


# Food Items
@router.get("/foods", response_model=list[FoodItemResponse])
def search_foods(
    q: str | None = None,
    category: str | None = None,
    user_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search food items. Returns shared items + user's own."""
    from sqlalchemy import or_

    query = db.query(FoodItem).filter(FoodItem.deleted_at.is_(None))

    if user_only:
        query = query.filter(FoodItem.user_id == current_user.id)
    else:
        query = query.filter(
            or_(FoodItem.is_shared == True, FoodItem.user_id == current_user.id)  # noqa: E712
        )

    if q:
        query = query.filter(FoodItem.name.ilike(f"%{q}%"))
    if category:
        query = query.filter(FoodItem.category == category)

    return query.order_by(FoodItem.name).limit(limit).all()


@router.post("/foods", response_model=FoodItemResponse)
def create_food_item(
    data: FoodItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new food item."""
    food = FoodItem(user_id=current_user.id, source="manual", **data.model_dump())
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


# External food search (must be before /foods/{food_id} routes)
class ExternalFoodResult(BaseModel):
    external_id: str
    name: str
    brand: str | None = None
    category: str | None = None
    serving_size: float = 100
    serving_unit: str = "g"
    calories: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    source: str


@router.get("/foods/search-external", response_model=list[ExternalFoodResult])
async def search_external_foods(
    q: str = Query(..., min_length=2),
    limit: int = Query(15, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """Search USDA + Open Food Facts for foods not in local DB."""
    from app.food_search import search_external

    return await search_external(q, limit)


class ImportExternalFood(BaseModel):
    external_id: str
    name: str
    brand: str | None = None
    category: str | None = None
    serving_size: float = 100
    serving_unit: str = "g"
    calories: int | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    source: str


@router.post("/foods/import-external", response_model=FoodItemResponse)
def import_external_food(
    data: ImportExternalFood,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import a food from external search into the local database."""
    food = FoodItem(
        user_id=current_user.id,
        name=data.name,
        brand=data.brand,
        category=data.category,
        serving_size=data.serving_size,
        serving_unit=data.serving_unit,
        calories=data.calories,
        protein_g=data.protein_g,
        carbs_g=data.carbs_g,
        fat_g=data.fat_g,
        fiber_g=data.fiber_g,
        is_shared=True,
        source=data.source,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


@router.put("/foods/{food_id}", response_model=FoodItemResponse)
def update_food_item(
    food_id: int,
    data: FoodItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a food item (owner only)."""
    food = (
        db.query(FoodItem)
        .filter(FoodItem.id == food_id, FoodItem.user_id == current_user.id)
        .filter(FoodItem.deleted_at.is_(None))
        .first()
    )
    if not food:
        raise HTTPException(status_code=404, detail="Food item not found")

    for key, value in data.model_dump().items():
        setattr(food, key, value)
    db.commit()
    db.refresh(food)
    return food


@router.delete("/foods/{food_id}")
def delete_food_item(
    food_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a food item (owner only, blocked if referenced by meals)."""
    food = (
        db.query(FoodItem)
        .filter(FoodItem.id == food_id, FoodItem.user_id == current_user.id)
        .filter(FoodItem.deleted_at.is_(None))
        .first()
    )
    if not food:
        raise HTTPException(status_code=404, detail="Food item not found")

    # Check if referenced by any meals
    ref_count = (
        db.query(MealFoodItem).filter(MealFoodItem.food_item_id == food_id).count()
    )
    if ref_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete: food item is used in {ref_count} meal(s)",
        )

    food.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}
