"""Routines: a saved workout you repeat.

Unlike the exercise catalogue, a routine **belongs to one account**. The movements
in it are shared; how you choose to program them is yours. Two people following
different plans out of the same library is the normal case, not an edge one.

The header row is `workout_templates`, a table that has existed unused since the
initial schema (see the migration for why it is reused rather than replaced).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from app import planning
from app.database import get_db
from app.models import User, WorkoutTemplate
from app.routers.auth import get_current_user

router = APIRouter()


class RoutineExerciseInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    catalog_id: int | None = None
    target_sets: int | None = Field(None, ge=1, le=100)
    target_reps: int | None = Field(None, ge=1, le=1000)
    target_weight_kg: float | None = Field(None, ge=0, le=1000)
    notes: str | None = Field(None, max_length=255)


class RoutineExerciseResponse(RoutineExerciseInput):
    id: int
    position: int

    class Config:
        from_attributes = True


class RoutineInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    default_duration_mins: int | None = Field(None, ge=1, le=600)
    exercises: list[RoutineExerciseInput] = Field(default_factory=list, max_length=50)


class RoutineResponse(BaseModel):
    id: int
    name: str
    default_duration_mins: int | None
    exercises: list[RoutineExerciseResponse]

    class Config:
        from_attributes = True


def _owned(db: Session, user: User):
    return planning.owned_routines(db, user.id)


def _http(exc: planning.PlanningError) -> HTTPException:
    return HTTPException(status_code=409 if exc.conflict else 400, detail=str(exc))


@router.get("/", response_model=list[RoutineResponse])
def list_routines(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        _owned(db, current_user)
        .options(selectinload(WorkoutTemplate.exercises))
        .order_by(WorkoutTemplate.name)
        .all()
    )


@router.post("/", response_model=RoutineResponse)
def create_routine(
    data: RoutineInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        routine = planning.save_routine(
            db,
            current_user.id,
            name=data.name,
            exercises=data.exercises,
            default_duration_mins=data.default_duration_mins,
        )
    except planning.PlanningError as exc:
        raise _http(exc) from None
    db.commit()
    db.refresh(routine)
    return routine


@router.put("/{routine_id}", response_model=RoutineResponse)
def update_routine(
    routine_id: int,
    data: RoutineInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    routine = _owned(db, current_user).filter(WorkoutTemplate.id == routine_id).first()
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    try:
        # A PUT carries the whole routine, so `exercises` is always sent and
        # always replaces. The assistant path omits it to mean "leave them".
        planning.save_routine(
            db,
            current_user.id,
            name=data.name,
            exercises=data.exercises,
            default_duration_mins=data.default_duration_mins,
            routine=routine,
            # A PUT carries the whole routine, so an omitted duration clears it.
            replace=True,
        )
    except planning.PlanningError as exc:
        raise _http(exc) from None
    db.commit()
    db.refresh(routine)
    return routine


@router.delete("/{routine_id}")
def delete_routine(
    routine_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A hard delete, unlike the catalogue.

    Nothing references a routine — sessions copy from it rather than pointing at
    it — so removing one strands no history, and there is no reason to keep a
    plan you have abandoned.
    """
    routine = _owned(db, current_user).filter(WorkoutTemplate.id == routine_id).first()
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    db.delete(routine)
    db.commit()
    return {"status": "deleted", "id": routine_id}
