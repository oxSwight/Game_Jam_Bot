"""English (auto-detected) registration flow.

Covers the region-aware language default and that the whole questionnaire -
prompts, buttons, option labels, summary and /status - renders in English when
the resolved UI language is ``en``.
"""

from app.core.i18n import resolve_ui_lang
from app.handlers import registration as reg_h
from tests.conftest import make_payload
from tests.test_handlers_fsm import FakeCallback, FakeMessage, make_state


def test_resolve_ui_lang_region_aware():
    # non-CIS clients default to English
    assert resolve_ui_lang("en") == "en"
    assert resolve_ui_lang("en-US") == "en"
    assert resolve_ui_lang("fr") == "en"
    assert resolve_ui_lang("de-DE") == "en"
    assert resolve_ui_lang("pt-BR") == "en"
    # CIS locales (and no signal) default to Russian
    assert resolve_ui_lang("ru") == "ru"
    assert resolve_ui_lang("uk") == "ru"
    assert resolve_ui_lang("kk") == "ru"
    assert resolve_ui_lang(None) == "ru"


async def test_full_english_funnel(services):
    """Walk a beginner game-designer from roles to confirm in English and check
    each step, the strengths option label, and the final summary are localized."""
    state = make_state(111)
    await state.set_state(reg_h.RegistrationStates.roles)
    await state.update_data(
        nickname="Neo",
        email="neo@x.com",
        category_id="game_design",
        category_title="Гейм-дизайн",
        roles=["game_designer"],
        experience_level="beginner",
    )

    # roles done -> Step C (experience)
    cb = FakeCallback("role:done", 111)
    await reg_h.toggle_role(cb, state, lang="en")
    assert any("Step C - Experience level" in a for a in cb.message.answers)

    # experience -> Step D (game-design engine wording)
    cb = FakeCallback("exp:beginner", 111)
    await reg_h.process_experience(cb, state, lang="en")
    assert any("Step D - Engine or working context" in a for a in cb.message.answers)

    # pick an engine, finish -> Step E (tools)
    await reg_h.toggle_engine(FakeCallback("engine:Unreal Engine", 111), state, lang="en")
    cb = FakeCallback("engine:done", 111)
    await reg_h.toggle_engine(cb, state, lang="en")
    assert await state.get_state() == reg_h.RegistrationStates.tools.state

    # pick a tool, finish -> beginner branch opens Step F (strengths) in English
    await reg_h.toggle_tool(FakeCallback("tool:Miro", 111), state, lang="en")
    cb = FakeCallback("tool:done", 111)
    await reg_h.toggle_tool(cb, state, lang="en")
    assert await state.get_state() == reg_h.RegistrationStates.strengths.state
    assert any("Step F - Strengths" in a for a in cb.message.answers)

    # pick a strength (stored value is Russian, label is English), finish -> motivation
    await reg_h.toggle_strength(FakeCallback("strg:Придумывать механику", 111), state, lang="en")
    cb = FakeCallback("strg:done", 111)
    await reg_h.toggle_strength(cb, state, lang="en")
    assert await state.get_state() == reg_h.RegistrationStates.motivation.state

    # motivation done -> English confirm summary
    await reg_h.toggle_motivation(FakeCallback("mot:Learning", 111), state, lang="en")
    cb = FakeCallback("mot:done", 111)
    await reg_h.toggle_motivation(cb, state, lang="en")
    summary = next(a for a in cb.message.answers if "Nickname:" in a)
    assert "Category:</b> Game Design" in summary
    assert "Engine:</b> Unreal Engine" in summary
    assert "Tools:</b> Miro" in summary
    assert "Strengths:</b> Inventing mechanics" in summary  # localized label
    assert "Experience:</b> Beginner · 0-6 mo." in summary


async def test_status_renders_english(services, session):
    await services.applications.submit_registration(
        make_payload(telegram_id=111, nickname="Neo", email="neo@x.com")
    )
    await session.commit()

    msg = FakeMessage(user_id=111)
    await reg_h.cmd_status(msg, services, lang="en")
    out = msg.answers[0]
    assert "Your profile" in out
    assert "Category: Programming" in out
    assert "Engine: Unity" in out
    assert "Tools: Blender" in out
    assert "Experience: Beginner · 0-6 mo." in out
