"""Admin review dashboard.

A single /review card walks the pending queue one application at a time. Acting
on it (approve/reject) performs the decision - minting a personal join-request
group invite on approval - then edits the same message to show the next
application, so admins never get one push per sign-up (which would blow
Telegram's rate limits).
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, Message

from app.core.i18n import normalize_lang
from app.keyboards.admin import review_keyboard
from app.models.application import Application, ApplicationStatus
from app.schemas.registration import ApplicationRead
from app.services import ServiceContainer
from app.services.notification import render_application_card
from app.services.user import UserService

logger = logging.getLogger(__name__)


class IsAdminFilter(BaseFilter):
    """Passes only when AdminMiddleware has stamped is_admin=True on the event data.

    Works for both Message and CallbackQuery events - `is_admin` is injected by
    name from the handler data regardless of the event type.
    """

    async def __call__(self, event: object, is_admin: bool = False) -> bool:
        return is_admin


router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


# --------------------------------------------------------------------------- #
# /review - one card at a time, swipe-through queue
# --------------------------------------------------------------------------- #
@router.message(Command("review"))
async def cmd_review(message: Message, services: ServiceContainer) -> None:
    text, keyboard = await _render_review(services)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("rev:"))
async def cb_review_decision(callback: CallbackQuery, services: ServiceContainer) -> None:
    # callback data: "rev:<approve|reject>:<application_id>" (full UUID; old
    # cards may still carry an 8-char prefix - find_by_prefix handles both)
    try:
        _, action, prefix = callback.data.split(":", 2)
    except ValueError:
        await callback.answer()
        return
    # Whitelist the action BEFORE any DB work: an unknown/forged "rev:*" payload
    # must be ignored, not fall through to the reject branch and silently
    # decline a real person's application.
    if action not in ("approve", "reject"):
        await callback.answer()
        return

    application = await services.applications.find_by_prefix(prefix)
    if application is None or application.status != ApplicationStatus.PENDING_REVIEW:
        # Already handled (e.g. by another admin) - just advance to the next card.
        await callback.answer("Заявка уже обработана.")
        await _refresh_review(callback, services)
        return

    nickname = _nickname(application)
    if action == "approve":
        toast = await _approve(application, nickname, services, callback.from_user.id)
    else:
        toast = await _reject(application, nickname, services, callback.from_user.id)

    await callback.answer(toast)
    await _refresh_review(callback, services)


async def _approve(
    application: Application,
    nickname: str,
    services: ServiceContainer,
    actor_id: int,
) -> str:
    # Capture what the notification needs before committing/expiring anything.
    user = application.user
    telegram_id = user.telegram_id if user else None
    lang = normalize_lang(user.language if user else None)

    # Conditional transition: only wins if the row is still pending. Two admins
    # racing on the same card → exactly one approval, exactly one invite.
    updated = await services.applications.update_status(
        application.id,
        ApplicationStatus.APPROVED,
        actor_telegram_id=actor_id,
        expected_status=ApplicationStatus.PENDING_REVIEW,
    )
    if updated is None:
        return "Заявка уже обработана."
    await services.session.commit()

    if not (services.notifications and telegram_id):
        return f"Одобрено: {nickname} (уведомление не отправлено)"

    invited = await services.notifications.send_approval_with_invite(
        telegram_id, nickname, lang=lang
    )
    if invited:
        return f"Одобрено, ссылка выдана: {nickname}"
    return f"Одобрено: {nickname} (ссылку выдать не удалось)"


async def _reject(
    application: Application,
    nickname: str,
    services: ServiceContainer,
    actor_id: int,
) -> str:
    user = application.user
    telegram_id = user.telegram_id if user else None
    lang = normalize_lang(user.language if user else None)

    updated = await services.applications.update_status(
        application.id,
        ApplicationStatus.REJECTED,
        actor_telegram_id=actor_id,
        expected_status=ApplicationStatus.PENDING_REVIEW,
    )
    if updated is None:
        return "Заявка уже обработана."
    await services.session.commit()

    if services.notifications and telegram_id:
        await services.notifications.notify_user_rejected(telegram_id, lang=lang)
    return f"Отклонено: {nickname}"


async def _render_review(services: ServiceContainer) -> tuple[str, object | None]:
    """Build (text, keyboard) for the head of the pending queue, or an
    empty-queue message with no keyboard."""
    application = await services.applications.first_pending()
    if application is None:
        return "Очередь пуста - заявок на проверке нет.", None

    remaining = await services.applications.count_pending()
    card = render_application_card(_to_read(application))
    text = f"<b>Очередь · осталось {remaining}</b>\n\n{card}"
    return text, review_keyboard(application.id)


async def _refresh_review(callback: CallbackQuery, services: ServiceContainer) -> None:
    text, keyboard = await _render_review(services)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        # "message is not modified" when nothing changed - safe to ignore.
        logger.debug("review card unchanged, skipping edit")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _nickname(application: Application) -> str:
    return (application.user.nickname if application.user else None) or "-"


def _to_read(application: Application) -> ApplicationRead:
    return UserService._to_read(application.user, application)
