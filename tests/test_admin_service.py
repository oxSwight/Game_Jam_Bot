from sqlalchemy import select

from app.models.application import ApplicationStatus
from app.models.log import Log
from tests.conftest import make_payload


async def _submit(services, session, **kw):
    app = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return app


async def _actions_for(session, application_id):
    logs = (
        await session.scalars(select(Log).where(Log.application_id == application_id))
    ).all()
    return [log.action for log in logs]


async def test_approve_sets_status_and_logs(services, session):
    app = await _submit(services, session)
    await services.applications.update_status(
        app.id, ApplicationStatus.APPROVED, actor_telegram_id=111
    )
    await session.commit()

    reloaded = await services.applications.find_by_prefix(app.id[:8])
    assert reloaded.status == ApplicationStatus.APPROVED
    actions = await _actions_for(session, app.id)
    assert "application_submitted" in actions
    assert "status_approved" in actions


async def test_reject_with_reason_logged(services, session):
    app = await _submit(services, session)
    await services.applications.update_status(
        app.id, ApplicationStatus.REJECTED, actor_telegram_id=111, reason="spam"
    )
    await session.commit()

    reject_log = next(
        log
        for log in (
            await session.scalars(select(Log).where(Log.application_id == app.id))
        ).all()
        if log.action == "status_rejected"
    )
    assert reject_log.details == "reason=spam"


async def test_find_by_prefix(services, session):
    app = await _submit(services, session)
    prefix = app.id[:8]
    assert await services.applications.find_by_prefix(prefix) is not None
    assert await services.applications.find_by_prefix("deadbeef") is None


async def test_first_pending_is_fifo(services, session):
    a = await _submit(services, session, telegram_id=2001, nickname="U1", email="u1@x.com")
    await _submit(services, session, telegram_id=2002, nickname="U2", email="u2@x.com")
    assert await services.applications.count_pending() == 2
    # oldest first
    head = await services.applications.first_pending()
    assert head.id == a.id


async def test_first_pending_empty(services):
    assert await services.applications.first_pending() is None


async def test_update_status_unknown_id_returns_none(services):
    assert await services.applications.update_status(
        "does-not-exist", ApplicationStatus.APPROVED
    ) is None
