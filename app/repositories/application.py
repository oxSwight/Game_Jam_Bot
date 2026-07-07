from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationStatus
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
        """Look up an application by (a prefix of) its id. Returns None when the
        prefix is ambiguous — acting on 'whichever matched first' could hand an
        admin decision to the wrong application."""
        if not prefix:
            return None
        result = await self.session.scalars(
            select(Application)
            .where(Application.id.startswith(prefix))
            .options(selectinload(Application.user))
            .limit(2),
        )
        matches = list(result.all())
        if len(matches) != 1:
            return None
        return matches[0]

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

    async def max_player_code_in_block(self, base: int, block: int) -> int | None:
        """Highest player_code already assigned in a category's [base, base+block)
        window — the seed for the next code in that discipline."""
        return await self.session.scalar(
            select(func.max(Application.player_code)).where(
                Application.player_code >= base,
                Application.player_code < base + block,
            )
        )

    async def count_pending(self) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.status == ApplicationStatus.PENDING_REVIEW),
        )
        return int(result or 0)

    async def first_pending(self) -> Application | None:
        """The oldest application still awaiting review — the head of the FIFO
        review queue that /review walks through one card at a time."""
        result = await self.session.scalars(
            select(Application)
            .where(Application.status == ApplicationStatus.PENDING_REVIEW)
            .order_by(Application.created_at.asc())
            .options(selectinload(Application.user))
            .limit(1),
        )
        return result.first()
