"""Release-hardening regressions (round-3 audit fixes).

Covers: atomic admin decisions (no double approve/invite), counter-based
player_code allocation (incl. legacy-DB seeding), right-to-erasure /withdraw,
the submit-time queue cap, catalog whitelists on the final payload, the
join-request identity gate, /invite self-service, ambiguous-prefix refusal,
consent-version audit logging and PII-free audit details.
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core import config as cfg
from app.data.captcha import CAPTCHA_CHOICES, build_captcha
from app.handlers import membership as membership_h
from app.handlers import registration as reg_h
from app.models.application import Application, ApplicationStatus
from app.models.log import Log
from app.models.user import User
from app.schemas.registration import RegistrationCreate
from app.services.application import QueueFullError
from tests.conftest import make_payload
from tests.test_handlers_fsm import FakeMessage, FakeNotifications

pytestmark = []


async def _submit(services, session, **kw):
    read = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return read


def _fsm_data(**overrides):
    data = {
        "nickname": "Tester",
        "email": "t@x.com",
        "category_id": "programming",
        "category_title": "Programming / Engineering",
        "roles": ["programmer"],
        "experience_level": "beginner",
        "engine": ["Unity"],
        "engine_other": None,
        "tools": ["Blender"],
        "tools_other": None,
        "motivations": ["Learning"],
        "consent": True,
    }
    data.update(overrides)
    return data


# ------------------- atomic decisions (two-admin race) ------------------- #
async def test_second_decision_on_same_card_loses(services, session):
    read = await _submit(services, session)

    first = await services.applications.update_status(
        read.id,
        ApplicationStatus.APPROVED,
        actor_telegram_id=111,
        expected_status=ApplicationStatus.PENDING_REVIEW,
    )
    assert first is not None

    # Second admin raced on the same pending card - conditional UPDATE matches
    # zero rows, so no second decision (and no second invite) happens.
    second = await services.applications.update_status(
        read.id,
        ApplicationStatus.REJECTED,
        actor_telegram_id=222,
        expected_status=ApplicationStatus.PENDING_REVIEW,
    )
    assert second is None

    reloaded = await services.applications.find_by_prefix(read.id)
    assert reloaded.status == ApplicationStatus.APPROVED


# ------------------- player_code counter allocation ------------------- #
async def test_counter_seeds_from_legacy_max(services, session):
    """A legacy DB has codes but no counter rows: the first allocation must seed
    from the highest existing code in the block, not restart at the base."""
    user = await services.users.users.get_or_create(telegram_id=77)
    await session.flush()
    session.add(
        Application(
            user_id=user.id,
            player_code=1000041,
            main_category="programming",
            skill_category_id="programming",
            skill_category_title="Programming",
            subcategories=["Programmer"],
            experience_level="beginner",
            engine=["Unity"],
            tools=["Blender"],
            motivations=["Learning"],
            status=ApplicationStatus.REJECTED,
        )
    )
    await session.commit()

    read = await _submit(services, session, telegram_id=78, nickname="Next", email="n@x.com")
    assert read.player_code == 1000042


async def test_counter_survives_reuse_within_category(services, session):
    a = await _submit(services, session, telegram_id=1, nickname="Aa", email="a@x.com")
    b = await _submit(services, session, telegram_id=2, nickname="Bb", email="b@x.com")
    c = await _submit(services, session, telegram_id=3, nickname="Cc", email="c@x.com")
    codes = {a.player_code, b.player_code, c.player_code}
    assert codes == {1000001, 1000002, 1000003}


# ------------------- submit-time queue cap ------------------- #
async def test_submit_refused_when_queue_filled_mid_form(services, session, monkeypatch):
    await _submit(services, session, telegram_id=900, nickname="Filler", email="f@x.com")
    monkeypatch.setattr(cfg.get_settings(), "pending_cap", 1, raising=False)

    with pytest.raises(QueueFullError):
        await services.applications.submit_registration(
            make_payload(telegram_id=901, nickname="Late", email="late@x.com")
        )
    # refused submit leaves no side effects - not even a user row
    assert await services.users.get_by_telegram_id(901) is None


# ------------------- payload whitelists ------------------- #
def test_payload_rejects_forged_catalog_values():
    forged = {
        "engine": ["TotallyRealEngine"],
        "tools": ["EvilTool"],
        "motivations": ["Spam"],
        "experience_level": "l33t",
    }
    for field, value in forged.items():
        with pytest.raises(ValidationError):
            RegistrationCreate.from_fsm_data(
                data=_fsm_data(**{field: value}), telegram_id=1, telegram_username="u"
            )


def test_payload_accepts_catalog_values():
    payload = RegistrationCreate.from_fsm_data(
        data=_fsm_data(), telegram_id=1, telegram_username="u"
    )
    assert payload.engine == ["Unity"]


# ------------------- right to erasure ------------------- #
async def test_erase_removes_user_applications_and_logs(services, session):
    await _submit(services, session)

    assert await services.applications.erase_user_data(1001) is True
    await session.commit()

    assert (await session.scalars(select(User))).all() == []
    assert (await session.scalars(select(Application))).all() == []
    remaining_actions = list((await session.scalars(select(Log.action))).all())
    # everything tied to the erased user is gone; only the anonymous marker stays
    assert remaining_actions == ["data_erased"]


async def test_erase_includes_rejected_snapshots(services, session):
    read = await _submit(services, session)
    await services.applications.update_status(read.id, ApplicationStatus.REJECTED)
    await session.commit()

    assert await services.applications.erase_user_data(1001) is True
    await session.commit()
    assert (await session.scalars(select(Application))).all() == []


# ------------------- audit log minimisation ------------------- #
async def test_submit_log_records_consent_version(services, session):
    await _submit(services, session)
    log = (
        await session.scalars(
            select(Log).where(Log.action == "application_submitted")
        )
    ).first()
    assert "consent_v=1" in (log.details or "")


async def test_contact_update_log_carries_no_pii(services, session):
    await _submit(services, session)
    await services.applications.update_contact(1001, email="secret@x.com")
    await session.commit()
    log = (
        await session.scalars(select(Log).where(Log.action == "contact_updated"))
    ).first()
    assert "secret@x.com" not in (log.details or "")
    assert "email=changed" in log.details


# ------------------- join-request identity gate ------------------- #
class FakeJoinRequest:
    def __init__(self, chat_id: int, user_id: int):
        self.chat = SimpleNamespace(id=chat_id)
        self.from_user = SimpleNamespace(id=user_id, is_bot=False)
        self.approved = False
        self.declined = False

    async def approve(self):
        self.approved = True

    async def decline(self):
        self.declined = True


async def test_join_request_approved_player_admitted(services, session, monkeypatch):
    read = await _submit(services, session, telegram_id=321, nickname="Ok", email="ok@x.com")
    await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await session.commit()
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)

    ev = FakeJoinRequest(-100, 321)
    await membership_h.on_join_request(ev, services)
    assert ev.approved and not ev.declined


async def test_join_request_pending_player_declined(services, session, monkeypatch):
    await _submit(services, session, telegram_id=322, nickname="Pend", email="p@x.com")
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)

    ev = FakeJoinRequest(-100, 322)
    await membership_h.on_join_request(ev, services)
    assert ev.declined and not ev.approved


async def test_join_request_stranger_declined(services, monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)
    ev = FakeJoinRequest(-100, 999999)
    await membership_h.on_join_request(ev, services)
    assert ev.declined and not ev.approved


async def test_join_request_other_chat_ignored(services, monkeypatch):
    monkeypatch.setattr(cfg.get_settings(), "group_chat_id", -100, raising=False)
    ev = FakeJoinRequest(-999, 999999)
    await membership_h.on_join_request(ev, services)
    assert not ev.declined and not ev.approved


# ------------------- /invite self-service ------------------- #
async def test_invite_reissues_link_for_approved(services, session):
    read = await _submit(services, session, telegram_id=111, nickname="Appr", email="ap@x.com")
    await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await session.commit()
    services.notifications = FakeNotifications()

    await reg_h.cmd_invite(FakeMessage("/invite", user_id=111), services)
    assert services.notifications.approved  # a fresh link was minted and DMed


async def test_invite_refused_before_approval(services, session):
    await _submit(services, session, telegram_id=112, nickname="Pnd", email="pn@x.com")
    services.notifications = FakeNotifications()

    msg = FakeMessage("/invite", user_id=112)
    await reg_h.cmd_invite(msg, services)
    assert not services.notifications.approved
    assert any("одобрения" in a.lower() for a in msg.answers)


async def test_admin_invite_by_username_delivers_to_target(services, session):
    from aiogram.filters import CommandObject

    read = await _submit(services, session, telegram_id=555, nickname="Bob", email="bob@x.com")
    await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await session.commit()
    services.notifications = FakeNotifications()

    msg = FakeMessage("/invite @tester", user_id=999)  # 999 = admin
    await reg_h.cmd_invite(
        msg, services, command=CommandObject(command="invite", args="@tester"), is_admin=True
    )
    # the link went to the TARGET (555), not the admin who issued the command
    assert services.notifications.approved
    assert services.notifications.approved[0][0] == 555
    assert any("отправлена" in a.lower() for a in msg.answers)


async def test_admin_invite_unknown_username(services):
    from aiogram.filters import CommandObject

    services.notifications = FakeNotifications()
    msg = FakeMessage("/invite @ghost", user_id=999)
    await reg_h.cmd_invite(
        msg, services, command=CommandObject(command="invite", args="@ghost"), is_admin=True
    )
    assert not services.notifications.approved
    assert any("не найден" in a.lower() for a in msg.answers)


async def test_admin_invite_target_not_approved(services, session):
    from aiogram.filters import CommandObject

    await _submit(services, session, telegram_id=556, nickname="Pend", email="p@x.com")  # pending
    services.notifications = FakeNotifications()
    msg = FakeMessage("/invite @tester", user_id=999)
    await reg_h.cmd_invite(
        msg, services, command=CommandObject(command="invite", args="@tester"), is_admin=True
    )
    assert not services.notifications.approved
    assert any("одобрен" in a.lower() for a in msg.answers)


async def test_non_admin_invite_with_arg_falls_back_to_self(services):
    from aiogram.filters import CommandObject

    services.notifications = FakeNotifications()
    # a non-admin can't invite others: the @arg is ignored, they get the
    # self-service path (and have no approved application of their own)
    msg = FakeMessage("/invite @tester", user_id=777)
    await reg_h.cmd_invite(
        msg, services, command=CommandObject(command="invite", args="@tester"), is_admin=False
    )
    assert not services.notifications.approved
    assert any("одобрен" in a.lower() for a in msg.answers)


async def test_invite_refused_when_already_member(services, session):
    read = await _submit(services, session, telegram_id=113, nickname="Mem", email="m@x.com")
    await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
    await services.users.set_active(113, True)
    await session.commit()
    services.notifications = FakeNotifications()

    msg = FakeMessage("/invite", user_id=113)
    await reg_h.cmd_invite(msg, services)
    assert not services.notifications.approved
    assert any("уже состоите" in a.lower() for a in msg.answers)


# ------------------- ambiguous id prefix ------------------- #
async def test_ambiguous_prefix_matches_nothing(services, session):
    u1 = await services.users.users.get_or_create(telegram_id=31)
    u2 = await services.users.users.get_or_create(telegram_id=32)
    await session.flush()
    common = dict(
        main_category="programming",
        skill_category_id="programming",
        skill_category_title="Programming",
        subcategories=["Programmer"],
        experience_level="beginner",
        engine=["Unity"],
        tools=["Blender"],
        motivations=["Learning"],
        status=ApplicationStatus.PENDING_REVIEW,
    )
    session.add(Application(id="aaaa1111-0000-0000-0000-000000000001", user_id=u1.id, **common))
    session.add(Application(id="aaaa2222-0000-0000-0000-000000000002", user_id=u2.id, **common))
    await session.commit()

    # A prefix hitting two rows must refuse rather than pick "whichever first".
    assert await services.applications.find_by_prefix("aaaa") is None
    found = await services.applications.find_by_prefix(
        "aaaa1111-0000-0000-0000-000000000001"
    )
    assert found is not None
    assert await services.applications.find_by_prefix("") is None


# ------------------- captcha hardening ------------------- #
def test_captcha_uses_wider_option_set():
    options, target = build_captcha()
    assert len(options) == CAPTCHA_CHOICES == 8
    assert len(set(options)) == len(options)
    assert 0 <= target < len(options)


# ------------------- consent document ------------------- #
def test_consent_text_documents_data_and_erasure():
    from app.core.i18n import t

    for lang in ("ru", "en"):
        text = t("consent_text", lang, version=1)
        assert "/withdraw" in text  # the erasure path is stated up front
        assert "email" in text.lower()  # what is collected is named explicitly


# ============ round-4: co-admin feedback (menu clarity, engine/tools, /review) ============ #

# ------------------- category title clarity (issue 1) ------------------- #
def test_management_category_title_has_no_bare_pm_jargon():
    from app.data.catalog import CATEGORY_BY_ID

    title = CATEGORY_BY_ID["management"].title
    assert title == "Менеджмент / Продюсирование"
    # the bare "/ PM" abbreviation the co-admin couldn't parse is gone from the title
    assert not title.endswith("PM")


def test_category_titles_are_localised_russian():
    from app.data.catalog import CATEGORY_BY_ID

    assert CATEGORY_BY_ID["programming"].title == "Программирование"
    assert CATEGORY_BY_ID["art_2d"].title == "2D-арт"


# ------------------- engine/tools options (issue 2) ------------------- #
def test_other_option_shown_under_friendly_label():
    from app.data.catalog import option_label

    assert option_label("Other") == "Свой вариант"
    assert option_label("Unity") == "Unity"  # real values pass through unchanged


def test_no_experience_option_accepted_by_payload():
    from app.data.catalog import NO_EXPERIENCE_OPTION

    payload = RegistrationCreate.from_fsm_data(
        data=_fsm_data(engine=[NO_EXPERIENCE_OPTION], tools=[NO_EXPERIENCE_OPTION]),
        telegram_id=1,
        telegram_username="u",
    )
    assert payload.engine == [NO_EXPERIENCE_OPTION]
    assert payload.tools == [NO_EXPERIENCE_OPTION]


async def test_engine_none_option_is_exclusive():
    from app.data.catalog import NO_EXPERIENCE_OPTION
    from tests.test_handlers_fsm import FakeCallback, make_state

    state = make_state()
    await state.set_state(reg_h.RegistrationStates.engine)
    await state.update_data(engine=["Unity"], engine_other="Custom")

    # picking "haven't worked" wipes real picks and pending free-text
    await reg_h.toggle_engine(FakeCallback(f"engine:{NO_EXPERIENCE_OPTION}"), state)
    data = await state.get_data()
    assert data["engine"] == [NO_EXPERIENCE_OPTION]
    assert data.get("engine_other") is None

    # picking a real engine afterwards drops the sentinel
    await reg_h.toggle_engine(FakeCallback("engine:Godot"), state)
    assert (await state.get_data())["engine"] == ["Godot"]


async def test_tool_none_option_is_exclusive():
    from app.data.catalog import NO_EXPERIENCE_OPTION
    from tests.test_handlers_fsm import FakeCallback, make_state

    state = make_state()
    await state.set_state(reg_h.RegistrationStates.tools)
    await state.update_data(tools=["Blender", "Maya"])

    await reg_h.toggle_tool(FakeCallback(f"tool:{NO_EXPERIENCE_OPTION}"), state)
    assert (await state.get_data())["tools"] == [NO_EXPERIENCE_OPTION]

    await reg_h.toggle_tool(FakeCallback("tool:Krita"), state)
    assert (await state.get_data())["tools"] == ["Krita"]


# ------------------- admin ping on new application (issue 3) ------------------- #
class FakeBot:
    def __init__(self):
        self.sent: list = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


async def test_admin_ping_reaches_every_admin(monkeypatch):
    from app.services.notification import NotificationService

    bot = FakeBot()
    svc = NotificationService(bot)
    monkeypatch.setattr(svc.settings, "admin_ids", [111, 222], raising=False)

    await svc.notify_admins_new_application("Neo", "Программирование", 4)
    assert [c for c, _ in bot.sent] == [111, 222]
    assert "Neo" in bot.sent[0][1] and "4" in bot.sent[0][1]


async def test_admin_ping_debounced_under_burst(monkeypatch):
    from app.services.notification import NotificationService

    bot = FakeBot()
    svc = NotificationService(bot, admin_ping_window=10_000.0)
    monkeypatch.setattr(svc.settings, "admin_ids", [111], raising=False)

    await svc.notify_admins_new_application("A", "cat", 1)
    await svc.notify_admins_new_application("B", "cat", 2)
    assert len(bot.sent) == 1  # second ping suppressed within the window


async def test_admin_ping_noop_without_admins(monkeypatch):
    from app.services.notification import NotificationService

    bot = FakeBot()
    svc = NotificationService(bot)
    monkeypatch.setattr(svc.settings, "admin_ids", [], raising=False)

    await svc.notify_admins_new_application("A", "cat", 1)
    assert bot.sent == []


# ------------------- approval clears a prior ban (expired-link fix) ------------------- #
async def test_approval_unbans_before_inviting(monkeypatch):
    from types import SimpleNamespace

    from app.services.notification import NotificationService

    class InviteBot:
        def __init__(self):
            self.unbanned: list = []
            self.sent: list = []

        async def unban_chat_member(self, chat_id, user_id, only_if_banned=False):
            self.unbanned.append((chat_id, user_id, only_if_banned))

        async def create_chat_invite_link(self, chat_id, **kw):
            assert kw.get("creates_join_request") is True
            return SimpleNamespace(invite_link="https://t.me/+fresh")

        async def send_message(self, chat_id, text, **kw):
            self.sent.append((chat_id, text))

    bot = InviteBot()
    svc = NotificationService(bot)
    monkeypatch.setattr(svc.settings, "group_chat_id", -1004483350935, raising=False)

    ok = await svc.send_approval_with_invite(1649043123, "Hanna", lang="ru")
    assert ok is True
    # a banned applicant is unbanned (only_if_banned) BEFORE the link is minted,
    # so their fresh link isn't rejected as "expired"
    assert bot.unbanned == [(-1004483350935, 1649043123, True)]
    assert any("+fresh" in text for _, text in bot.sent)


async def test_confirm_submit_pings_admins(services, session):
    from tests.test_handlers_fsm import FakeCallback, FakeNotifications, make_state

    services.notifications = FakeNotifications()
    state = make_state(654)
    await state.set_state(reg_h.RegistrationStates.confirm)
    await state.update_data(**_fsm_data(nickname="Jane", email="jane@x.com"))

    await reg_h.confirm_submit(FakeCallback("confirm:submit", user_id=654), state, services)
    assert services.notifications.admin_pings
    assert services.notifications.admin_pings[0][0] == "Jane"


# ------------------- startup config warnings (issue 3 root cause) ------------------- #
def test_risky_config_warns_on_empty_admins_and_placeholder_group(caplog):
    from types import SimpleNamespace

    from app.main import _EXAMPLE_GROUP_CHAT_ID, _warn_on_risky_config

    with caplog.at_level("WARNING"):
        _warn_on_risky_config(
            SimpleNamespace(admin_ids=[], group_chat_id=_EXAMPLE_GROUP_CHAT_ID)
        )
    blob = " ".join(r.message for r in caplog.records)
    assert "ADMIN_IDS" in blob
    assert "GROUP_CHAT_ID" in blob


def test_healthy_config_is_silent(caplog):
    from types import SimpleNamespace

    from app.main import _warn_on_risky_config

    with caplog.at_level("WARNING"):
        _warn_on_risky_config(SimpleNamespace(admin_ids=[111], group_chat_id=-100987654321))
    assert not caplog.records
