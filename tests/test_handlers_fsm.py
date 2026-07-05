"""Handler happy/error coverage for the FSM- and callback-driven commands
(/history, /broadcast, /edit, /language, events/teams). Drives handlers with a
real FSMContext (MemoryStorage) and fake Message/CallbackQuery objects that
record what the bot would send."""

from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.handlers import admin as admin_h
from app.handlers import admin_extra
from app.handlers import registration as reg_h
from app.models.application import ApplicationStatus
from tests.conftest import make_payload


def make_state(user_id: int = 111) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id),
    )


class FakeMessage:
    def __init__(self, text: str = "", user_id: int = 111):
        self.text = text
        self.html_text = text
        self.from_user = SimpleNamespace(id=user_id, username="u", language_code="ru")
        self.chat = SimpleNamespace(id=user_id)
        self.answers: list[str] = []

    async def answer(self, text, **kw):
        self.answers.append(text)

    async def edit_text(self, text, **kw):
        self.answers.append(text)


class FakeCallback:
    def __init__(self, data: str, user_id: int = 111):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, username="u", language_code="ru")
        self.message = FakeMessage(user_id=user_id)
        self.answered: list = []

    async def answer(self, text=None, **kw):
        self.answered.append(text)


class FakeNotifications:
    def __init__(self):
        self.sent: list = []

    async def broadcast(self, recipients, text):
        self.sent.append((list(recipients), text))
        return (len(recipients), 0)


async def _submit(services, session, **kw):
    read = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return read


# ------------------------------ /history ------------------------------ #
async def test_history_happy(services, session):
    app = await _submit(services, session)
    msg = FakeMessage(f"/history {app.id[:8]}")
    await admin_h.cmd_history(msg, services)
    assert "История" in msg.answers[0]


async def test_history_missing_arg(services):
    msg = FakeMessage("/history")
    await admin_h.cmd_history(msg, services)
    assert "Использование" in msg.answers[0]


async def test_history_not_found(services):
    msg = FakeMessage("/history deadbeef")
    await admin_h.cmd_history(msg, services)
    assert "не найдена" in msg.answers[0].lower()


# ------------------------------ /broadcast ------------------------------ #
async def test_broadcast_no_recipients(services):
    state = make_state()
    msg = FakeMessage("/broadcast")
    await admin_extra.cmd_broadcast(msg, state, services)
    assert "нет одобренных" in msg.answers[0].lower()
    assert await state.get_state() is None


async def test_broadcast_happy_flow(services, session):
    read = await _submit(services, session)
    await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await session.commit()
    services.notifications = FakeNotifications()

    state = make_state()
    await admin_extra.cmd_broadcast(FakeMessage("/broadcast"), state, services)
    await admin_extra.broadcast_compose(FakeMessage("Hello players"), state)
    cb = FakeCallback("bcast:send")
    await admin_extra.broadcast_send(cb, state, services)

    assert services.notifications.sent  # a send happened
    recipients, text = services.notifications.sent[0]
    assert text == "Hello players"
    assert len(recipients) == 1
    assert await state.get_state() is None


# ------------------------------ /edit ------------------------------ #
async def test_edit_no_active_application(services):
    state = make_state()
    msg = FakeMessage("/edit")
    await reg_h.cmd_edit(msg, state, services)
    assert "нет активной заявки" in msg.answers[0].lower()


async def test_edit_nickname_happy(services, session):
    await _submit(services, session, telegram_id=111, nickname="Original", email="o@x.com")
    state = make_state(111)
    await reg_h.cmd_edit(FakeMessage("/edit", user_id=111), state, services)
    await reg_h.edit_pick_nickname(FakeCallback("edit:nickname", 111), state)
    await reg_h.edit_apply_nickname(FakeMessage("Renamed", user_id=111), state, services)

    profile = await services.users.get_profile(111)
    assert profile.nickname == "Renamed"
    assert await state.get_state() is None


