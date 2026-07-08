"""application strengths (step F, beginner branch)

Adds the ``strengths`` JSON column to applications: a multi-select of what a
beginner applicant is best at, collected only on the beginner branch (step F).
Non-beginner rows keep the empty-list default.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-08 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'applications',
        sa.Column('strengths', sa.JSON(), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('applications', 'strengths')
