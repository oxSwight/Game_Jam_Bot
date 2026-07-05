import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.core.i18n import normalize_lang
from app.data.layers import LAYER_COLUMNS, LAYER_NAMES
from app.keyboards.admin import reject_reason_keyboard
from app.models.application import Application, ApplicationStatus
from app.services import ServiceContainer
from app.states.admin import AdminStates
from app.utils.html import safe

logger = logging.getLogger(__name__)

QUEUE_PAGE_SIZE = 5


class IsAdminFilter(BaseFilter):
    """Passes only when AdminMiddleware has stamped is_admin=True on the event data.

    Works for both Message and CallbackQuery events — `is_admin` is injected by
    name from the handler data regardless of the event type.
    """

    async def __call__(self, event: object, is_admin: bool = False) -> bool:
        return is_admin


router = Router()
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


# --------------------------------------------------------------------------- #
# Text commands
# --------------------------------------------------------------------------- #
@router.message(Command("pending"))
async def cmd_pending(message: Message, services: ServiceContainer) -> None:
    count = await services.applications.count_pending()
    await message.answer(f"Заявок на проверке: <b>{count}</b>")


@router.message(Command("approve"))
async def cmd_approve(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /approve <id_prefix>")
        return
    await _decide_by_prefix(
        prefix=parts[1],
        status=ApplicationStatus.APPROVED,
        actor_id=message.from_user.id,
        services=services,
        reply=message.answer,
    )


@router.message(Command("reject"))
async def cmd_reject(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /reject <id_prefix>")
        return
    await _decide_by_prefix(
        prefix=parts[1],
        status=ApplicationStatus.REJECTED,
        actor_id=message.from_user.id,
        services=services,
        reply=message.answer,
    )


@router.message(Command("delete"))
async def cmd_delete(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /delete <id_prefix>")
        return

    application = await services.applications.delete_by_prefix(parts[1])
    if application is None:
        await message.answer("Заявка не найдена.")
        return
    await services.session.commit()
    await message.answer(
        f"🗑 Заявка <code>{application.id[:8]}</code> удалена "
        f"(<b>{safe(_nickname(application))}</b>)."
    )


# --------------------------------------------------------------------------- #
# Inline review buttons attached to the new-application notification
# --------------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("appr:"))
async def cb_approve(callback: CallbackQuery, services: ServiceContainer) -> None:
    await _decide_from_card(callback, ApplicationStatus.APPROVED, services)


@router.callback_query(F.data.startswith("rej:"))
async def cb_reject(callback: CallbackQuery, services: ServiceContainer) -> None:
    await _decide_from_card(callback, ApplicationStatus.REJECTED, services)


async def _decide_from_card(
    callback: CallbackQuery,
    status: ApplicationStatus,
    services: ServiceContainer,
) -> None:
    """Approve/Reject originating from a single-application notification card.

    Edits the message to strip the buttons and append the decision — this is the
    double-click guard: once decided, no other admin can act on the same card.
    """
    prefix = callback.data.split(":", 1)[1]
    application = await services.applications.find_by_prefix(prefix)

    if application is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        await _strip_keyboard(callback)
        return

    if application.status != ApplicationStatus.PENDING_REVIEW:
        await callback.answer("Заявка уже обработана другим админом.", show_alert=True)
        await _finalize_card(callback, _decision_line(application.status))
        return

    nickname = _nickname(application)
    await services.applications.update_status(
        application.id, status, actor_telegram_id=callback.from_user.id
    )
    await services.session.commit()

    await _notify_user(application, status, nickname, services)
    await _finalize_card(callback, _decision_line(status))
    await callback.answer("Готово ✅" if status == ApplicationStatus.APPROVED else "Отклонено ❌")


# --------------------------------------------------------------------------- #
# Reject with a reason (FSM: admin types free-text, it's logged + sent to user)
# --------------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("rejr:"))
async def cb_reject_reason_start(
    callback: CallbackQuery, state: FSMContext, services: ServiceContainer
) -> None:
    prefix = callback.data.split(":", 1)[1]
    application = await services.applications.find_by_prefix(prefix)
    if application is None or application.status != ApplicationStatus.PENDING_REVIEW:
        await callback.answer("Заявка уже обработана.", show_alert=True)
        await _strip_keyboard(callback)
        return
    await state.set_state(AdminStates.reject_reason)
    await state.update_data(
        reject_app_id=application.id,
        card_chat_id=callback.message.chat.id,
        card_message_id=callback.message.message_id,
    )
    await callback.message.answer(
        "📝 Введите причину отклонения (её увидит заявитель):",
        reply_markup=reject_reason_keyboard(application.id),
    )
    await callback.answer()


@router.message(Command("cancel"), AdminStates.reject_reason)
async def cancel_reject_reason(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отклонение отменено.")


@router.message(AdminStates.reject_reason)
async def process_reject_reason(
    message: Message, state: FSMContext, services: ServiceContainer
) -> None:
    reason = (message.text or "").strip()
    # Don't silently capture a slash-command as the rejection reason — the admin
    # likely meant to run it. Nudge them to type a reason or /cancel first.
    if reason.startswith("/"):
        await message.answer("Это команда. Введите причину текстом или /cancel.")
        return
    if len(reason) < 2:
        await message.answer("Причина слишком короткая. Повторите или нажмите «Без причины».")
        return
    data = await state.get_data()
    await _finalize_reject(message, state, services, data.get("reject_app_id"), reason)


@router.callback_query(AdminStates.reject_reason, F.data.startswith("rejskip:"))
async def cb_reject_skip(
    callback: CallbackQuery, state: FSMContext, services: ServiceContainer
) -> None:
    data = await state.get_data()
    await _finalize_reject(callback.message, state, services, data.get("reject_app_id"), None)
    await callback.answer("Отклонено")


@router.callback_query(F.data == "rejcancel")
async def cb_reject_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отклонение отменено.")
    await callback.answer()


async def _finalize_reject(
    message: Message,
    state: FSMContext,
    services: ServiceContainer,
    app_id: str | None,
    reason: str | None,
) -> None:
    await state.clear()
    if not app_id:
        await message.answer("Сессия устарела — заявка не найдена.")
        return
    application = await services.applications.find_by_prefix(app_id)
    if application is None or application.status != ApplicationStatus.PENDING_REVIEW:
        await message.answer("Заявка уже обработана.")
        return

    nickname = _nickname(application)
    await services.applications.update_status(
        application.id,
        ApplicationStatus.REJECTED,
        actor_telegram_id=message.chat.id,
        reason=reason,
    )
    await services.session.commit()
    await _notify_user(application, ApplicationStatus.REJECTED, nickname, services, reason=reason)

    suffix = f"\n<b>Причина:</b> {safe(reason)}" if reason else ""
    await message.answer(f"❌ Заявка <b>{safe(nickname)}</b> отклонена.{suffix}")


# --------------------------------------------------------------------------- #
# History — audit log of a single application
# --------------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("hist:"))
async def cb_history(callback: CallbackQuery, services: ServiceContainer) -> None:
    prefix = callback.data.split(":", 1)[1]
    application = await services.applications.find_by_prefix(prefix)
    if application is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    await callback.message.answer(await _render_history(application, services))
    await callback.answer()


@router.message(Command("history"))
async def cmd_history(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /history &lt;id_prefix&gt;")
        return
    application = await services.applications.find_by_prefix(parts[1])
    if application is None:
        await message.answer("Заявка не найдена.")
        return
    await message.answer(await _render_history(application, services))


async def _render_history(application: Application, services: ServiceContainer) -> str:
    logs = await services.applications.logs_for(application.id)
    lines = [
        f"🕓 <b>История заявки</b> <code>{application.id[:8]}</code> "
        f"(<b>{safe(_nickname(application))}</b>)\n"
    ]
    if not logs:
        lines.append("Событий пока нет.")
    for log in logs:
        ts = log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else "—"
        actor = f" · by {log.actor_telegram_id}" if log.actor_telegram_id else ""
        details = f" — {safe(log.details)}" if log.details else ""
        lines.append(f"• <code>{ts}</code> {safe(log.action)}{actor}{details}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# /queue — interactive, paginated list of pending applications
# --------------------------------------------------------------------------- #
@router.message(Command("queue"))
async def cmd_queue(message: Message, services: ServiceContainer) -> None:
    text, keyboard = await _render_queue_page(services, page=0)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("queue:"))
async def cb_queue_page(callback: CallbackQuery, services: ServiceContainer) -> None:
    page = int(callback.data.split(":", 1)[1])
    await _refresh_queue(callback, services, page)
    await callback.answer()


@router.callback_query(F.data.startswith("qapr:"))
async def cb_queue_approve(callback: CallbackQuery, services: ServiceContainer) -> None:
    await _decide_from_queue(callback, ApplicationStatus.APPROVED, services)


@router.callback_query(F.data.startswith("qrej:"))
async def cb_queue_reject(callback: CallbackQuery, services: ServiceContainer) -> None:
    await _decide_from_queue(callback, ApplicationStatus.REJECTED, services)


@router.callback_query(F.data.startswith("qdel:"))
async def cb_queue_delete(callback: CallbackQuery, services: ServiceContainer) -> None:
    # callback data: "qdel:<short_id>:<page>"
    _, prefix, page_str = callback.data.split(":")
    page = int(page_str)
    application = await services.applications.delete_by_prefix(prefix)
    if application is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
    else:
        await services.session.commit()
        await callback.answer(f"🗑 Удалено: {_nickname(application)}")
    await _refresh_queue(callback, services, page)


async def _decide_from_queue(
    callback: CallbackQuery,
    status: ApplicationStatus,
    services: ServiceContainer,
) -> None:
    # callback data: "qapr:<short_id>:<page>"
    _, prefix, page_str = callback.data.split(":")
    page = int(page_str)
    application = await services.applications.find_by_prefix(prefix)

    if application is None or application.status != ApplicationStatus.PENDING_REVIEW:
        await callback.answer("Заявка уже обработана.", show_alert=True)
        await _refresh_queue(callback, services, page)
        return

    nickname = _nickname(application)
    await services.applications.update_status(
        application.id, status, actor_telegram_id=callback.from_user.id
    )
    await services.session.commit()
    await _notify_user(application, status, nickname, services)

    await callback.answer(
        f"{'✅ Одобрено' if status == ApplicationStatus.APPROVED else '❌ Отклонено'}: {nickname}"
    )
    await _refresh_queue(callback, services, page)


async def _render_queue_page(services: ServiceContainer, *, page: int):
    """Build (text, keyboard) for a queue page, clamping to a valid page."""
    from app.keyboards.admin import queue_keyboard

    total = await services.applications.count_pending()
    if total == 0:
        return "✅ Очередь пуста — заявок на проверке нет.", None

    total_pages = max(1, (total + QUEUE_PAGE_SIZE - 1) // QUEUE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    offset = page * QUEUE_PAGE_SIZE

    apps = await services.applications.list_pending(limit=QUEUE_PAGE_SIZE, offset=offset)

    lines = [f"📋 <b>Очередь заявок</b> — всего: {total}\n"]
    for idx, app in enumerate(apps, start=1):
        roles = ", ".join(safe(r) for r in app.subcategories) or "—"
        lines.append(
            f"<b>#{idx}</b> {safe(_nickname(app))} "
            f"(<code>{app.id[:8]}</code>)\n"
            f"   {safe(app.skill_category_title)} · {roles}"
        )
    text = "\n".join(lines)
    keyboard = queue_keyboard(apps, page=page, total_pages=total_pages)
    return text, keyboard


async def _refresh_queue(callback: CallbackQuery, services: ServiceContainer, page: int) -> None:
    text, keyboard = await _render_queue_page(services, page=page)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        # "message is not modified" when nothing changed — safe to ignore.
        logger.debug("queue page unchanged, skipping edit")


# --------------------------------------------------------------------------- #
# /setlayer (unchanged)
# --------------------------------------------------------------------------- #
@router.message(Command("setlayer"))
async def cmd_set_layer(message: Message, services: ServiceContainer) -> None:
    parts = (message.text or "").split()
    if len(parts) < 4:
        layers_text = "\n".join(f"  {k}: {v}" for k, v in LAYER_NAMES.items())
        await message.answer(
            "Использование: /setlayer &lt;id_prefix&gt; &lt;1-5&gt; &lt;score&gt;\n\n"
            f"<b>Слои:</b>\n{layers_text}"
        )
        return

    prefix, layer_str, score_str = parts[1], parts[2], parts[3]

    try:
        layer = int(layer_str)
        score = float(score_str)
    except ValueError:
        await message.answer("Некорректные layer или score. Пример: /setlayer abc123 1 85.5")
        return

    if layer not in LAYER_COLUMNS:
        await message.answer("Layer должен быть от 1 до 5.")
        return

    if not (0.0 <= score <= 100.0):
        await message.answer(
            f"Недопустимый score <b>{score}</b>. Значение должно быть от 0.0 до 100.0."
        )
        return

    application = await services.applications.find_by_prefix(prefix)
    if not application:
        await message.answer("Заявка не найдена.")
        return

    updated = await services.applications.set_layer_score(
        application.id,
        layer,
        score,
        actor_telegram_id=message.from_user.id,
    )
    if not updated:
        await message.answer("Не удалось обновить score.")
        return

    nickname = _nickname(application)
    await message.answer(
        f"Layer {layer} (<i>{safe(LAYER_NAMES[layer])}</i>) = <b>{score}</b> "
        f"для <b>{safe(nickname)}</b>"
    )


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _nickname(application: Application) -> str:
    return (application.user.nickname if application.user else None) or "—"


def _decision_line(status: ApplicationStatus) -> str:
    label = "✅ Approved by Admin" if status == ApplicationStatus.APPROVED else "❌ Rejected by Admin"
    return f"\n\n<b>{label}</b>"


async def _decide_by_prefix(
    *,
    prefix: str,
    status: ApplicationStatus,
    actor_id: int,
    services: ServiceContainer,
    reply,
) -> None:
    application = await services.applications.find_by_prefix(prefix)
    if not application:
        await reply("Заявка не найдена.")
        return

    nickname = _nickname(application)
    await services.applications.update_status(application.id, status, actor_telegram_id=actor_id)
    await services.session.commit()
    await _notify_user(application, status, nickname, services)

    if status == ApplicationStatus.APPROVED:
        await reply(f"✅ Игрок <b>{safe(nickname)}</b> одобрен.")
    else:
        await reply(f"❌ Заявка <b>{safe(nickname)}</b> отклонена.")


async def _notify_user(
    application: Application,
    status: ApplicationStatus,
    nickname: str,
    services: ServiceContainer,
    reason: str | None = None,
) -> None:
    if not (services.notifications and application.user):
        return
    lang = normalize_lang(application.user.language)
    if status == ApplicationStatus.APPROVED:
        await services.notifications.notify_user_approved(
            application.user.telegram_id, nickname, lang=lang
        )
    else:
        await services.notifications.notify_user_rejected(
            application.user.telegram_id, reason=reason, lang=lang
        )


async def _finalize_card(callback: CallbackQuery, decision_line: str) -> None:
    """Append the decision to the card and drop the inline keyboard."""
    base = callback.message.html_text or ""
    try:
        await callback.message.edit_text(base + decision_line, reply_markup=None)
    except TelegramBadRequest:
        logger.debug("could not edit card, stripping keyboard only")
        await _strip_keyboard(callback)


async def _strip_keyboard(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
