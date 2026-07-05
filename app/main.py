import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    ErrorEvent,
)

from app.core.config import get_settings
from app.core.database import run_migrations
from app.core.instance_lock import InstanceLock
from app.core.logging import setup_logging
from app.core.redis import create_fsm_storage, create_redis
from app.handlers.admin import router as admin_router
from app.handlers.admin_extra import router as admin_extra_router
from app.handlers.registration import router as registration_router
from app.middlewares import (
    AdminMiddleware,
    DbSessionMiddleware,
    LanguageMiddleware,
    ServicesMiddleware,
    ThrottlingMiddleware,
)
from app.services.notification import NotificationService

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="register", description="Подать заявку"),
    BotCommand(command="status", description="Статус вашей заявки"),
    BotCommand(command="edit", description="Изменить ник/email"),
    BotCommand(command="withdraw", description="Удалить заявку и подать заново"),
    BotCommand(command="language", description="Язык / Language"),
    BotCommand(command="whoami", description="Ваш ID и роль"),
    BotCommand(command="help", description="Список команд"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="queue", description="👑 Очередь заявок"),
    BotCommand(command="pending", description="👑 Сколько заявок на проверке"),
    BotCommand(command="approve", description="👑 Одобрить заявку"),
    BotCommand(command="reject", description="👑 Отклонить заявку"),
    BotCommand(command="delete", description="👑 Удалить заявку"),
    BotCommand(command="stats", description="👑 Статистика"),
    BotCommand(command="export", description="👑 Экспорт CSV"),
    BotCommand(command="broadcast", description="👑 Рассылка одобренным"),
    BotCommand(command="leaderboard", description="👑 Лидерборд"),
    BotCommand(command="events", description="👑 События"),
    BotCommand(command="teams", description="👑 Команды события"),
]


async def _setup_commands(bot: Bot, admin_ids: list[int]) -> None:
    """Populate Telegram's '/' menu: base commands for everyone, plus the admin
    set scoped to each admin's private chat so the tools are discoverable."""
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in admin_ids:
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception:
            logger.warning("could not set admin commands for %s", admin_id, exc_info=True)


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
    await run_migrations()

    storage, redis = await _create_storage()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    notifications = NotificationService(bot)

    dp = Dispatcher(storage=storage)

    # Middleware order matters (outer → inner):
    # throttle (shed spam early) → DB session → services → language → admin auth
    dp.update.middleware(ThrottlingMiddleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(ServicesMiddleware(notification_service=notifications))
    dp.update.middleware(LanguageMiddleware())
    dp.update.middleware(AdminMiddleware())

    dp.include_router(registration_router)
    dp.include_router(admin_router)
    dp.include_router(admin_extra_router)

    @dp.error()
    async def global_error_handler(event: ErrorEvent) -> None:
        logger.exception(
            "Unhandled exception while processing update",
            exc_info=event.exception,
        )

    await bot.delete_webhook(drop_pending_updates=True)
    await _setup_commands(bot, settings.admin_ids)
    logger.info(
        "bot starting",
        extra={"extra_fields": {"log_json": settings.log_json, "admin_ids": settings.admin_ids}},
    )
    try:
        await dp.start_polling(bot)
    finally:
        if redis is not None:
            await redis.aclose()
        await bot.session.close()
        lock.release()


if __name__ == "__main__":
    asyncio.run(main())
