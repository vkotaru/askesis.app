import os
import uuid
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date
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

from app.database import get_db
from app.models import User, Meal, MealTemplate
from app.routers.auth import get_current_user, check_view_permission

router = APIRouter()

# Upload directory for meal photos
MEAL_UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "meals"
MEAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def validate_file_path(file_path: Path) -> Path:
    """Validate that file path is within upload directory (prevent path traversal)."""
    resolved = file_path.resolve()
    upload_resolved = MEAL_UPLOAD_DIR.resolve()
    if not str(resolved).startswith(str(upload_resolved)):
        raise HTTPException(status_code=403, detail="Invalid file path")
    return resolved


class MealCreate(BaseModel):
    date: date
    label: str = Field(..., min_length=1, max_length=50)
    time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")  # HH:MM format
    calories: int | None = Field(None, ge=0, le=10000)
    description: str | None = Field(None, max_length=2000)


class MealResponse(MealCreate):
    id: int
    user_id: int
    photo_path: str | None = None
    ai_analysis: str | None = None
    photo_url: str | None = None

    class Config:
        from_attributes = True


class FoodAnalysis(BaseModel):
    calories: int | None = None
    description: str | None = None
    foods: list[str] = []
    macros: dict | None = None


def process_meal_image(file_path: Path, max_size: int = 800, quality: int = 80) -> Path:
    """Process uploaded meal image: resize, optimize."""
    img = Image.open(file_path)
    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "P", "CMYK"):
        img = img.convert("RGB")

    if img.size[0] > max_size or img.size[1] > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    output_path = file_path.with_suffix(".jpg")
    img.save(output_path, "JPEG", quality=quality, optimize=True)

    if output_path != file_path and file_path.exists():
        file_path.unlink()

    return output_path


async def analyze_food_with_gemini(image_path: Path) -> FoodAnalysis | None:
    """Use Gemini to analyze food in image."""
    if not GEMINI_AVAILABLE:
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Load image
        img = Image.open(image_path)

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


def meal_to_response(meal: Meal) -> dict:
    """Convert Meal to response dict with photo URL."""
    return {
        "id": meal.id,
        "user_id": meal.user_id,
        "date": meal.date,
        "label": meal.label,
        "time": meal.time,
        "calories": meal.calories,
        "description": meal.description,
        "photo_path": meal.photo_path,
        "ai_analysis": meal.ai_analysis,
        "photo_url": f"/api/nutrition/meals/{meal.id}/photo" if meal.photo_path else None,
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


@router.get("/meals")
def get_meals(
    meal_date: date | None = None,
    user_id: int | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = check_view_permission(user_id, "nutrition", db, current_user)
    query = db.query(Meal).filter(Meal.user_id == target_user.id)

    if meal_date:
        query = query.filter(Meal.date == meal_date)

    meals = query.order_by(Meal.date.desc(), Meal.time).offset(offset).limit(limit).all()
    return [meal_to_response(m) for m in meals]


@router.post("/meals")
def create_meal(
    meal_data: MealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = Meal(user_id=current_user.id, **meal_data.model_dump())
    db.add(meal)
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
    meal = db.query(Meal).filter(
        Meal.id == meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    for key, value in meal_data.model_dump().items():
        setattr(meal, key, value)

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
    meal = db.query(Meal).filter(
        Meal.id == meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Generate unique filename
    file_ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    unique_name = f"{current_user.id}_{meal_id}_{uuid.uuid4().hex[:8]}{file_ext}"
    file_path = MEAL_UPLOAD_DIR / unique_name

    # Save uploaded file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Process image
    try:
        processed_path = process_meal_image(file_path)
    except Exception as e:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}")

    # Delete old photo if exists
    if meal.photo_path:
        old_path = Path(meal.photo_path)
        if old_path.exists():
            old_path.unlink()

    # Update meal with photo path
    meal.photo_path = str(processed_path)

    # Analyze with Gemini if requested
    analysis = None
    if analyze:
        analysis = await analyze_food_with_gemini(processed_path)
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

    if not meal or not meal.photo_path:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Check permission - allow owner or shared users
    if meal.user_id != current_user.id:
        check_view_permission(meal.user_id, "nutrition", db, current_user)

    # Validate path is within upload directory (prevent path traversal)
    file_path = validate_file_path(Path(meal.photo_path))
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Photo file not found")

    return FileResponse(file_path, media_type="image/jpeg")


@router.post("/analyze-photo")
async def analyze_food_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Analyze a food photo without creating a meal (preview)."""
    if not GEMINI_AVAILABLE:
        raise HTTPException(status_code=503, detail="Gemini API not available")

    # Validate file type
    allowed_types = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type")

    # Save temporarily
    temp_name = f"temp_{uuid.uuid4().hex}.jpg"
    temp_path = MEAL_UPLOAD_DIR / temp_name

    content = await file.read()
    with open(temp_path, "wb") as f:
        f.write(content)

    try:
        processed_path = process_meal_image(temp_path)
        analysis = await analyze_food_with_gemini(processed_path)

        return analysis.model_dump() if analysis else {"error": "Analysis failed"}

    finally:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)
        if processed_path.exists():
            processed_path.unlink()


@router.delete("/meals/{meal_id}")
def delete_meal(
    meal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = db.query(Meal).filter(
        Meal.id == meal_id,
        Meal.user_id == current_user.id
    ).first()

    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    db.delete(meal)
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

    yesterday_meals = db.query(Meal).filter(
        Meal.user_id == current_user.id,
        Meal.date == yesterday
    ).all()

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
        new_meals.append(new_meal)

    db.commit()
    return {"copied": len(new_meals)}


# Templates
@router.get("/templates", response_model=list[MealTemplateResponse])
def get_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(MealTemplate).filter(
        MealTemplate.user_id == current_user.id
    ).all()


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
