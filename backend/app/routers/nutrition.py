from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date

from app.database import get_db
from app.models import User, Meal, MealTemplate
from app.routers.auth import get_current_user

router = APIRouter()


class MealCreate(BaseModel):
    date: date
    label: str
    time: str | None = None
    calories: int | None = None
    description: str | None = None


class MealResponse(MealCreate):
    id: int
    user_id: int

    class Config:
        from_attributes = True


class MealTemplateCreate(BaseModel):
    name: str
    label: str
    calories: int | None = None
    description: str | None = None


class MealTemplateResponse(MealTemplateCreate):
    id: int

    class Config:
        from_attributes = True


@router.get("/meals", response_model=list[MealResponse])
def get_meals(
    meal_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Meal).filter(Meal.user_id == current_user.id)

    if meal_date:
        query = query.filter(Meal.date == meal_date)

    return query.order_by(Meal.date.desc(), Meal.time).all()


@router.post("/meals", response_model=MealResponse)
def create_meal(
    meal_data: MealCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meal = Meal(user_id=current_user.id, **meal_data.model_dump())
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal


@router.put("/meals/{meal_id}", response_model=MealResponse)
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
    return meal


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
