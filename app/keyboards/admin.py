"""Inline keyboards for the admin review dashboard."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def review_keyboard(application_id: str) -> InlineKeyboardMarkup:
    """Approve / Reject buttons under the single /review card. Acting on a card
    performs the decision and swaps the card for the next pending application.

    The full 36-char UUID fits Telegram's 64-byte callback_data cap alongside the
    "rev:approve:" prefix (48 bytes total), so no truncated-prefix lookups - and
    no chance of a prefix collision routing a decision to the wrong application.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"rev:approve:{application_id}")
    builder.button(text="❌ Отклонить", callback_data=f"rev:reject:{application_id}")
    builder.adjust(2)
    return builder.as_markup()


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Отправить всем", callback_data="bcast:send")
    builder.button(text="Отмена", callback_data="bcast:cancel")
    builder.adjust(2)
    return builder.as_markup()
