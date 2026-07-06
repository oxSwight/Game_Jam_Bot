from app.data.catalog import PLAYER_CODE_WIDTH, category_code_base
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

        player_code = await self._next_player_code(payload.main_category)

        application = Application(
            user_id=user.id,
            player_code=player_code,
            # Snapshot the contact details onto the row itself (see model note).
            nickname=payload.nickname,
            email=str(payload.email),
            main_category=payload.main_category,
            blueprint_subcategory=payload.blueprint_subcategory,
            skill_category_id=payload.skill_category_id,
            skill_category_title=payload.skill_category_title,
            subcategories=payload.subcategories,
            experience_level=payload.experience_level,
            engine=payload.engine,
            engine_other=payload.engine_other,
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

    async def _next_player_code(self, category_id: str) -> int:
        """Assign the next category-coded public id (e.g. 10007). Single polling
        instance means this max()+1 is race-free enough; the unique index is the
        backstop."""
        base = category_code_base(category_id)
        block = 10 ** PLAYER_CODE_WIDTH
        current = await self.applications.max_player_code_in_block(base, block)
        return (current or base) + 1

    async def update_status(
        self,
        application_id: str,
        status: ApplicationStatus,
        actor_telegram_id: int | None = None,
        reason: str | None = None,
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
                details=(f"reason={reason}" if reason else None),
            ),
        )
        await self.session.flush()
        return application

    async def count_by_status(self) -> dict[str, int]:
        return await self.applications.count_by_status()

    async def count_by_category(self) -> list[tuple[str, int]]:
        return await self.applications.count_by_category()

    async def count_by_experience(self) -> list[tuple[str, int]]:
        return await self.applications.count_by_experience()

    async def list_all_with_users(self) -> list[Application]:
        return await self.applications.list_all_with_users()

    async def list_approved(self) -> list[Application]:
        return await self.applications.list_by_status(ApplicationStatus.APPROVED)

    async def update_contact(
        self,
        telegram_id: int,
        *,
        nickname: str | None = None,
        email: str | None = None,
    ) -> bool:
        """Update the caller's nickname and/or email on their own active
        application's user record. Returns False if they have no active
        application. Raises IntegrityError upward on unique-constraint clashes."""
        user = await self.users.get_by_telegram_id(telegram_id)
        if not user:
            return False
        application = await self.applications.get_active_for_user(user.id)
        if not application:
            return False
        if nickname is not None:
            user.nickname = nickname
            application.nickname = nickname  # keep the row's snapshot in sync
        if email is not None:
            user.email = email
            application.email = email
        self.session.add(
            Log(
                application_id=application.id,
                actor_telegram_id=telegram_id,
                action="contact_updated",
                details=f"nickname={nickname or '-'} email={email or '-'}",
            ),
        )
        await self.session.flush()
        return True

    async def update_profile(
        self, telegram_id: int, payload: RegistrationCreate
    ) -> bool:
        """Overwrite the skill/category fields of the caller's active application
        in place — lets a player refine their roles, experience, engine, tools and
        motivation over time WITHOUT losing their (possibly approved) status or
        creating a new row. Nickname/email are managed separately via update_contact.
        Returns False if they have no active application."""
        user = await self.users.get_by_telegram_id(telegram_id)
        if not user:
            return False
        application = await self.applications.get_active_for_user(user.id)
        if not application:
            return False

        # If the discipline changed, the player_code's category prefix would go
        # stale, so re-issue it into the new category's block (also covers legacy
        # rows that never got a code). The old number is simply retired.
        category_changed = application.main_category != payload.main_category
        old_code = application.player_code
        if category_changed or application.player_code is None:
            application.player_code = await self._next_player_code(payload.main_category)

        application.main_category = payload.main_category
        application.blueprint_subcategory = payload.blueprint_subcategory
        application.skill_category_id = payload.skill_category_id
        application.skill_category_title = payload.skill_category_title
        application.subcategories = payload.subcategories
        application.experience_level = payload.experience_level
        application.engine = payload.engine
        application.engine_other = payload.engine_other
        application.tools = payload.tools
        application.tools_other = payload.tools_other
        application.motivations = payload.motivations

        self.session.add(
            Log(
                application_id=application.id,
                actor_telegram_id=telegram_id,
                action="profile_updated",
                details=f"category={payload.main_category} roles={len(payload.subcategories)}",
            ),
        )
        if application.player_code != old_code:
            self.session.add(
                Log(
                    application_id=application.id,
                    actor_telegram_id=telegram_id,
                    action="player_code_reassigned",
                    details=f"{old_code} -> {application.player_code}",
                ),
            )
        await self.session.flush()
        return True

    async def count_pending(self) -> int:
        return await self.applications.count_pending()

    async def first_pending(self) -> Application | None:
        return await self.applications.first_pending()

    async def find_by_prefix(self, prefix: str) -> Application | None:
        return await self.applications.find_by_id_prefix(prefix)

    async def withdraw_active(self, telegram_id: int) -> bool:
        """Hard-delete the caller's own active (non-rejected) application so they
        can register again. Used for self-service reset / cleaning up test data."""
        user = await self.users.get_by_telegram_id(telegram_id)
        if not user:
            return False
        application = await self.applications.get_active_for_user(user.id)
        if not application:
            return False
        await self.applications.delete(application)
        await self.session.flush()
        return True
