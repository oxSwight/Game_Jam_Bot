import logging
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    # NoDecode: stop pydantic-settings from JSON-decoding this env var before our
    # validator runs. Without it, a single id like "717098190" is valid JSON and
    # gets decoded to an int, which our before-validator then turns into [] —
    # silently disabling all admin access. See parse_admin_ids below.
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list, alias="ADMIN_IDS")

    # The private/closed group the bot gates access to. On approval the bot mints a
    # join-request invite link into this chat (the join is then auto-approved only
    # for the approved applicant). Optional so the bot can still boot for
    # local/testing, but approvals fail loudly (and are logged) until it is set.
    group_chat_id: int | None = Field(default=None, alias="GROUP_CHAT_ID")

    # Anti-spam: hard ceiling on applications sitting in pending_review. Once the
    # queue is full, /register is refused until admins drain it. Protects the DB
    # and admin workflow from a flood of bogus sign-ups.
    pending_cap: int = Field(default=300, alias="PENDING_CAP")

    # PostgreSQL is the production database. SQLite is only used by the test suite
    # (in-memory), so it is never the default here.
    database_url: str = Field(
        default="postgresql+asyncpg://gamejam:gamejam@localhost:5432/gamejam",
        alias="DATABASE_URL",
    )
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    fsm_storage: str = Field(default="redis", alias="FSM_STORAGE")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=False, alias="LOG_JSON")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, int):
            return [value]
        if isinstance(value, (list, tuple)):
            return [int(v) for v in value]
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip().lstrip("-").isdigit()]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
