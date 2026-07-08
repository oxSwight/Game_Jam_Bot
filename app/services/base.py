from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.application import ApplicationRepository
from app.repositories.user import UserRepository


class BaseService:
    """Lightweight DI base - repositories are created per request session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._users: UserRepository | None = None
        self._applications: ApplicationRepository | None = None

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            self._users = UserRepository(self.session)
        return self._users

    @property
    def applications(self) -> ApplicationRepository:
        if self._applications is None:
            self._applications = ApplicationRepository(self.session)
        return self._applications
