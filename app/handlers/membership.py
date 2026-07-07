"""Group membership tracking.

The bot is an admin of the gated group, so Telegram delivers a ``chat_member``
update whenever someone's membership there changes. We use it to keep each
player's ``is_active`` flag in sync — False when they leave/are kicked, True when
they (re)join — and to greet a returning player we already remember with a DM.
"""

import logging

from aiogram import Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatJoinRequest, ChatMemberUpdated

from app.core.config import get_settings
from app.core.i18n import normalize_lang
from app.services import ServiceContainer

logger = logging.getLogger(__name__)

router = Router()

_MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


def _is_member(chat_member) -> bool:
    """True if this ChatMember represents someone currently in the group.
    RESTRICTED members carry an ``is_member`` flag; left/kicked are never in."""
    status = chat_member.status
    if status in _MEMBER_STATUSES:
        return True
    if status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(chat_member, "is_member", False))
    return False


@router.chat_join_request()
async def on_join_request(event: ChatJoinRequest, services: ServiceContainer) -> None:
    """The identity check at the door. Invite links are minted with
    creates_join_request=True, so following one only files a REQUEST; here we
    approve it iff the requester's own application is APPROVED. A leaked or
    forwarded link therefore admits nobody but the person it was issued for."""
    settings = get_settings()
    if settings.group_chat_id is None or event.chat.id != settings.group_chat_id:
        return

    approved = await services.applications.has_approved_application(event.from_user.id)
    try:
        if approved:
            await event.approve()
        else:
            await event.decline()
    except Exception:
        # Request already handled by a human admin, expired, or a flood limit —
        # nothing to recover; the user can simply follow the link again.
        logger.warning("could not settle join request", exc_info=True)
        return
    logger.info("join request %s", "approved" if approved else "declined")


@router.chat_member()
async def on_group_membership_change(
    event: ChatMemberUpdated, services: ServiceContainer
) -> None:
    settings = get_settings()
    # Only care about the one gated group.
    if settings.group_chat_id is None or event.chat.id != settings.group_chat_id:
        return

    affected = event.new_chat_member.user
    if affected is None or affected.is_bot:
        return

    now_member = _is_member(event.new_chat_member)
    was_member = _is_member(event.old_chat_member)

    # Only touch players we already know — we don't create rows for random joiners.
    user = await services.users.set_active(affected.id, now_member)
    await services.session.commit()
    if user is None:
        logger.debug("membership change for unknown user %s — ignored", affected.id)
        return

    # Log the internal row id, not the Telegram id — keeps PII out of the logs.
    logger.info(
        "membership change: user_id=%s is_active=%s (%s -> %s)",
        user.id,
        now_member,
        event.old_chat_member.status,
        event.new_chat_member.status,
    )

    # Fresh (re)join of a remembered player → welcome them back by DM.
    if now_member and not was_member and services.notifications:
        lang = normalize_lang(user.language)
        await services.notifications.notify_welcome_back(
            affected.id, user.nickname or "", lang=lang
        )
