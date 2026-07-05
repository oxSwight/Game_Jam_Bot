"""Inline keyboards for the admin dashboard (Phase 3)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Telegram callback_data is capped at 64 bytes, so we carry a short id prefix.
SHORT_ID_LEN = 8


def short_id(application_id: str) -> str:
    return application_id[:SHORT_ID_LEN]


def review_keyboard(application_id: str) -> InlineKeyboardMarkup:
    """Approve / Reject buttons attached to a new-application notification."""
    sid = short_id(application_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Approve", callback_data=f"appr:{sid}")
    builder.button(text="❌ Reject", callback_data=f"rej:{sid}")
    builder.button(text="📝 Reject + причина", callback_data=f"rejr:{sid}")
    builder.button(text="🕓 История", callback_data=f"hist:{sid}")
    builder.adjust(2, 2)
    return builder.as_markup()


def reject_reason_keyboard(application_id: str) -> InlineKeyboardMarkup:
    """Shown while waiting for a rejection reason: skip (reject without one) or
    abort the rejection entirely."""
    sid = short_id(application_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Без причины", callback_data=f"rejskip:{sid}")
    builder.button(text="✖️ Отмена", callback_data="rejcancel")
    builder.adjust(2)
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить всем", callback_data="bcast:send")
    builder.button(text="✖️ Отмена", callback_data="bcast:cancel")
    builder.adjust(2)
    return builder.as_markup()


def history_keyboard(application_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🕓 История", callback_data=f"hist:{short_id(application_id)}")
    return builder.as_markup()


def queue_keyboard(
    applications: list,
    *,
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Interactive pending-queue page: per-application actions + pagination.

    ``applications`` is the slice of pending applications shown on this page.
    Queue-originated actions carry the page so the list can be re-rendered
    in place after an approve/reject.
    """
    builder = InlineKeyboardBuilder()

    for idx, app in enumerate(applications, start=1):
        sid = short_id(app.id)
        builder.row(
            InlineKeyboardButton(text=f"✅ #{idx}", callback_data=f"qapr:{sid}:{page}"),
            InlineKeyboardButton(text=f"❌ #{idx}", callback_data=f"qrej:{sid}:{page}"),
            InlineKeyboardButton(text=f"🗑 #{idx}", callback_data=f"qdel:{sid}:{page}"),
        )

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️", callback_data=f"queue:{page - 1}")
        )
    nav_row.append(
        InlineKeyboardButton(
            text=f"· {page + 1}/{total_pages} ·",
            callback_data=f"queue:{page}",  # acts as a refresh
        )
    )
    if page + 1 < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="▶️", callback_data=f"queue:{page + 1}")
        )
    builder.row(*nav_row)
    return builder.as_markup()