async def test_edit_nickname_invalid(services, session):
    await _submit(services, session, telegram_id=111, nickname="Original", email="o@x.com")
    state = make_state(111)
    await reg_h.cmd_edit(FakeMessage("/edit", user_id=111), state, services)
    await reg_h.edit_pick_nickname(FakeCallback("edit:nickname", 111), state)
    msg = FakeMessage("x", user_id=111)  # too short
    await reg_h.edit_apply_nickname(msg, state, services)
    # validation error surfaced, nickname unchanged
    assert (await services.users.get_profile(111)).nickname == "Original"


# ------------------------------ /language ------------------------------ #
async def test_language_set(services, session):
    cb = FakeCallback("lang:en", user_id=111)
    await reg_h.set_language(cb, services)
    await services.session.commit()
    user = await services.users.get_by_telegram_id(111)
    assert user.language == "en"


# ------------------------------ events/teams ------------------------------ #
async def test_events_list(services, session):
    await services.events.create_event("Jam One")
    await session.commit()
    msg = FakeMessage("/events")
    await admin_extra.cmd_events(msg, services)
    assert "Jam One" in msg.answers[0]


async def test_event_activate_and_teams(services, session):
    ev = await services.events.create_event("Jam")
    await session.commit()
    # activate
    await admin_extra.cmd_event_activate(FakeMessage(f"/event_activate {ev.id}"), services)
    # create a team
    await admin_extra.cmd_team_new(FakeMessage(f"/team_new {ev.id} Red"), services)
    msg = FakeMessage("/teams")  # no arg → falls back to active event
    await admin_extra.cmd_teams(msg, services)
    assert "Red" in msg.answers[0]


async def test_team_new_missing_arg(services):
    msg = FakeMessage("/team_new")
    await admin_extra.cmd_team_new(msg, services)
    assert "Использование" in msg.answers[0]


async def test_autoteams_without_teams_errors(services, session):
    ev = await services.events.create_event("Jam")
    await session.commit()
    msg = FakeMessage(f"/autoteams {ev.id}")
    await admin_extra.cmd_autoteams(msg, services)
    assert "команд" in msg.answers[0].lower()


# --------------- free-text FSM guards & cancels --------------- #
async def test_reject_reason_ignores_slash_command(services, session):
    app = await _submit(services, session)
    state = make_state()
    await state.set_state(admin_h.AdminStates.reject_reason)
    await state.update_data(reject_app_id=app.id)
    msg = FakeMessage("/queue")
    await admin_h.process_reject_reason(msg, state, services)
    # command NOT consumed as a reason; application still pending
    assert "команда" in msg.answers[0].lower()
    still = await services.applications.find_by_prefix(app.id[:8])
    assert still.status == ApplicationStatus.PENDING_REVIEW


async def test_reject_reason_cancel(services):
    state = make_state()
    await state.set_state(admin_h.AdminStates.reject_reason)
    msg = FakeMessage("/cancel")
    await admin_h.cancel_reject_reason(msg, state)
    assert await state.get_state() is None
    assert "отменено" in msg.answers[0].lower()


async def test_broadcast_compose_ignores_slash_command():
    state = make_state()
    await state.set_state(admin_extra.AdminStates.broadcast_message)
    msg = FakeMessage("/stats")
    await admin_extra.broadcast_compose(msg, state)
    assert "команда" in msg.answers[0].lower()
    # still waiting for real text, not advanced to confirm
    assert await state.get_state() == admin_extra.AdminStates.broadcast_message.state


def test_not_command_filter():
    from app.handlers.registration import not_command

    assert not_command(FakeMessage("neo@example.com")) is True
    assert not_command(FakeMessage("Neo")) is True
    assert not_command(FakeMessage("/events")) is False
    assert not_command(FakeMessage("/leaderboard")) is False
    assert not_command(FakeMessage("")) is True  # non-command empty text


async def test_edit_cancel(services, session):
    await _submit(services, session, telegram_id=111, nickname="Original", email="o@x.com")
    state = make_state(111)
    await state.set_state(reg_h.EditStates.nickname)
    msg = FakeMessage("/cancel", user_id=111)
    await reg_h.cancel_edit(msg, state)
    assert await state.get_state() is None
