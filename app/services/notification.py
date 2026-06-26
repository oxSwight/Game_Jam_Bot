import logging

from aiogram import Bot

from app.core.config import get_settings
from app.keyboards.admin import review_keyboard
from app.schemas.registration import ApplicationRead
from app.utils.html import join_with_other, safe

logger = logging.getLogger(__name__)


def render_application_card(application: ApplicationRead) -> str:
    """Formatted, HTML-safe card for an application — shared by the new-application
    notification and the admin queue so both stay visually consistent."""
    return (
        "🆕 <b>Новая заявка на регистрацию</b>\n\n"
        f"ID: <code>{application.id}</code>\n"
        f"Telegram: @{safe(application.telegram_username) or '—'} ({application.telegram_id})\n"
        f"Ник: {safe(application.nickname)}\n"
        f"Email: {safe(application.email)}\n"
        f"Категория: {safe(application.skill_category_title)}\n"
        f"Роли: {', '.join(safe(s) for s in application.subcategories)}\n"
        f"Опыт: {safe(application.experience_level)}\n"
        f"Движок: {join_with_other(application.engine, application.engine_other)}\n"
        f"Инструменты: {join_with_other(application.tools, application.tools_other)}\n"
        f"Мотивация: {', '.join(safe(m) for m in application.motivations)}"
    )


class NotificationService:
    """Telegram-side notifications — keeps handlers free of message formatting."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()

    async def notify_admins_new_application(self, application: ApplicationRead) -> None:
        if not self.settings.admin_ids:
            logger.warning(
                "no ADMIN_IDS configured — cannot notify anyone about application %s",
                application.id,
            )
            return

        logger.debug(
            "notifying %d admin(s) %s about application %s",
            len(self.settings.admin_ids),
            self.settings.admin_ids,
            application.id,
        )

        text = render_application_card(application)
        keyboard = review_keyboard(application.id)

        for admin_id in self.settings.admin_ids:
            try:
                await self.bot.send_message(admin_id, text, reply_markup=keyboard)
                logger.debug("notified admin %s about application %s", admin_id, application.id)
            except Exception:
                logger.warning(
                    "failed to notify admin %s about application %s",
                    admin_id,
                    application.id,
                    exc_info=True,
                )

    async def notify_user_approved(self, telegram_id: int, nickname: str) -> None:
        await self._safe_send(
            telegram_id,
            f"🎉 Ваша заявка одобрена!\n\nДобро пожаловать на платформу, <b>{safe(nickname)}</b>!",
        )

    async def notify_user_rejected(self, telegram_id: int) -> None:
        await self._safe_send(
            telegram_id,
            "Ваша заявка не прошла проверку. Вы можете подать новую через /register",
        )

    async def _safe_send(self, chat_id: int, text: str) -> None:
        try:
            await self.bot.send_message(chat_id, text)
        except Exception:
            logger.warning(
                "failed to send notification to chat_id=%s",
                chat_id,
                exc_info=True,
            )
