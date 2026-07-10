import asyncio
import logging
import sys
import tempfile
import time
from pathlib import Path

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
from app.core.database import (
    AnotherInstanceRunningError,
    acquire_singleton_db_lock,
    release_singleton_db_lock,
    run_migrations,
)
from app.core.instance_lock import InstanceLock
from app.core.logging import setup_logging
from app.core.redis import create_fsm_storage, create_redis
from app.handlers.admin import router as admin_router
from app.handlers.admin_extra import router as admin_extra_router
from app.handlers.fallback import router as fallback_router
from app.handlers.membership import router as membership_router
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
    BotCommand(command="edit", description="Изменить ник/email/навыки"),
    BotCommand(command="invite", description="Ссылка в группу (после одобрения)"),
    BotCommand(command="withdraw", description="Удалить все свои данные"),
    BotCommand(command="language", description="Язык / Language"),
    BotCommand(command="help", description="Список команд"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="review", description="Очередь заявок"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="export", description="Экспорт CSV"),
    BotCommand(command="broadcast", description="Рассылка одобренным"),
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


# The GROUP_CHAT_ID shipped in .env.example - a live deployment left on this value
# has never configured its real group, so approvals can't mint invite links.
_EXAMPLE_GROUP_CHAT_ID = -1001234567890


def _warn_on_risky_config(settings) -> None:
    """Surface config that silently breaks the bot at INFO/WARNING so it's caught
    on startup instead of via a confused admin ('/review does nothing')."""
    if not settings.admin_ids:
        logger.warning(
            "ADMIN_IDS is EMPTY - /review, /stats, /export and /broadcast are "
            "disabled and nobody can review applications. Set ADMIN_IDS."
        )
    if settings.group_chat_id is None:
        logger.warning(
            "GROUP_CHAT_ID is not set - approvals cannot mint invite links. "
            "Set it to your gated group's numeric id."
        )
    elif settings.group_chat_id == _EXAMPLE_GROUP_CHAT_ID:
        logger.warning(
            "GROUP_CHAT_ID is still the .env.example placeholder (%s) - approvals "
            "cannot mint invite links. Set it to your real group id.",
            _EXAMPLE_GROUP_CHAT_ID,
        )


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
    await redis.ping()  # intentional fail-fast - no except
    logger.info("FSM storage: Redis (%s)", settings.redis_url)
    return create_fsm_storage(redis), redis


# Touched every HEARTBEAT_INTERVAL seconds while polling is alive; the Docker
# healthcheck fails the container when the file goes stale.
HEARTBEAT_PATH = Path(tempfile.gettempdir()) / "gamejam_bot_heartbeat"
HEARTBEAT_INTERVAL = 30.0


async def _heartbeat() -> None:
    while True:
        try:
            HEARTBEAT_PATH.write_text(str(time.time()))
        except OSError:
            logger.debug("could not write heartbeat file", exc_info=True)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def main() -> None:
    lock = InstanceLock()
    lock.acquire()

    setup_logging()
    settings = get_settings()
    _warn_on_risky_config(settings)
    await run_migrations()

    # Cluster-wide singleton: the file lock above only guards this host; the
    # advisory lock guards the shared database (e.g. two containers).
    try:
        db_lock = await acquire_singleton_db_lock()
    except AnotherInstanceRunningError:
        logger.error(
            "Another bot instance already holds the database singleton lock. "
            "Stop it before starting a new one."
        )
        lock.release()
        sys.exit(1)

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
    dp.include_router(membership_router)
    # Must be LAST: catches inline taps no other router claimed (stale buttons /
    # reset sessions) so they never vanish silently.
    dp.include_router(fallback_router)

    @dp.error()
    async def global_error_handler(event: ErrorEvent) -> None:
        logger.exception(
            "Unhandled exception while processing update",
            exc_info=event.exception,
        )
        # If the failing update was a button press, the client is stuck showing a
        # loading spinner until Telegram times it out. Clear it and surface a
        # generic error so the user knows to retry rather than staring at a hang.
        callback = event.update.callback_query
        if callback is not None:
            try:
                await callback.answer(
                    "Что-то пошло не так. Попробуйте ещё раз.", show_alert=True
                )
            except Exception:
                logger.debug("could not answer callback after error", exc_info=True)

    await bot.delete_webhook(drop_pending_updates=True)
    await _setup_commands(bot, settings.admin_ids)
    # Log the admin COUNT, not the ids - Telegram ids are PII.
    logger.info(
        "bot starting",
        extra={"extra_fields": {"log_json": settings.log_json, "admins": len(settings.admin_ids)}},
    )
    heartbeat_task = asyncio.create_task(_heartbeat())
    try:
        # resolve_used_update_types() makes Telegram deliver chat_member and
        # chat_join_request updates (needed by the membership handlers) - they're
        # excluded from the default set.
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        heartbeat_task.cancel()
        if redis is not None:
            await redis.aclose()
        await bot.session.close()
        await release_singleton_db_lock(db_lock)
        lock.release()


if __name__ == "__main__":
    asyncio.run(main())
