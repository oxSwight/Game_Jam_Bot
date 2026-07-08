"""Category-coded player ids, per-application contact snapshots, and the
active/inactive membership tracking with returning-player memory."""

from types import SimpleNamespace

from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.core import config as cfg
from app.handlers import membership as membership_h
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


class FakeNotif:
    def __init__(self):
        self.welcomed: list = []

    async def notify_welcome_back(self, telegram_id, nickname, lang="ru"):
        self.welcomed.append((telegram_id, nickname, lang))


def _member(status, user_id=None, is_member=False):
    ns = SimpleNamespace(status=status, is_member=is_member)
    if user_id is not None:
        ns.user = SimpleNamespace(id=user_id, is_bot=False)
    return ns


def _chat_member_event(chat_id, user_id, old, new):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        old_chat_member=_member(old),
        new_chat_member=_member(new, user_id=user_id),
    )


async def _submit(services, session, **kw):
    read = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return read


# ------------------------ category-coded ids ------------------------ #
async def test_player_code_prefixed_by_category(services, session):
    prog = await _submit(services, session, telegram_id=1, nickname="Prog", email="p@x.com",
                         category_id="programming", category_title="Programming / Engineering",
                         roles=["programmer"])
    art = await _submit(services, session, telegram_id=2, nickname="Artist", email="a@x.com",
                        category_id="art_2d", category_title="2D Art", roles=["concept"])

    assert prog.player_code == 1000001   # programming block starts at 1_000_000
    assert art.player_code == 3000001    # 2D art block starts at 3_000_000


async def test_player_codes_increment_within_category(services, session):
    a = await _submit(services, session, telegram_id=1, nickname="Aa", email="a@x.com")
    b = await _submit(services, session, telegram_id=2, nickname="Bb", email="b@x.com")
    assert (a.player_code, b.player_code) == (1000001, 1000002)


async def test_category_change_reissues_player_code(services, session):
    read = await _submit(services, session, telegram_id=1, nickname="Switcher", email="s@x.com",
                         category_id="programming", category_title="Programming / Engineering",
                         roles=["programmer"])
    assert read.player_code == 1000001  # programming block

    # Switch discipline to Audio → the id must move into the audio block.
    payload = make_payload(telegram_id=1, nickname="Switcher", email="s@x.com",
                           category_id="audio", category_title="Audio", roles=["composer"])
    ok = await services.applications.update_profile(1, payload)
    await session.commit()
    assert ok

    profile = await services.users.get_profile(1)
    assert profile.main_category == "audio"
    assert profile.player_code == 5000001  # audio block (prefix 5)


async def test_same_category_edit_keeps_player_code(services, session):
    read = await _submit(services, session, telegram_id=1, nickname="Stable", email="st@x.com",
                         category_id="programming", category_title="Programming / Engineering",
                         roles=["programmer"])
    payload = make_payload(telegram_id=1, nickname="Stable", email="st@x.com",
                           category_id="programming", category_title="Programming / Engineering",
                           roles=["programmer", "backend_other"])
    await services.applications.update_profile(1, payload)
    await session.commit()
    profile = await services.users.get_profile(1)
    assert profile.player_code == read.player_code  # unchanged when discipline stays


# ------------------------ per-application snapshot ------------------------ #
async def test_reregistration_keeps_each_applications_own_contact(services, session):
    # Same telegram user registers, is rejected, then registers again with new data.
    first = await _submit(services, session, telegram_id=777, nickname="OldNick", email="old@x.com")
    await services.applications.update_status(first.id, ApplicationStatus.REJECTED)
    await session.commit()

    second = await _submit(services, session, telegram_id=777, nickname="NewNick", email="new@x.com")

    # Export sees BOTH applications, each with its OWN snapshot - not both rewritten
    # to the latest values (the reported bug).
    rows = await services.applications.list_all_with_users()
    by_id = {a.id: a for a in rows}
    assert by_id[first.id].nickname == "OldNick"
    assert by_id[first.id].email == "old@x.com"
    assert by_id[second.id].nickname == "NewNick"
    assert by_id[second.id].email == "new@x.com"


# ------------------------ active / inactive ------------------------ #
async def test_set_active_reflected_in_profile(services, session):
    await _submit(services, session, telegram_id=555, nickname="Mem", email="m@x.com")
    # not in group yet
    assert (await services.users.get_profile(555)).is_active is False

    await services.users.set_active(555, True)
    await session.commit()
    assert (await services.users.get_profile(555)).is_active is True


async def test_set_active_unknown_user_is_noop(services):
    assert await services.users.set_active(999999, True) is None


# ------------------------ returning-player memory ------------------------ #
async def test_start_greets_returning_player(services, session):
    # Registered before, then rejected → no active application, but still known.
    read = await _submit(services, session, telegram_id=888, nickname="Remembered", email="r@x.com")
    await services.applications.update_status(read.id, ApplicationStatus.REJECTED)
    await session.commit()

    msg = FakeMessage("/start", user_id=888)
    await reg_h.cmd_start(msg, make_state(888), services)
    assert any("возвращением" in a.lower() for a in msg.answers)
    assert any("Remembered" in a for a in msg.answers)


# ------------------------ membership handler ------------------------ #
async def test_membership_join_marks_active_and_greets(services, session, monkeypatch):
    await _submit(services, session, telegram_id=1234, nickname="Rejoiner", email="rj@x.com")
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)
    services.notifications = FakeNotif()

    ev = _chat_member_event(-100, 1234, ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
    await membership_h.on_group_membership_change(ev, services)

    user = await services.users.get_by_telegram_id(1234)
    assert user.is_active is True
    assert services.notifications.welcomed  # welcomed back by DM
    assert services.notifications.welcomed[0][1] == "Rejoiner"


async def test_membership_leave_marks_inactive_without_greeting(services, session, monkeypatch):
    await _submit(services, session, telegram_id=1234, nickname="Leaver", email="lv@x.com")
    await services.users.set_active(1234, True)
    await session.commit()
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)
    services.notifications = FakeNotif()

    ev = _chat_member_event(-100, 1234, ChatMemberStatus.MEMBER, ChatMemberStatus.LEFT)
    await membership_h.on_group_membership_change(ev, services)

    user = await services.users.get_by_telegram_id(1234)
    assert user.is_active is False
    assert not services.notifications.welcomed


async def test_membership_ignores_other_chats(services, session, monkeypatch):
    await _submit(services, session, telegram_id=1234, nickname="Xx", email="x@x.com")
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)
    services.notifications = FakeNotif()

    ev = _chat_member_event(-999, 1234, ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER)
    await membership_h.on_group_membership_change(ev, services)

    user = await services.users.get_by_telegram_id(1234)
    assert user.is_active is False  # untouched
    assert not services.notifications.welcomed
