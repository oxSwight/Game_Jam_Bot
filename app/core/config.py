from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_ids: list[int] = Field(default_factory=list, alias="ADMIN_IDS")

    database_url: str = Field(
        default="sqlite+aiosqlite:///./players.db",
        alias="DATABASE_URL",
    )
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    fsm_storage: str = Field(default="redis", alias="FSM_STORAGE")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=False, alias="LOG_JSON")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> list[int]:
        if isinstance(value, list):
            return [int(v) for v in value]
        if not value:
            return []
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip().isdigit()]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
