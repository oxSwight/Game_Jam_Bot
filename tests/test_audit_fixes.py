"""Regression tests for the security-audit fixes.

- H2: a stale "Back" tap (nav:back_roles) with empty FSM data must reset the
  session and answer with guidance, not KeyError into the global error handler.
  (The new per-state filters are routing-level; this pins the in-handler guard.)
- M3: /review must ignore an unknown rev:* action - previously anything that
  wasn't "approve" fell into the reject branch.
- M4: set_language must refuse to persist a forged/unsupported language code.
- M5: the edit prompts must advertise /cancel so the step isn't a hidden dead end.
"""

from app.core.i18n import t
from app.handlers import admin as admin_h
from app.handlers import registration as reg_h
from app.models.application import ApplicationStatus
from tests.test_handlers_fsm import (
    FakeCallback,
    FakeNotifications,
    _submit,
    make_state,
)


# ------------------------- H2: stale nav guard -------------------------- #
async def test_stale_nav_back_roles_resets_session():
    state = make_state(999)  # cleared session: no state, no data
    cb = FakeCallback("nav:back_roles")
    await reg_h.nav_back_roles(cb, state)  # must not raise
    assert await state.get_state() is None
    # answered with the session-expired guidance (mentions /register)
    assert any(text and "register" in text.lower() for text in cb.answered)


# --------------------- M3: /review unknown action ----------------------- #
async def test_review_unknown_action_is_ignored(services, session):
    a = await _submit(services, session, telegram_id=501, nickname="P1", email="p1@x.com")
    services.notifications = FakeNotifications()

    cb = FakeCallback(f"rev:skip:{a.id[:8]}", user_id=111)
    await admin_h.cb_review_decision(cb, services)

    reloaded = await services.applications.find_by_prefix(a.id[:8])
    assert reloaded.status == ApplicationStatus.PENDING_REVIEW  # untouched
    assert not services.notifications.approved
    assert not services.notifications.rejected


# --------------------- M4: language code whitelist ---------------------- #
async def test_set_language_rejects_unknown_code(services):
    cb = FakeCallback("lang:xx", user_id=777)
    await reg_h.set_language(cb, services)
    assert await services.users.get_language(777) is None


async def test_set_language_accepts_supported_code(services):
    cb = FakeCallback("lang:en", user_id=778)
    await reg_h.set_language(cb, services)
    assert await services.users.get_language(778) == "en"


# ------------------- M5: edit prompts advertise /cancel ------------------ #
def test_edit_prompts_advertise_cancel():
    for key in ("edit_enter_nickname", "edit_enter_email"):
        for lang in ("ru", "en"):
            assert "/cancel" in t(key, lang)
