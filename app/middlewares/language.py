from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.i18n import DEFAULT_LANG, normalize_lang
from app.services import ServiceContainer


class LanguageMiddleware(BaseMiddleware):
    """Resolves the caller's UI language and stamps ``lang`` into handler data.

    Priority: the user's saved ``User.language`` (set via /language) → the
    Telegram client's ``language_code`` → DEFAULT_LANG. Must run after
    ServicesMiddleware so the per-request container is available.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lang = DEFAULT_LANG
        user = data.get("event_from_user")
        services: ServiceContainer | None = data.get("services")

        if user is not None:
            client_lang = normalize_lang(getattr(user, "language_code", None))
            lang = client_lang
            if services is not None:
                saved = await services.users.get_language(user.id)
                if saved:
                    lang = normalize_lang(saved)

        data["lang"] = lang
        return await handler(event, data)
