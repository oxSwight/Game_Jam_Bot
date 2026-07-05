from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session) -> None:
        super().__init__(session, User)

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
