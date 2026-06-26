import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.core.config import get_settings
from app.core.database import init_db
from app.core.instance_lock import InstanceLock
from app.core.logging import setup_logging
from app.core.redis import create_fsm_storage, create_redis
from app.handlers.admin import router as admin_router
from app.handlers.registration import router as registration_router
from app.middlewares import AdminMiddleware, DbSessionMiddleware, ServicesMiddleware
from app.services.notification import NotificationService

logger = logging.getLogger(__name__)


async def _create_storage() -> tuple[BaseStorage, object | None]:
    settings = get_settings()

    if settings.fsm_storage == "memory":
        logger.info("FSM storage: MemoryStorage (FSM_STORAGE=memory)")
        return MemoryStorage(), None

    if not settings.redis_url:
        raise RuntimeError(
            "No FSM storage configured: set REDIS_URL for Redis "
            "or FSM_STORAGE=memory for in-process storage."
        )

    redis = create_redis()
    await redis.ping()  # intentional fail-fast — no except
    logger.info("FSM storage: Redis (%s)", settings.redis_url)
    return create_fsm_storage(redis), redis


async def main() -> None:
    lock = InstanceLock()
    lock.acquire()

    setup_logging()
    settings = get_settings()
    await init_db()

    storage, redis = await _create_storage()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    notifications = NotificationService(bot)

    dp = Dispatcher(storage=storage)

    # Middleware order matters: DB session → services → admin auth
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(ServicesMiddleware(notification_service=notifications))
    dp.update.middleware(AdminMiddleware())

    dp.include_router(registration_router)
    dp.include_router(admin_router)

    @dp.error()
    async def global_error_handler(event: ErrorEvent) -> None:
        logger.exception(
            "Unhandled exception while processing update",
            exc_info=event.exception,
        )

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("bot starting", extra={"extra_fields": {"log_json": settings.log_json}})
    try:
        await dp.start_polling(bot)
    finally:
        if redis is not None:
            await redis.aclose()
        await bot.session.close()
        lock.release()


if __name__ == "__main__":
    asyncio.run(main())
