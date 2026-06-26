from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.application import ApplicationService
from app.services.notification import NotificationService
from app.services.user import UserService


@dataclass(slots=True)
class ServiceContainer:
    session: AsyncSession
    users: UserService
    applications: ApplicationService
    notifications: NotificationService | None = None

    @classmethod
    def from_session(
        cls,
        session: AsyncSession,
        notifications: NotificationService | None = None,
    ) -> "ServiceContainer":
        return cls(
            session=session,
            users=UserService(session),
            applications=ApplicationService(session),
            notifications=notifications,
        )
