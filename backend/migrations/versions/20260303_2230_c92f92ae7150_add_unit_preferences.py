"""add_unit_preferences

Revision ID: c92f92ae7150
Revises: 944cdba064bf
Create Date: 2026-03-03 22:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c92f92ae7150'
down_revision: Union[str, None] = '944cdba064bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unit preference columns to user_settings table
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('distance_unit', sa.String(length=10), nullable=False, server_default='km'))
        batch_op.add_column(sa.Column('measurement_unit', sa.String(length=10), nullable=False, server_default='cm'))
        batch_op.add_column(sa.Column('weight_unit', sa.String(length=10), nullable=False, server_default='kg'))
        batch_op.add_column(sa.Column('water_unit', sa.String(length=10), nullable=False, server_default='ml'))


def downgrade() -> None:
    # Remove unit preference columns
    with op.batch_alter_table('user_settings', schema=None) as batch_op:
        batch_op.drop_column('water_unit')
        batch_op.drop_column('weight_unit')
        batch_op.drop_column('measurement_unit')
        batch_op.drop_column('distance_unit')
