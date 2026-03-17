"""Add compound indexes on (user_id, date) for query performance

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-03-17 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "i9j0k1l2m3n4"
down_revision: Union[str, None] = "h8i9j0k1l2m3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_daily_logs_user_date", "daily_logs", ["user_id", "date"])
    op.create_index("ix_meals_user_date", "meals", ["user_id", "date"])
    op.create_index(
        "ix_daily_nutrition_user_date", "daily_nutrition", ["user_id", "date"]
    )
    op.create_index("ix_activities_user_date", "activities", ["user_id", "date"])
    op.create_index(
        "ix_body_measurements_user_date", "body_measurements", ["user_id", "date"]
    )
    op.create_index(
        "ix_progress_photos_user_date", "progress_photos", ["user_id", "date"]
    )


def downgrade() -> None:
    op.drop_index("ix_progress_photos_user_date", table_name="progress_photos")
    op.drop_index("ix_body_measurements_user_date", table_name="body_measurements")
    op.drop_index("ix_activities_user_date", table_name="activities")
    op.drop_index("ix_daily_nutrition_user_date", table_name="daily_nutrition")
    op.drop_index("ix_meals_user_date", table_name="meals")
    op.drop_index("ix_daily_logs_user_date", table_name="daily_logs")
