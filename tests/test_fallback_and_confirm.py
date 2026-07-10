"""Safety net for the 'I registered but /status is empty' class of report:
- the confirm screen must loudly say nothing is submitted until the button is pressed
- an inline tap no router claims (stale button / reset session) must never vanish
  silently — the fallback router answers it with a next step.
"""

from app.handlers import fallback as fb
from app.handlers import registration as reg_h
from app.states.registration import RegistrationStates
from tests.test_handlers_fsm import FakeCallback, make_state


# ------------------------ confirm-screen warning ------------------------ #
def _full_data(**over):
    data = {
        "nickname": "Neo", "email": "neo@x.com",
        "category_id": "programming", "category_title": "Programming / Engineering",
        "roles": ["programmer"], "experience_level": "beginner",
        "engine": ["Unity"], "tools": ["Blender"], "motivations": ["Learning"],
        "strengths": [],
    }
    data.update(over)
    return data


def test_confirm_text_warns_not_submitted():
    text = reg_h._confirm_text(_full_data(), "ru", 111)
    assert "НЕ отправлена" in text
    assert "Отправить заявку" in text


def test_confirm_text_edit_mode_warns_not_saved():
    text = reg_h._confirm_text(_full_data(edit_mode=True), "ru", 111)
    assert "НЕ сохранены" in text


def test_confirm_text_english():
    text = reg_h._confirm_text(_full_data(), "en", 111)
    assert "NOT submitted" in text


async def test_motivation_done_renders_warning_card():
    state = make_state(111)
    await state.set_state(RegistrationStates.motivation)
    await state.update_data(**_full_data())
    cb = FakeCallback("mot:done")
    await reg_h.toggle_motivation(cb, state)
    # The rendered confirm card carries the loud reminder.
    assert any("НЕ отправлена" in a for a in cb.message.answers)


# ------------------------ stale-callback fallback ------------------------ #
async def test_stale_callback_gives_next_step():
    cb = FakeCallback("confirm:submit")  # submit tap after the session was reset
    await fb.stale_callback(cb)
    # spinner cleared (answer() with no text) + a helpful message sent to the chat
    assert None in cb.answered
    assert any("register" in m.lower() for m in cb.message.answers)


async def test_stale_callback_without_message_uses_alert():
    cb = FakeCallback("mot:done")
    cb.message = None  # very old tap: source message no longer available
    await fb.stale_callback(cb)
    # Falls back to an alert popup carrying the guidance.
    assert any(m and "register" in m.lower() for m in cb.answered)
