"""add_activity_fields_and_color_scheme

Revision ID: 944cdba064bf
Revises: c01286a36ee9
Create Date: 2026-03-03 22:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '944cdba064bf'
down_revision: Union[str, None] = 'c01286a36ee9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create TimeOfDay enum type
    timeofday_enum = sa.Enum('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT', name='timeofday')
    timeofday_enum.create(op.get_bind(), checkfirst=True)

    # Add new columns to activities table
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('time_of_day', sa.Enum('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT', name='timeofday'), nullable=True))
        batch_op.add_column(sa.Column('url', sa.String(length=500), nullable=True))

    # Add color_scheme column to user_settings table
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('color_scheme', sa.String(length=30), nullable=False, server_default='forest'))


def downgrade() -> None:
    # Remove color_scheme from user_settings
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_column('color_scheme')

    # Remove new columns from activities
    with op.batch_alter_table('activities', schema=None) as batch_op:
        batch_op.drop_column('url')
        batch_op.drop_column('time_of_day')

    # Drop TimeOfDay enum type
    timeofday_enum = sa.Enum('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT', name='timeofday')
    timeofday_enum.drop(op.get_bind(), checkfirst=True)
