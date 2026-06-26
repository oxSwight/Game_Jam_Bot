from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.config import get_settings


class AdminMiddleware(BaseMiddleware):
    """Blocks non-admin users from admin handlers when `is_admin_required` is set."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = _extract_user(event)
        if user is None:
            return await handler(event, data)

        data["is_admin"] = user.id in get_settings().admin_ids
        if data.get("admin_required") and not data["is_admin"]:
            if isinstance(event, Message):
                await event.answer("Недостаточно прав.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Недостаточно прав.", show_alert=True)
            return None
        return await handler(event, data)


def _extract_user(event: TelegramObject):
    if isinstance(event, Message) and event.from_user:
        return event.from_user
    if isinstance(event, CallbackQuery) and event.from_user:
        return event.from_user
    return None
