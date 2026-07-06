import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from app.core.config import get_settings
from app.core.i18n import t
from app.data.catalog import EXPERIENCE_LEVELS
from app.schemas.registration import ApplicationRead
from app.utils.html import join_with_other, safe

logger = logging.getLogger(__name__)


def render_application_card(application: ApplicationRead) -> str:
    """Formatted, HTML-safe card for a single application — shown by the /review
    dashboard, one application at a time."""
    experience = EXPERIENCE_LEVELS.get(
        application.experience_level, application.experience_level
    )
    return (
        f"ID игрока: <code>{application.player_code or '-'}</code>\n"
        f"Telegram: @{safe(application.telegram_username) or '-'} ({application.telegram_id})\n"
        f"Ник: {safe(application.nickname)}\n"
        f"Email: {safe(application.email)}\n"
        f"Категория: {safe(application.skill_category_title)}\n"
        f"Роли: {', '.join(safe(s) for s in application.subcategories)}\n"
        f"Опыт: {safe(experience)}\n"
        f"Движок: {join_with_other(application.engine, application.engine_other)}\n"
        f"Инструменты: {join_with_other(application.tools, application.tools_other)}\n"
        f"Мотивация: {', '.join(safe(m) for m in application.motivations)}"
    )


class NotificationService:
    """Telegram-side notifications and invite-link minting — keeps handlers free
    of message formatting and Bot-API calls."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.settings = get_settings()

    # ------------------------------------------------------------------ #
    # Gateway: mint a single-use invite and hand it to the approved user
    # ------------------------------------------------------------------ #
    async def send_approval_with_invite(
        self, telegram_id: int, nickname: str, lang: str = "ru"
    ) -> bool:
        """Mint a one-join invite link into the gated group and DM it to the
        approved applicant. Returns True if a link was successfully delivered,
        False if we had to fall back to a link-less approval notice."""
        link = await self._create_single_use_invite(nickname)
        if link is None:
            await self._safe_send(telegram_id, t("notify_approved_no_link", lang))
            return False
        # The link is bot-generated (a t.me URL) — trusted, not user input, so it
        # is interpolated verbatim and Telegram auto-links it.
        await self._safe_send(
            telegram_id, t("notify_approved", lang, nickname=safe(nickname), link=link)
        )
        return True

    async def _create_single_use_invite(self, nickname: str) -> str | None:
        """Create an invite link limited to a single join (member_limit=1). Returns
        the URL, or None if the group isn't configured or the API call fails."""
        if not self.settings.group_chat_id:
            logger.error(
                "GROUP_CHAT_ID is not configured — cannot mint an invite link"
            )
            return None
        try:
            # name is an admin-facing label (max 32 chars), not shown to the user.
            name = f"gj-{nickname}"[:32]
            result = await self.bot.create_chat_invite_link(
                chat_id=self.settings.group_chat_id,
                member_limit=1,
                name=name,
            )
            return result.invite_link
        except Exception:
            logger.warning(
                "failed to create single-use invite link (group_chat_id=%s)",
                self.settings.group_chat_id,
                exc_info=True,
            )
            return None

    async def notify_welcome_back(
        self, telegram_id: int, nickname: str, lang: str = "ru"
    ) -> None:
        await self._safe_send(
            telegram_id, t("welcome_back_group", lang, nickname=safe(nickname))
        )

    async def notify_user_rejected(
        self, telegram_id: int, reason: str | None = None, lang: str = "ru"
    ) -> None:
        if reason:
            text = t("notify_rejected_reason", lang, reason=safe(reason))
        else:
            text = t("notify_rejected", lang)
        await self._safe_send(telegram_id, text)

    async def broadcast(self, recipients: list[int], text: str) -> tuple[int, int]:
        """Send ``text`` to each recipient, respecting Telegram flood limits.

        Returns (sent, failed). Paces sends to stay under the ~30 msg/s global
        limit and honours ``TelegramRetryAfter`` back-off so a large broadcast
        doesn't get the bot rate-limited."""
        sent = failed = 0
        for chat_id in recipients:
            ok = await self._safe_send_once(chat_id, text)
            if ok:
                sent += 1
            else:
                failed += 1
            await asyncio.sleep(0.05)  # ~20 msg/s, comfortably under the limit
        return sent, failed

    async def _safe_send_once(self, chat_id: int, text: str) -> bool:
        try:
            await self.bot.send_message(chat_id, text)
            return True
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await self.bot.send_message(chat_id, text)
                return True
            except Exception:
                logger.warning("broadcast retry failed for chat_id=%s", chat_id, exc_info=True)
                return False
        except Exception:
            logger.warning("broadcast failed for chat_id=%s", chat_id, exc_info=True)
            return False

    async def _safe_send(self, chat_id: int, text: str) -> None:
        try:
            await self.bot.send_message(chat_id, text)
        except Exception:
            logger.warning(
                "failed to send notification to chat_id=%s",
                chat_id,
                exc_info=True,
            )
