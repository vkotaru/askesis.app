"""Create food_items and meal_food_items tables

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-03-15 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h8i9j0k1l2m3"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "food_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(200), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("serving_size", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "serving_unit", sa.String(20), nullable=False, server_default="g"
        ),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("fiber_g", sa.Float(), nullable=True),
        sa.Column(
            "is_shared", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", "brand", name="unique_food_item"),
    )
    op.create_index(op.f("ix_food_items_name"), "food_items", ["name"], unique=False)

    op.create_table(
        "meal_food_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("meal_id", sa.Integer(), nullable=False),
        sa.Column("food_item_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(
            ["meal_id"], ["meals.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["food_item_id"], ["food_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_meal_food_items_meal_id"),
        "meal_food_items",
        ["meal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_meal_food_items_food_item_id"),
        "meal_food_items",
        ["food_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_meal_food_items_food_item_id"), table_name="meal_food_items"
    )
    op.drop_index(op.f("ix_meal_food_items_meal_id"), table_name="meal_food_items")
    op.drop_table("meal_food_items")
    op.drop_index(op.f("ix_food_items_name"), table_name="food_items")
    op.drop_table("food_items")
