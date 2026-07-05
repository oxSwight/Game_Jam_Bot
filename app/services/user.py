from pydantic import ValidationError

from app.models.application import Application
from app.models.user import User
from app.schemas.registration import ApplicationRead
from app.services.base import BaseService


class UserService(BaseService):
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.users.get_by_telegram_id(telegram_id)

    async def get_language(self, telegram_id: int) -> str | None:
        return await self.users.get_language(telegram_id)

    async def set_language(self, telegram_id: int, language: str) -> User:
        """Persist a UI-language choice, creating the user row if needed so the
        preference survives even before they register an application."""
        user = await self.users.get_or_create(telegram_id=telegram_id)
        user.language = language
        await self.session.flush()
        return user

    async def get_profile(self, telegram_id: int) -> ApplicationRead | None:
        user = await self.users.get_by_telegram_id(telegram_id)
        if not user:
            return None
        application = await self.applications.get_active_for_user(user.id)
        if not application:
            return None
        return self._to_read(user, application)

    @staticmethod
    def _to_read(user: User, application: Application) -> ApplicationRead:
        return ApplicationRead(
            id=application.id,
            status=application.status.value,
            nickname=user.nickname,
            email=user.email,
            main_category=application.main_category,
            skill_category_title=application.skill_category_title,
            subcategories=application.subcategories,
            experience_level=application.experience_level,
            engine=application.engine,
            engine_other=application.engine_other,
            tools=application.tools,
            tools_other=application.tools_other,
            motivations=application.motivations,
            telegram_id=user.telegram_id,
            telegram_username=user.telegram_username,
        )

    def format_validation_error(self, error: ValidationError) -> str:
        messages = []
        for item in error.errors():
            loc = item.get("loc", ())
            field = loc[-1] if loc else "value"
            messages.append(f"{field}: {item.get('msg', 'invalid')}")
        return "; ".join(messages)
