"""Last-resort handler for inline taps that no other router claimed.

Registered LAST in the dispatcher, so aiogram only routes an update here when the
registration/admin/membership routers all passed on it — e.g. a button tap on an
old message after the FSM state moved on, or an "Отправить заявку" tap on a confirm
screen whose session was reset. Without this the tap logs "Update is not handled"
and vanishes with zero feedback, leaving the user convinced their action worked.
"""

import logging

from aiogram import Router
from aiogram.types import CallbackQuery

from app.core.i18n import t

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query()
async def stale_callback(callback: CallbackQuery, lang: str = "ru") -> None:
    # DEBUG: telegram_id (and potentially forged callback data) is PII-adjacent
    # diagnostic detail - keep it out of routine INFO logs.
    logger.debug(
        "unhandled callback -> stale-button notice",
        extra={"extra_fields": {
            "telegram_id": callback.from_user.id,
            "data": callback.data,
        }},
    )
    notice = t("reg_session_expired", lang)
    # Clear the button's loading spinner, then tell them what to do. If the source
    # message is gone (very old tap), fall back to the popup alert.
    if callback.message is not None:
        await callback.answer()
        await callback.message.answer(notice)
    else:
        await callback.answer(notice, show_alert=True)
