"""Regression test for the pre-Alembic database adoption path.

Simulates an un-versioned DB (created by the old create_all, no alembic_version)
and asserts _bootstrap_legacy_schema adopts it without raising and without
touching existing rows — the data-loss-sensitive branch.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.database as db
import app.models  # noqa: F401  (populate metadata)
from app.models.base import Base


async def test_bootstrap_adopts_unversioned_db(tmp_path, monkeypatch):
    db_file = tmp_path / "legacy.db"
    legacy_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")

    # Build an existing schema WITHOUT alembic_version, and seed a user.
    async with legacy_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await conn.execute(
            text("INSERT INTO users (telegram_id, language) VALUES (999, 'ru')")
        )

    monkeypatch.setattr(db, "engine", legacy_engine)

    adopted = await db._bootstrap_legacy_schema()
    assert adopted is True  # recognised as legacy → caller will stamp

    async with legacy_engine.begin() as conn:
        count = await conn.scalar(text("SELECT count(*) FROM users"))
        cols = [
            row[1]
            for row in await conn.execute(text("PRAGMA table_info(applications)"))
        ]
    assert count == 1  # existing row preserved
    assert "team_id" in cols  # new column added
    await legacy_engine.dispose()


async def test_bootstrap_fresh_db_returns_false(tmp_path, monkeypatch):
    """A brand-new empty DB is not 'legacy' — it should migrate normally."""
    db_file = tmp_path / "fresh.db"
    fresh_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setattr(db, "engine", fresh_engine)

    adopted = await db._bootstrap_legacy_schema()
    assert adopted is False
    await fresh_engine.dispose()
