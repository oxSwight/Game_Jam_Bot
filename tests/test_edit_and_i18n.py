import pytest
from sqlalchemy.exc import IntegrityError

from app.core.i18n import (
    DEFAULT_LANG,
    assert_catalog_complete,
    normalize_lang,
    t,
)
from tests.conftest import make_payload


# --------------------------- i18n --------------------------- #
def test_catalog_complete():
    assert_catalog_complete()  # raises if any key misses a language


def test_t_formats_and_falls_back():
    assert "Neo" in t("notify_approved", "en", nickname="Neo")
    # unknown lang → default
    assert t("welcome", "zz") == t("welcome", DEFAULT_LANG)
    # unknown key → returns the key itself, never crashes
    assert t("no_such_key", "en") == "no_such_key"


def test_normalize_lang():
    assert normalize_lang("en") == "en"
    assert normalize_lang(None) == DEFAULT_LANG
    assert normalize_lang("fr") == DEFAULT_LANG


# --------------------------- /edit --------------------------- #
async def test_update_contact_changes_fields(services, session):
    await services.applications.submit_registration(make_payload())
    await session.commit()

    ok = await services.applications.update_contact(
        1001, nickname="NewNick", email="new@example.com"
    )
    await session.commit()
    assert ok is True
    profile = await services.users.get_profile(1001)
    assert profile.nickname == "NewNick"
    assert profile.email == "new@example.com"


async def test_update_contact_no_active_application(services):
    assert await services.applications.update_contact(9999, nickname="X") is False


async def test_update_contact_duplicate_email_raises(services, session):
    await services.applications.submit_registration(
        make_payload(telegram_id=1, nickname="Alice", email="a@x.com")
    )
    await services.applications.submit_registration(
        make_payload(telegram_id=2, nickname="Bob", email="b@x.com")
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await services.applications.update_contact(2, email="a@x.com")
        await session.flush()


async def test_set_language_persists(services, session):
    await services.users.set_language(1001, "en")
    await session.commit()
    user = await services.users.get_by_telegram_id(1001)
    assert user.language == "en"
