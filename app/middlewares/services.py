from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ServiceContainer
from app.services.notification import NotificationService


class ServicesMiddleware(BaseMiddleware):
    """Builds a per-request service container from the injected DB session."""

    def __init__(self, notification_service: NotificationService | None = None) -> None:
        self.notification_service = notification_service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession | None = data.get("session")
        if session is None:
            raise RuntimeError("DbSessionMiddleware must run before ServicesMiddleware")

        data["services"] = ServiceContainer.from_session(
            session=session,
            notifications=self.notification_service,
        )
        return await handler(event, data)
