from app.models.event import Event, EventStatus, Team
from app.models.log import Log
from app.services.base import BaseService


class EventError(Exception):
    """User-facing event/team operation error (message is safe to show)."""


class EventService(BaseService):
    async def create_event(self, name: str) -> Event:
        name = name.strip()
        if len(name) < 2:
            raise EventError("Название события слишком короткое.")
        existing = await self.events.find_by_name_prefix(name)
        if existing and existing.name == name:
            raise EventError("Событие с таким названием уже существует.")
        event = Event(name=name)
        await self.events.add(event)
        return event

    async def list_events(self) -> list[Event]:
        return await self.events.list_all()

    async def set_status(self, event: Event, status: EventStatus) -> Event:
        # Only one active event at a time keeps the leaderboard unambiguous.
        if status == EventStatus.ACTIVE:
            current = await self.events.get_active()
            if current and current.id != event.id:
                current.status = EventStatus.FINISHED
        event.status = status
        await self.session.flush()
        return event

    async def create_team(self, event: Event, name: str) -> Team:
        name = name.strip()
        if len(name) < 2:
            raise EventError("Название команды слишком короткое.")
        existing = await self.teams.find_by_name_prefix(event.id, name)
        if existing and existing.name == name:
            raise EventError("Команда с таким названием уже есть в этом событии.")
        team = Team(event_id=event.id, name=name)
        await self.teams.add(team)
        return team

    async def assign_member(self, application, team: Team) -> None:
        application.team_id = team.id
        self.session.add(
            Log(
                application_id=application.id,
                action="team_assigned",
                details=f"team={team.name}",
            )
        )
        await self.session.flush()

    async def auto_balance(self, event: Event) -> tuple[int, int]:
        """Round-robin distribute unassigned approved applicants across the
        event's teams. Returns (assigned_count, team_count). Requires at least
        one team to exist."""
        teams = await self.teams.list_for_event(event.id)
        if not teams:
            raise EventError("Сначала создайте хотя бы одну команду в событии.")
        pool = await self.teams.unassigned_approved()
        if not pool:
            return (0, len(teams))

        # Seed the round-robin cursor from current team sizes so repeated runs
        # keep teams balanced rather than always starting from team #1.
        sizes = [len(t.members) for t in teams]
        assigned = 0
        for application in pool:
            idx = min(range(len(teams)), key=lambda i: sizes[i])
            team = teams[idx]
            application.team_id = team.id
            sizes[idx] += 1
            assigned += 1
            self.session.add(
                Log(
                    application_id=application.id,
                    action="team_assigned",
                    details=f"team={team.name} (auto)",
                )
            )
        await self.session.flush()
        return (assigned, len(teams))
