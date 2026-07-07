from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session, User)

    async def get_by_username(self, username: str) -> User | None:
        """Look up a user by their stored Telegram @username (case-insensitive,
        without the leading @). Returns the first match; usernames aren't unique
        over time (a handle can be re-used), but the stored value is our best
        pointer for an admin-issued invite."""
        cleaned = username.lstrip("@").strip()
        if not cleaned:
            return None
        result = await self.session.scalars(
            select(User)
            .where(func.lower(User.telegram_username) == cleaned.lower())
            .order_by(User.updated_at.desc())
        )
        return result.first()

    async def get_language(self, telegram_id: int) -> str | None:
        """Lightweight single-column lookup for the per-update language
        middleware — avoids loading the user and all their applications."""
        return await self.session.scalar(
            select(User.language).where(User.telegram_id == telegram_id)
        )

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.scalars(
            select(User)
            .where(User.telegram_id == telegram_id)
            .options(selectinload(User.applications)),
        )
        return result.first()

    async def get_or_create(
        self,
        telegram_id: int,
        telegram_username: str | None = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            if telegram_username and user.telegram_username != telegram_username:
                user.telegram_username = telegram_username
            return user
        user = User(telegram_id=telegram_id, telegram_username=telegram_username)
        return await self.add(user)
