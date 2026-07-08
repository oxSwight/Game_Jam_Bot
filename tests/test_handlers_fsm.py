"""Handler happy/error coverage for the FSM- and callback-driven flows
(captcha, /review, /broadcast, /edit, /language, url-reset). Drives handlers with
a real FSMContext (MemoryStorage) and fake Message/CallbackQuery objects that
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

    async def edit_reply_markup(self, **kw):
        pass

    async def delete(self):
        pass


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
        self.approved: list = []
        self.rejected: list = []
        self.admin_pings: list = []

    async def broadcast(self, recipients, text):
        self.sent.append((list(recipients), text))
        return (len(recipients), 0)

    async def send_approval_with_invite(self, telegram_id, nickname, lang="ru"):
        self.approved.append((telegram_id, nickname, lang))
        return True

    async def notify_user_rejected(self, telegram_id, reason=None, lang="ru"):
        self.rejected.append((telegram_id, reason, lang))

    async def notify_admins_new_application(self, nickname, category, pending_count):
        self.admin_pings.append((nickname, category, pending_count))


async def _submit(services, session, **kw):
    read = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return read


# ------------------------------ captcha ------------------------------ #
async def test_register_opens_captcha_gate(services):
    state = make_state(111)
    await reg_h.cmd_register(FakeMessage("/register", user_id=111), state, services)
    assert await state.get_state() == reg_h.RegistrationStates.captcha.state
    assert "captcha_answer" in await state.get_data()


async def test_captcha_correct_advances_to_consent(services):
    state = make_state(111)
    await reg_h.cmd_register(FakeMessage("/register", user_id=111), state, services)
    target = (await state.get_data())["captcha_answer"]
    await reg_h.process_captcha(FakeCallback(f"cap:{target}", 111), state)
    assert await state.get_state() == reg_h.RegistrationStates.consent.state


async def test_captcha_wrong_cancels_registration(services):
    from app.data.captcha import CAPTCHA_CHOICES

    state = make_state(111)
    await reg_h.cmd_register(FakeMessage("/register", user_id=111), state, services)
    target = (await state.get_data())["captcha_answer"]
    wrong = (target + 1) % CAPTCHA_CHOICES
    cb = FakeCallback(f"cap:{wrong}", 111)
    await reg_h.process_captcha(cb, state)
    assert await state.get_state() is None
    assert any("не пройдена" in (a or "").lower() for a in cb.message.answers)


async def test_register_blocked_when_queue_full(services, session, monkeypatch):
    # Cap the queue at 1 and fill it, then a new /register must be refused.
    from app.core import config as cfg

    await _submit(services, session, telegram_id=900, nickname="Filler", email="f@x.com")
    monkeypatch.setattr(cfg.get_settings(), "pending_cap", 1, raising=False)

    state = make_state(222)
    msg = FakeMessage("/register", user_id=222)
    await reg_h.cmd_register(msg, state, services)
    assert await state.get_state() is None
    assert "переполнена" in msg.answers[0].lower()


# ------------------------------ url reset ------------------------------ #
async def test_url_in_nickname_resets_flow(services):
    state = make_state(111)
    await state.set_state(reg_h.RegistrationStates.nickname)
    msg = FakeMessage("visit http://evil.example", user_id=111)
    await reg_h.process_nickname(msg, state, services)
    assert await state.get_state() is None
    assert "ссылки" in msg.answers[0].lower()


async def test_plain_email_is_not_treated_as_url(services):
    # Regression: an @-domain email must not be misread as a link.
    state = make_state(111)
    await state.update_data(nickname="Neo")
    await state.set_state(reg_h.RegistrationStates.email)
    msg = FakeMessage("neo@example.com", user_id=111)
    await reg_h.process_email(msg, state, services)
    assert await state.get_state() == reg_h.RegistrationStates.category.state


# ------------------------------ /review ------------------------------ #
async def test_review_shows_first_pending(services, session):
    await _submit(services, session, telegram_id=501, nickname="P1", email="p1@x.com")
    msg = FakeMessage("/review", user_id=111)
    await admin_h.cmd_review(msg, services)
    assert "Очередь" in msg.answers[0]
    assert "P1" in msg.answers[0]


async def test_review_empty_queue(services):
    msg = FakeMessage("/review", user_id=111)
    await admin_h.cmd_review(msg, services)
    assert "пуст" in msg.answers[0].lower()


async def test_review_approve_mints_invite_and_swipes(services, session):
    a = await _submit(services, session, telegram_id=501, nickname="P1", email="p1@x.com")
    await _submit(services, session, telegram_id=502, nickname="P2", email="p2@x.com")
    services.notifications = FakeNotifications()

    cb = FakeCallback(f"rev:approve:{a.id[:8]}", user_id=111)
    await admin_h.cb_review_decision(cb, services)

    # approved + personal invite requested for that user
    assert services.notifications.approved
    assert services.notifications.approved[0][1] == "P1"
    reloaded = await services.applications.find_by_prefix(a.id[:8])
    assert reloaded.status == ApplicationStatus.APPROVED
    # card was edited in place to the next pending application (P2)
    assert any("P2" in a for a in cb.message.answers)


async def test_review_reject_notifies_user(services, session):
    a = await _submit(services, session, telegram_id=501, nickname="P1", email="p1@x.com")
    services.notifications = FakeNotifications()

    cb = FakeCallback(f"rev:reject:{a.id[:8]}", user_id=111)
    await admin_h.cb_review_decision(cb, services)

    assert services.notifications.rejected
    reloaded = await services.applications.find_by_prefix(a.id[:8])
    assert reloaded.status == ApplicationStatus.REJECTED
    # queue now empty → card shows the empty state
    assert any("пуст" in a.lower() for a in cb.message.answers)


async def test_review_already_handled_advances(services, session):
    a = await _submit(services, session, telegram_id=501, nickname="P1", email="p1@x.com")
    await services.applications.update_status(a.id, ApplicationStatus.APPROVED)
    await session.commit()
    services.notifications = FakeNotifications()

    cb = FakeCallback(f"rev:approve:{a.id[:8]}", user_id=111)
    await admin_h.cb_review_decision(cb, services)
    # not re-approved; no invite minted
    assert not services.notifications.approved
    assert any("уже обработана" in (t or "").lower() for t in cb.answered)


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

    assert services.notifications.sent
    recipients, text = services.notifications.sent[0]
    assert text == "Hello players"
    assert len(recipients) == 1
    assert await state.get_state() is None


async def test_broadcast_compose_ignores_slash_command():
    state = make_state()
    await state.set_state(admin_extra.AdminStates.broadcast_message)
    msg = FakeMessage("/stats")
    await admin_extra.broadcast_compose(msg, state)
    assert "команда" in msg.answers[0].lower()
    assert await state.get_state() == admin_extra.AdminStates.broadcast_message.state


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
    assert (await services.users.get_profile(111)).nickname == "Original"


# ------------------------------ /language ------------------------------ #
async def test_language_set(services, session):
    cb = FakeCallback("lang:en", user_id=111)
    await reg_h.set_language(cb, services)
    await services.session.commit()
    user = await services.users.get_by_telegram_id(111)
    assert user.language == "en"


async def test_language_set_shows_next_step(services, session):
    # A brand-new user picking a language must not dead-end on a bare
    # "language switched": the landing now guides them into registration.
    cb = FakeCallback("lang:en", user_id=111)
    await reg_h.set_language(cb, services)
    assert any("/register" in a for a in cb.message.answers)


async def test_start_registration_button_opens_captcha(services, session):
    state = make_state(111)
    cb = FakeCallback("reg:start", user_id=111)
    await reg_h.cb_start_registration(cb, state, services)
    assert await state.get_state() == reg_h.RegistrationStates.captcha.state


# --------------- free-text FSM guards & cancels --------------- #
def test_not_command_filter():
    from app.handlers.registration import not_command

    assert not_command(FakeMessage("neo@example.com")) is True
    assert not_command(FakeMessage("Neo")) is True
    assert not_command(FakeMessage("/register")) is False
    assert not_command(FakeMessage("/review")) is False
    assert not_command(FakeMessage("")) is True  # non-command empty text


async def test_edit_cancel(services, session):
    await _submit(services, session, telegram_id=111, nickname="Original", email="o@x.com")
    state = make_state(111)
    await state.set_state(reg_h.EditStates.nickname)
    msg = FakeMessage("/cancel", user_id=111)
    await reg_h.cancel_edit(msg, state)
    assert await state.get_state() is None


# --------------- duplicate nickname/email on submit --------------- #
async def _seed_confirm_state(state, *, nickname, email):
    """Put the FSM in the confirm step with a full, valid registration payload."""
    await state.set_state(reg_h.RegistrationStates.confirm)
    await state.update_data(
        nickname=nickname,
        email=email,
        category_id="programming",
        category_title="Programming / Engineering",
        roles=["gameplay_programmer", "general_programmer"],
        experience_level="beginner",
        engine=["Unity"],
        engine_other=None,
        tools=["Blender"],
        tools_other=None,
        motivations=["Learning"],
        consent=True,
    )


async def test_submit_duplicate_nickname_recovers(services, session):
    # First player takes the nickname "Alex".
    await _submit(services, session, telegram_id=111, nickname="Alex", email="alex@x.com")

    # Second player reaches confirm with the SAME (already-taken) nickname.
    state = make_state(222)
    await _seed_confirm_state(state, nickname="Alex", email="bob@x.com")
    cb = FakeCallback("confirm:submit", user_id=222)
    await reg_h.confirm_submit(cb, state, services)  # must NOT raise

    assert any("занят" in (a or "").lower() for a in cb.answered)
    assert await state.get_state() == reg_h.RegistrationStates.nickname.state
    assert await services.users.get_profile(222) is None

    # They re-enter a free nickname, then email - the flow jumps straight back to
    # confirm (category/roles preserved), and the retried submit now succeeds.
    await reg_h.process_nickname(FakeMessage("Alex2", user_id=222), state, services)
    await reg_h.process_email(FakeMessage("bob@x.com", user_id=222), state, services)
    assert await state.get_state() == reg_h.RegistrationStates.confirm.state

    cb2 = FakeCallback("confirm:submit", user_id=222)
    await reg_h.confirm_submit(cb2, state, services)
    profile = await services.users.get_profile(222)
    assert profile is not None
    assert profile.nickname == "Alex2"
    assert await state.get_state() is None


# --------------- edit profile: skills & category --------------- #
async def test_edit_skills_updates_existing_application(services, session):
    read = await _submit(services, session, telegram_id=111, nickname="Tester", email="t@x.com")
    original_id = read.id

    state = make_state(111)
    await reg_h.cmd_edit(FakeMessage("/edit", user_id=111), state, services)
    await reg_h.edit_pick_skills(FakeCallback("edit:skills", 111), state, services)

    assert await state.get_state() == reg_h.RegistrationStates.category.state
    data = await state.get_data()
    assert data.get("edit_mode") is True
    assert data.get("roles") == ["gameplay_programmer", "general_programmer"]
    assert data.get("engine") == ["Unity"]

    await reg_h.process_category(FakeCallback("cat:programming", 111), state)
    assert (await state.get_data()).get("roles") == ["gameplay_programmer", "general_programmer"]
    await reg_h.toggle_role(FakeCallback("role:ai_programmer", 111), state)
    await reg_h.toggle_role(FakeCallback("role:done", 111), state)

    await reg_h.process_experience(FakeCallback("exp:commercial", 111), state)
    await reg_h.toggle_engine(FakeCallback("engine:done", 111), state)
    await reg_h.toggle_tool(FakeCallback("tool:done", 111), state)
    await reg_h.toggle_motivation(FakeCallback("mot:done", 111), state)
    assert await state.get_state() == reg_h.RegistrationStates.confirm.state

    await reg_h.confirm_submit(FakeCallback("confirm:submit", 111), state, services)
    assert await state.get_state() is None

    profile = await services.users.get_profile(111)
    assert profile.id == original_id                  # same row, not a new application
    assert profile.experience_level == "commercial"   # changed
    assert "AI Programmer" in profile.subcategories        # added role
    assert "Gameplay Programmer" in profile.subcategories  # kept
    assert profile.engine == ["Unity"]                # preserved through the walk


async def test_update_profile_service_preserves_status(services, session):
    read = await _submit(services, session, telegram_id=111, nickname="Tester", email="t@x.com")
    await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await session.commit()

    payload = make_payload(telegram_id=111, nickname="Tester", email="t@x.com")
    ok = await services.applications.update_profile(111, payload)
    await session.commit()
    assert ok is True

    profile = await services.users.get_profile(111)
    assert profile.id == read.id
    assert profile.status == "approved"  # editing skills doesn't reset the decision


async def test_update_profile_no_active_application(services):
    payload = make_payload(telegram_id=404)
    assert await services.applications.update_profile(404, payload) is False


async def test_engine_other_rejects_overlong_text():
    state = make_state()
    await state.set_state(reg_h.RegistrationStates.engine_other)
    await reg_h.process_engine_other(FakeMessage("x" * 200), state)
    assert (await state.get_data()).get("engine_other") is None
    assert await state.get_state() == reg_h.RegistrationStates.engine_other.state
