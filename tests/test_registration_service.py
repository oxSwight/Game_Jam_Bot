import pytest
from sqlalchemy.exc import IntegrityError

from app.models.application import ApplicationStatus
from app.services.application import ActiveApplicationExistsError
from tests.conftest import make_payload


async def test_submit_registration_happy_path(services, session):
    app = await services.applications.submit_registration(make_payload())
    await session.commit()

    assert app.status == ApplicationStatus.PENDING_REVIEW.value
    assert app.nickname == "Tester"
    assert app.subcategories == ["Programmer", "Gameplay"]
    assert await services.applications.count_pending() == 1


async def test_duplicate_active_raises(services, session):
    await services.applications.submit_registration(make_payload())
    await session.commit()
    with pytest.raises(ActiveApplicationExistsError):
        await services.applications.submit_registration(make_payload())


async def test_one_active_per_user_db_constraint(services, session):
    """The partial unique index must reject a second non-rejected application
    even if the service-level guard were bypassed."""
    from app.models.application import Application

    user = await services.users.users.get_or_create(telegram_id=42)
    await session.flush()
    session.add(
        Application(
            user_id=user.id,
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
    )
    session.add(
        Application(
            user_id=user.id,
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
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_reject_then_reregister_allowed(services, session):
    app = await services.applications.submit_registration(make_payload())
    await session.commit()

    await services.applications.update_status(
        app.id, ApplicationStatus.REJECTED, actor_telegram_id=111
    )
    await session.commit()

    # Rejected no longer counts as active - a fresh submission is allowed.
    assert not await services.applications.has_active_application(1001)
    app2 = await services.applications.submit_registration(make_payload())
    await session.commit()
    assert app2.id != app.id


async def test_withdraw_erases_all_user_data(services, session):
    await services.applications.submit_registration(make_payload())
    await session.commit()

    assert await services.applications.erase_user_data(1001) is True
    await session.commit()
    # Right to erasure: not just the application - the user row (nickname,
    # email, username) is gone too, so nothing identifying remains.
    assert await services.applications.has_active_application(1001) is False
    assert await services.users.get_by_telegram_id(1001) is None
    # erasing again finds nothing
    assert await services.applications.erase_user_data(1001) is False
