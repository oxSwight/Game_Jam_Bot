import pytest
from pydantic import ValidationError

from app.schemas.registration import (
    EmailStep,
    NicknameStep,
    RegistrationCreate,
    ToolsStep,
)


def test_nickname_too_short():
    with pytest.raises(ValidationError):
        NicknameStep(nickname="a")


def test_nickname_ok():
    assert NicknameStep(nickname="  Neo  ").nickname == "Neo"


def test_email_invalid():
    with pytest.raises(ValidationError):
        EmailStep(email="not-an-email")


def test_tools_other_required_when_other_selected():
    with pytest.raises(ValidationError):
        ToolsStep(tools=["Other"], tools_other=None)


def test_tools_reject_unknown():
    with pytest.raises(ValidationError):
        ToolsStep(tools=["NotAToolInCatalog"])


def test_from_fsm_data_stores_role_titles():
    payload = RegistrationCreate.from_fsm_data(
        data={
            "nickname": "Neo",
            "email": "neo@example.com",
            "category_id": "programming",
            "category_title": "Programming / Engineering",
            "roles": ["programmer", "gameplay"],
            "experience_level": "beginner",
            "engine": ["Unity"],
            "tools": ["Blender"],
            "motivations": ["Learning"],
            "consent": True,
        },
        telegram_id=5,
        telegram_username="neo",
    )
    # role ids resolved to human titles for downstream rendering
    assert payload.subcategories == ["Programmer", "Gameplay"]
    assert payload.main_category == "programming"


def test_invalid_main_category_rejected():
    with pytest.raises(ValidationError):
        RegistrationCreate.from_fsm_data(
            data={
                "nickname": "Neo",
                "email": "neo@example.com",
                "category_id": "not_real",
                "category_title": "X",
                "roles": ["programmer"],
                "experience_level": "beginner",
                "engine": ["Unity"],
                "tools": ["Blender"],
                "motivations": ["Learning"],
                "consent": True,
            },
            telegram_id=5,
            telegram_username="neo",
        )
