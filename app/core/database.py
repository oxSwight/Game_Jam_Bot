import asyncio
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.models.base import Base

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    # Import the models package for its side effect: registering every mapped
    # class on Base.metadata so create_all sees the full schema.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    return cfg


async def _bootstrap_legacy_schema() -> bool:
    """Handle databases created by the pre-Alembic ``create_all`` path.

    If app tables already exist but there is no ``alembic_version`` table, this
    is a legacy DB. We create any tables added since (events, teams), add the
    ``applications.team_id`` column if missing, then let the caller stamp it to
    head — preserving existing rows instead of failing on 'table already exists'.
    Returns True when a legacy DB was adopted (so the caller stamps instead of
    upgrading), False for a fresh database that should migrate normally.
    """
    from sqlalchemy import inspect

    import app.models  # noqa: F401

    def _inspect(sync_conn):
        insp = inspect(sync_conn)
        tables = set(insp.get_table_names())
        cols = (
            {c["name"] for c in insp.get_columns("applications")}
            if "applications" in tables
            else set()
        )
        return tables, cols

    async with engine.begin() as conn:
        tables, app_cols = await conn.run_sync(_inspect)

        if "alembic_version" in tables or "users" not in tables:
            # Already versioned, or a fresh DB — nothing legacy to adopt.
            return False

        logger.warning("legacy (un-versioned) database detected — adopting into Alembic")
        # create_all is checkfirst by default: only missing tables are created.
        await conn.run_sync(Base.metadata.create_all)
        if "team_id" not in app_cols:
            from sqlalchemy import text

            await conn.execute(
                text("ALTER TABLE applications ADD COLUMN team_id INTEGER")
            )
    return True


def _run_alembic(command_name: str) -> None:
    """Run an Alembic command synchronously. Must be called off the event loop:
    env.py drives the async engine via asyncio.run, which can't nest inside an
    already-running loop."""
    from alembic import command

    cfg = _alembic_config()
    getattr(command, command_name)(cfg, "head")


async def run_migrations() -> None:
    """Bring the database schema up to date on startup."""
    adopted = await _bootstrap_legacy_schema()
    if adopted:
        logger.info("stamping adopted legacy database to head")
        await asyncio.to_thread(_run_alembic, "stamp")
        return
    logger.info("running database migrations (alembic upgrade head)")
    await asyncio.to_thread(_run_alembic, "upgrade")
    logger.info("database migrations up to date")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
