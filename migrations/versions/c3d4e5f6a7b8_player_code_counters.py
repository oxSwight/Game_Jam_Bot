"""per-category player_code counters

Replaces the racy ``max(player_code)+1`` scan with an atomic per-category
counter row (see app.models.counter.PlayerCodeCounter). Seeded from the highest
code already issued in each category's block so existing ids keep incrementing
without collisions.

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-07-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Self-contained copy of the category blocks (app.data.catalog.CATEGORY_ID_PREFIX
# / PLAYER_CODE_WIDTH at the time of this revision) - migrations must not track
# later catalog edits.
_CATEGORY_PREFIX = {
    "programming": 1,
    "game_design": 2,
    "art_2d": 3,
    "art_3d": 4,
    "audio": 5,
    "management": 6,
}
_WIDTH = 6


def upgrade() -> None:
    op.create_table(
        'player_code_counters',
        sa.Column('category_id', sa.String(length=64), nullable=False),
        sa.Column('last_code', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('category_id'),
    )

    conn = op.get_bind()
    block = 10 ** _WIDTH
    for category_id, prefix in _CATEGORY_PREFIX.items():
        base = prefix * block
        current = conn.execute(
            sa.text(
                "SELECT max(player_code) FROM applications "
                "WHERE player_code >= :lo AND player_code < :hi"
            ),
            {"lo": base, "hi": base + block},
        ).scalar()
        conn.execute(
            sa.text(
                "INSERT INTO player_code_counters (category_id, last_code) "
                "VALUES (:category_id, :last_code)"
            ),
            {"category_id": category_id, "last_code": current or base},
        )


def downgrade() -> None:
    op.drop_table('player_code_counters')
