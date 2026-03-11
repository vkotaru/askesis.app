"""Create daily_nutrition table and migrate data from daily_logs

Revision ID: e5f6g7h8i9j0
Revises: d4e5f6g7h8i9
Create Date: 2026-03-11 00:03:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f6g7h8i9j0"
down_revision: Union[str, None] = "d4e5f6g7h8i9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create daily_nutrition table
    op.create_table(
        "daily_nutrition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="unique_user_nutrition_date"),
    )
    op.create_index(
        op.f("ix_daily_nutrition_date"), "daily_nutrition", ["date"], unique=False
    )

    # Migrate existing data from daily_logs to daily_nutrition
    # Only migrate rows that have at least one macro value set
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO daily_nutrition (user_id, date, protein_g, carbs_g, fat_g, created_at, updated_at)
            SELECT user_id, date, protein_g, carbs_g, fat_g, created_at, created_at
            FROM daily_logs
            WHERE protein_g IS NOT NULL OR carbs_g IS NOT NULL OR fat_g IS NOT NULL
        """)
    )

    # Drop macro columns from daily_logs
    op.drop_column("daily_logs", "total_calories")
    op.drop_column("daily_logs", "protein_g")
    op.drop_column("daily_logs", "carbs_g")
    op.drop_column("daily_logs", "fat_g")


def downgrade() -> None:
    # Add macro columns back to daily_logs
    op.add_column(
        "daily_logs", sa.Column("total_calories", sa.Integer(), nullable=True)
    )
    op.add_column("daily_logs", sa.Column("protein_g", sa.Float(), nullable=True))
    op.add_column("daily_logs", sa.Column("carbs_g", sa.Float(), nullable=True))
    op.add_column("daily_logs", sa.Column("fat_g", sa.Float(), nullable=True))

    # Migrate data back to daily_logs
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE daily_logs
            SET protein_g = dn.protein_g,
                carbs_g = dn.carbs_g,
                fat_g = dn.fat_g
            FROM daily_nutrition dn
            WHERE daily_logs.user_id = dn.user_id AND daily_logs.date = dn.date
        """)
    )

    # Drop daily_nutrition table
    op.drop_index(op.f("ix_daily_nutrition_date"), table_name="daily_nutrition")
    op.drop_table("daily_nutrition")
