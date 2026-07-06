"""player active-flag, category-coded ids, per-application contact snapshot

Revision ID: b1c2d3e4f5a6
Revises: 5a2f87ea5d0c
Create Date: 2026-07-06 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '5a2f87ea5d0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Group-membership flag: True while the player is in the gated group.
    op.add_column(
        'users',
        sa.Column('is_active', sa.Boolean(), server_default='0', nullable=False),
    )

    # Category-coded public id + per-application contact snapshot.
    op.add_column('applications', sa.Column('player_code', sa.BigInteger(), nullable=True))
    op.add_column('applications', sa.Column('nickname', sa.String(length=32), nullable=True))
    op.add_column('applications', sa.Column('email', sa.String(length=255), nullable=True))
    op.create_index(
        op.f('ix_applications_player_code'), 'applications', ['player_code'], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_applications_player_code'), table_name='applications')
    op.drop_column('applications', 'email')
    op.drop_column('applications', 'nickname')
    op.drop_column('applications', 'player_code')
    op.drop_column('users', 'is_active')
