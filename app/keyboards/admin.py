"""Inline keyboards for the admin review dashboard."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Telegram callback_data is capped at 64 bytes, so we carry a short id prefix.
SHORT_ID_LEN = 8


def short_id(application_id: str) -> str:
    return application_id[:SHORT_ID_LEN]


def review_keyboard(application_id: str) -> InlineKeyboardMarkup:
    """Approve / Reject buttons under the single /review card. Acting on a card
    performs the decision and swaps the card for the next pending application."""
    sid = short_id(application_id)
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"rev:approve:{sid}")
    builder.button(text="❌ Отклонить", callback_data=f"rev:reject:{sid}")
    builder.adjust(2)
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить всем", callback_data="bcast:send")
    builder.button(text="Отмена", callback_data="bcast:cancel")
    builder.adjust(2)
    return builder.as_markup()
