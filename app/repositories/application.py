from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationStatus
from app.models.log import Log
from app.repositories.base import BaseRepository


class ApplicationRepository(BaseRepository[Application]):
    def __init__(self, session) -> None:
        super().__init__(session, Application)

    async def get_active_for_user(self, user_id: int) -> Application | None:
        result = await self.session.scalars(
            select(Application)
            .where(
                Application.user_id == user_id,
                Application.status != ApplicationStatus.REJECTED,
            )
            .order_by(Application.created_at.desc()),
        )
        return result.first()

    async def find_by_id_prefix(self, prefix: str) -> Application | None:
        result = await self.session.scalars(
            select(Application)
            .where(Application.id.startswith(prefix))
            .options(selectinload(Application.user)),
        )
        return result.first()

    async def count_by_status(self) -> dict[str, int]:
        result = await self.session.execute(
            select(Application.status, func.count())
            .select_from(Application)
            .group_by(Application.status)
        )
        counts: dict[str, int] = {}
        for status, count in result.all():
            key = status.value if hasattr(status, "value") else str(status)
            counts[key] = int(count)
        return counts

    async def count_by_category(self) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Application.skill_category_title, func.count())
            .group_by(Application.skill_category_title)
            .order_by(func.count().desc())
        )
        return [(title, int(count)) for title, count in result.all()]

    async def count_by_experience(self) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Application.experience_level, func.count())
            .group_by(Application.experience_level)
            .order_by(func.count().desc())
        )
        return [(level, int(count)) for level, count in result.all()]

    async def list_all_with_users(self) -> list[Application]:
        result = await self.session.scalars(
            select(Application)
            .order_by(Application.created_at.asc())
            .options(selectinload(Application.user))
        )
        return list(result.all())

    async def list_by_status(self, status: ApplicationStatus) -> list[Application]:
        result = await self.session.scalars(
            select(Application)
            .where(Application.status == status)
            .order_by(Application.created_at.asc())
            .options(selectinload(Application.user))
        )
        return list(result.all())

    async def list_scored(self, limit: int) -> list[Application]:
        """Approved applications ordered by summed layer score (desc), for the
        leaderboard. Sorting happens in Python because layers are nullable and
        the 'unset = 0' rule is easier to express there than in portable SQL."""
        result = await self.session.scalars(
            select(Application)
            .where(Application.status == ApplicationStatus.APPROVED)
            .options(selectinload(Application.user))
        )
        apps = [a for a in result.all() if a.has_any_score]
        apps.sort(key=lambda a: a.total_score, reverse=True)
        return apps[:limit]

    async def logs_for(self, application_id: str) -> list[Log]:
        result = await self.session.scalars(
            select(Log)
            .where(Log.application_id == application_id)
            .order_by(Log.created_at.asc())
        )
        return list(result.all())

    async def count_pending(self) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.status == ApplicationStatus.PENDING_REVIEW),
        )
        return int(result or 0)

    async def list_pending(self, *, limit: int, offset: int) -> list[Application]:
        result = await self.session.scalars(
            select(Application)
            .where(Application.status == ApplicationStatus.PENDING_REVIEW)
            .order_by(Application.created_at.asc())
            .options(selectinload(Application.user))
            .limit(limit)
            .offset(offset),
        )
        return list(result.all())
