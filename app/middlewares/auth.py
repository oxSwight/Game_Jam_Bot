from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.core.config import get_settings


class AdminMiddleware(BaseMiddleware):
    """Stamps `is_admin` on the handler context for every update.

    Registered on the update observer, so `event` is an aiogram `Update` - the
    actual Message/CallbackQuery lives on `update.event`. Prefer the
    `event_from_user` aiogram already resolved into `data`, and fall back to
    unwrapping the Update ourselves so this works regardless of middleware order.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user") or _extract_user(event)
        if user is None:
            data.setdefault("is_admin", False)
            return await handler(event, data)

        data["is_admin"] = user.id in get_settings().admin_ids
        if data.get("admin_required") and not data["is_admin"]:
            inner = event.event if isinstance(event, Update) else event
            if isinstance(inner, Message):
                await inner.answer("Недостаточно прав.")
            elif isinstance(inner, CallbackQuery):
                await inner.answer("Недостаточно прав.", show_alert=True)
            return None
        return await handler(event, data)


def _extract_user(event: TelegramObject):
    # At the update-observer level the event is an Update wrapping the real one.
    if isinstance(event, Update):
        event = event.event
    return getattr(event, "from_user", None)
