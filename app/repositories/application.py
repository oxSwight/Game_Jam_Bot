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
        result = await self.session.scalars(
            select(Application)
            .where(Application.id.startswith(prefix))
            .options(selectinload(Application.user)),
        )
        return result.first()

    async def count_pending(self) -> int:
        result = await self.session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.status == ApplicationStatus.PENDING_REVIEW),
        )
        return int(result or 0)
