from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from app.core.config import get_settings


def create_redis() -> Redis:
    url = get_settings().redis_url
    if not url:
        raise RuntimeError("REDIS_URL is not set.")
    return Redis.from_url(url, decode_responses=True)


def create_fsm_storage(redis: Redis | None = None) -> BaseStorage:
    client = redis or create_redis()
    return RedisStorage(redis=client)
