from app.data.layers import LAYER_COLUMNS
from app.models.application import Application, ApplicationStatus
from app.models.log import Log
from app.schemas.registration import ApplicationRead, RegistrationCreate
from app.services.base import BaseService
from app.services.user import UserService


class ActiveApplicationExistsError(Exception):
    pass


class ApplicationService(BaseService):
    async def has_active_application(self, telegram_id: int) -> bool:
        user = await self.users.get_by_telegram_id(telegram_id)
        if not user:
            return False
        application = await self.applications.get_active_for_user(user.id)
        return application is not None

    async def submit_registration(self, payload: RegistrationCreate) -> ApplicationRead:
        user = await self.users.get_or_create(
            telegram_id=payload.identity.telegram_id,
            telegram_username=payload.identity.telegram_username,
        )

        active = await self.applications.get_active_for_user(user.id)
        if active and active.status != ApplicationStatus.REJECTED:
            raise ActiveApplicationExistsError()

        user.nickname = payload.nickname
        user.email = str(payload.email)

        application = Application(
            user_id=user.id,
            main_category=payload.main_category,
            blueprint_subcategory=payload.blueprint_subcategory,
            skill_category_id=payload.skill_category_id,
            skill_category_title=payload.skill_category_title,
            subcategories=payload.subcategories,
            experience_level=payload.experience_level,
            tools=payload.tools,
            tools_other=payload.tools_other,
            motivations=payload.motivations,
            consent_accepted=payload.consent_accepted,
            status=ApplicationStatus.PENDING_REVIEW,
        )
        await self.applications.add(application)

        self.session.add(
            Log(
                application_id=application.id,
                actor_telegram_id=payload.identity.telegram_id,
                action="application_submitted",
                details=f"status={ApplicationStatus.PENDING_REVIEW.value}",
            ),
        )
        await self.session.flush()

        return UserService._to_read(user, application)

    async def update_status(
        self,
        application_id: str,
        status: ApplicationStatus,
        actor_telegram_id: int | None = None,
    ) -> Application | None:
        application = await self.applications.get_by_id(application_id)
        if not application:
            return None
        application.status = status
        self.session.add(
            Log(
                application_id=application.id,
                actor_telegram_id=actor_telegram_id,
                action=f"status_{status.value}",
            ),
        )
        await self.session.flush()
        return application

    async def count_pending(self) -> int:
        return await self.applications.count_pending()

    async def find_by_prefix(self, prefix: str) -> Application | None:
        return await self.applications.find_by_id_prefix(prefix)

    async def set_layer_score(
        self,
        application_id: str,
        layer: int,
        score: float,
        actor_telegram_id: int | None = None,
    ) -> Application | None:
        application = await self.applications.get_by_id(application_id)
        if not application:
            return None
        column = LAYER_COLUMNS[layer]
        setattr(application, column, score)
        self.session.add(
            Log(
                application_id=application.id,
                actor_telegram_id=actor_telegram_id,
                action=f"layer_{layer}_set",
                details=f"score={score}",
            ),
        )
        await self.session.flush()
        return application
