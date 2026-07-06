from app.models.application import ApplicationStatus
from tests.conftest import make_payload


async def _submit(services, session, **kw):
    app = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return app


async def test_count_by_status(services, session):
    a1 = await _submit(services, session, telegram_id=1, nickname="Alice", email="a@x.com")
    await _submit(services, session, telegram_id=2, nickname="Bob", email="b@x.com")
    await services.applications.update_status(a1.id, ApplicationStatus.APPROVED)
    await session.commit()

    counts = await services.applications.count_by_status()
    assert counts.get("approved") == 1
    assert counts.get("pending_review") == 1


async def test_count_by_category_and_experience(services, session):
    await _submit(services, session, telegram_id=1, nickname="Alice", email="a@x.com")
    by_cat = await services.applications.count_by_category()
    by_exp = await services.applications.count_by_experience()
    assert by_cat[0][1] == 1
    assert by_exp[0][0] == "beginner"


async def test_export_rows_have_users(services, session):
    await _submit(services, session, telegram_id=1, nickname="Alice", email="a@x.com")
    rows = await services.applications.list_all_with_users()
    assert len(rows) == 1
    assert rows[0].user.nickname == "Alice"


async def test_list_approved(services, session):
    a = await _submit(services, session, telegram_id=1, nickname="Alice", email="a@x.com")
    await _submit(services, session, telegram_id=2, nickname="Bob", email="b@x.com")
    await services.applications.update_status(a.id, ApplicationStatus.APPROVED)
    await session.commit()
    approved = await services.applications.list_approved()
    assert [x.user.nickname for x in approved] == ["Alice"]
