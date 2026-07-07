import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

from app.core.config import get_settings
from app.core.i18n import DEFAULT_LANG, t
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

    def __init__(self, bot: Bot, admin_ping_window: float = 30.0) -> None:
        self.bot = bot
        self.settings = get_settings()
        # Debounce for the per-application admin ping: at most one push per this
        # many seconds, so a burst of sign-ups can't spam admins (or trip
        # Telegram's flood limits). The queue count in each ping stays fresh, so a
        # skipped ping loses no information — the next one shows the current total.
        self._admin_ping_window = admin_ping_window
        self._last_admin_ping: float | None = None

    async def notify_admins_new_application(
        self, nickname: str, category: str, pending_count: int
    ) -> None:
        """Ping every configured admin that a new application landed in the queue.
        Best-effort and debounced; no-op when ADMIN_IDS is empty."""
        admin_ids = self.settings.admin_ids
        if not admin_ids:
            return
        now = time.monotonic()
        if self._last_admin_ping is not None and now - self._last_admin_ping < self._admin_ping_window:
            return
        self._last_admin_ping = now
        text = t(
            "admin_new_application",
            DEFAULT_LANG,
            nickname=safe(nickname) or "—",
            category=safe(category),
            count=pending_count,
        )
        for admin_id in admin_ids:
            await self._safe_send(admin_id, text)

    # ------------------------------------------------------------------ #
    # Gateway: mint a join-request invite and hand it to the approved user
    # ------------------------------------------------------------------ #
    async def send_approval_with_invite(
        self, telegram_id: int, nickname: str, lang: str = "ru"
    ) -> bool:
        """Mint a join-request invite link into the gated group and DM it to the
        approved applicant. Returns True if a link was successfully delivered,
        False if we had to fall back to a link-less approval notice."""
        # A banned user can't use ANY invite link — Telegram shows it as "expired"
        # (Истекшая ссылка). If this applicant was previously removed/kicked,
        # clear the ban first so their fresh link actually works. Best-effort.
        await self._unban_if_banned(telegram_id)
        link = await self._create_join_request_invite(nickname)
        if link is None:
            await self._safe_send(telegram_id, t("notify_approved_no_link", lang))
            return False
        # The link is bot-generated (a t.me URL) — trusted, not user input, so it
        # is interpolated verbatim and Telegram auto-links it.
        await self._safe_send(
            telegram_id, t("notify_approved", lang, nickname=safe(nickname), link=link)
        )
        return True

    async def _unban_if_banned(self, telegram_id: int) -> None:
        """Lift a prior ban on the applicant so an approval can actually let them
        in. ``only_if_banned`` makes it a no-op for anyone not currently banned,
        so it never accidentally 'unkicks' by adding them to the group."""
        if not self.settings.group_chat_id:
            return
        try:
            await self.bot.unban_chat_member(
                chat_id=self.settings.group_chat_id,
                user_id=telegram_id,
                only_if_banned=True,
            )
        except Exception:
            # Missing can_restrict_members, or a transient API error — the invite
            # is still worth sending; a genuinely-banned user just won't get in.
            logger.warning(
                "could not clear a possible ban before inviting user", exc_info=True
            )

    async def _create_join_request_invite(self, nickname: str) -> str | None:
        """Create an invite link that raises a join REQUEST instead of letting the
        holder straight in (creates_join_request=True — Telegram forbids combining
        it with member_limit). The chat_join_request handler then approves only
        users whose application is APPROVED, so a leaked/forwarded link admits
        nobody else — identity is checked at the door, not by possession of a URL.
        Returns the URL, or None if the group isn't configured or the call fails."""
        if not self.settings.group_chat_id:
            logger.error(
                "GROUP_CHAT_ID is not configured — cannot mint an invite link"
            )
            return None
        # name is an admin-facing label (max 32 chars), not shown to the user.
        name = f"gj-{nickname}"[:32]
        for attempt in (1, 2):
            try:
                result = await self.bot.create_chat_invite_link(
                    chat_id=self.settings.group_chat_id,
                    creates_join_request=True,
                    name=name,
                )
                return result.invite_link
            except TelegramRetryAfter as exc:
                if attempt == 2:
                    logger.warning(
                        "invite link mint still rate-limited after retry "
                        "(group_chat_id=%s)",
                        self.settings.group_chat_id,
                    )
                    return None
                await asyncio.sleep(exc.retry_after + 1)
            except Exception:
                logger.warning(
                    "failed to create invite link (group_chat_id=%s)",
                    self.settings.group_chat_id,
                    exc_info=True,
                )
                return None
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
