"""Add training_plans and planned_workouts tables

Revision ID: m1n2o3p4q5r6
Revises: l2m3n4o5p6q7
Create Date: 2026-03-24 00:01:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "l2m3n4o5p6q7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("plan_name", sa.String(100), nullable=False),
        sa.Column("plan_display_name", sa.String(200), nullable=False),
        sa.Column("race_date", sa.Date(), nullable=False),
        sa.Column("race_distance_km", sa.Float(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_training_plans_user_id", "training_plans", ["user_id"])

    op.create_table(
        "planned_workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("training_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("workout_type", sa.String(50), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("target_distance_km", sa.Float(), nullable=True),
        sa.Column("target_pace_description", sa.String(200), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "activity_id",
            sa.Integer(),
            sa.ForeignKey("activities.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_planned_workouts_plan_id", "planned_workouts", ["plan_id"])
    op.create_index("ix_planned_workouts_date", "planned_workouts", ["date"])
    op.create_index(
        "ix_planned_workouts_plan_id_date", "planned_workouts", ["plan_id", "date"]
    )


def downgrade() -> None:
    op.drop_table("planned_workouts")
    op.drop_table("training_plans")
