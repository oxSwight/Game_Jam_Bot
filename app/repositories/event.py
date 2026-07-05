from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationStatus
from app.models.event import Event, EventStatus, Team
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[Event]):
    def __init__(self, session) -> None:
        super().__init__(session, Event)

    async def list_all(self) -> list[Event]:
        result = await self.session.scalars(
            select(Event).order_by(Event.created_at.desc())
        )
        return list(result.all())

    async def get_active(self) -> Event | None:
        result = await self.session.scalars(
            select(Event).where(Event.status == EventStatus.ACTIVE)
        )
        return result.first()

    async def find_by_name_prefix(self, prefix: str) -> Event | None:
        result = await self.session.scalars(
            select(Event).where(Event.name.startswith(prefix))
        )
        return result.first()


class TeamRepository(BaseRepository[Team]):
    def __init__(self, session) -> None:
        super().__init__(session, Team)

    async def get_with_members(self, team_id: int) -> Team | None:
        result = await self.session.scalars(
            select(Team)
            .where(Team.id == team_id)
            .options(selectinload(Team.members).selectinload(Application.user))
        )
        return result.first()

    async def list_for_event(self, event_id: int) -> list[Team]:
        result = await self.session.scalars(
            select(Team)
            .where(Team.event_id == event_id)
            .order_by(Team.name.asc())
            .options(selectinload(Team.members).selectinload(Application.user))
        )
        return list(result.all())

    async def find_by_name_prefix(self, event_id: int, prefix: str) -> Team | None:
        result = await self.session.scalars(
            select(Team)
            .where(Team.event_id == event_id, Team.name.startswith(prefix))
        )
        return result.first()

    async def unassigned_approved(self, limit: int = 500) -> list[Application]:
        """Approved applications not yet placed on any team — the pool for
        auto-balancing."""
        result = await self.session.scalars(
            select(Application)
            .where(
                Application.status == ApplicationStatus.APPROVED,
                Application.team_id.is_(None),
            )
            .order_by(Application.created_at.asc())
            .options(selectinload(Application.user))
            .limit(limit)
        )
        return list(result.all())
