"""Shared test fixtures.

Every test runs against a fresh in-memory SQLite database (StaticPool so the
single connection is shared across the async session), built from the ORM
metadata. This keeps tests fast and fully isolated - no external Redis/Postgres.
"""

import os

import pytest
import pytest_asyncio

# Settings read env at import time; provide required values before any app import.
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_IDS", "111,222")
os.environ.setdefault("FSM_STORAGE", "memory")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: E402,F401  (register all tables on metadata)
from app.models.base import Base  # noqa: E402
from app.services import ServiceContainer  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with maker() as s:
        yield s


@pytest.fixture
def services(session) -> ServiceContainer:
    return ServiceContainer.from_session(session)


def make_payload(
    telegram_id: int = 1001,
    nickname: str = "Tester",
    email: str = "tester@example.com",
    category_id: str = "programming",
    category_title: str = "Programming / Engineering",
    roles: list[str] | None = None,
):
    """Build a valid RegistrationCreate the way the FSM would."""
    from app.schemas.registration import RegistrationCreate

    return RegistrationCreate.from_fsm_data(
        data={
            "nickname": nickname,
            "email": email,
            "category_id": category_id,
            "category_title": category_title,
            "roles": roles if roles is not None else ["gameplay_programmer", "general_programmer"],
            "experience_level": "beginner",
            "engine": ["Unity"],
            "engine_other": None,
            "tools": ["Blender"],
            "tools_other": None,
            "motivations": ["Learning"],
            "consent": True,
        },
        telegram_id=telegram_id,
        telegram_username="tester",
    )
