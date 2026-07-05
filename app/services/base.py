from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.application import ApplicationRepository
from app.repositories.event import EventRepository, TeamRepository
from app.repositories.user import UserRepository


class BaseService:
    """Lightweight DI base — repositories are created per request session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._users: UserRepository | None = None
        self._applications: ApplicationRepository | None = None
        self._events: EventRepository | None = None
        self._teams: TeamRepository | None = None

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

    @property
    def events(self) -> EventRepository:
        if self._events is None:
            self._events = EventRepository(self.session)
        return self._events

    @property
    def teams(self) -> TeamRepository:
        if self._teams is None:
            self._teams = TeamRepository(self.session)
        return self._teams
