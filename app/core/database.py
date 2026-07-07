import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
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
    # class on Base.metadata so create_all sees the full schema. Used by the test
    # fixtures; production goes through Alembic (run_migrations).
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(_PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_PROJECT_ROOT / "migrations"))
    return cfg


def _run_alembic_upgrade() -> None:
    """Run ``alembic upgrade head`` synchronously. Must be called off the event
    loop: env.py drives the async engine via asyncio.run, which can't nest inside
    an already-running loop. Signals env.py to leave our logging config alone."""
    from alembic import command

    os.environ["ALEMBIC_SKIP_LOGGING_CONFIG"] = "1"
    try:
        command.upgrade(_alembic_config(), "head")
    finally:
        os.environ.pop("ALEMBIC_SKIP_LOGGING_CONFIG", None)


async def run_migrations() -> None:
    """Bring the PostgreSQL schema up to date on startup."""
    logger.info("running database migrations (alembic upgrade head)")
    await asyncio.to_thread(_run_alembic_upgrade)
    logger.info("database migrations up to date")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Arbitrary but fixed application-wide key for pg_advisory_lock.
_SINGLETON_LOCK_KEY = 823_547_001


class AnotherInstanceRunningError(RuntimeError):
    pass


async def acquire_singleton_db_lock() -> AsyncConnection | None:
    """Cluster-wide single-instance guarantee via a Postgres advisory lock.

    The local file lock (InstanceLock) only protects one host; two containers on
    different machines pointed at the same database would still double-poll. The
    advisory lock is held by a dedicated connection for the process lifetime and
    released automatically by Postgres if the process dies. Returns the holding
    connection (close it to release), or None on non-Postgres databases (tests).
    """
    if engine.dialect.name != "postgresql":
        return None
    conn = await engine.connect()
    try:
        acquired = (
            await conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": _SINGLETON_LOCK_KEY},
            )
        ).scalar()
    except Exception:
        await conn.close()
        raise
    if not acquired:
        await conn.close()
        raise AnotherInstanceRunningError(
            "another bot instance already holds the database singleton lock"
        )
    return conn


async def release_singleton_db_lock(conn: AsyncConnection | None) -> None:
    if conn is None:
        return
    try:
        await conn.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": _SINGLETON_LOCK_KEY}
        )
    except Exception:
        logger.debug("could not release advisory lock explicitly", exc_info=True)
    finally:
        await conn.close()
