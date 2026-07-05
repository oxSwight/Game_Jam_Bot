from app.models.application import ApplicationStatus
from tests.conftest import make_payload


async def _submit(services, session, **kw):
    app = await services.applications.submit_registration(make_payload(**kw))
    await session.commit()
    return app


async def test_approve_sets_status_and_logs(services, session):
    app = await _submit(services, session)
    await services.applications.update_status(
        app.id, ApplicationStatus.APPROVED, actor_telegram_id=111
    )
    await session.commit()

    reloaded = await services.applications.find_by_prefix(app.id[:8])
    assert reloaded.status == ApplicationStatus.APPROVED
    logs = await services.applications.logs_for(app.id)
    actions = [log.action for log in logs]
    assert "application_submitted" in actions
    assert "status_approved" in actions


async def test_reject_with_reason_logged(services, session):
    app = await _submit(services, session)
    await services.applications.update_status(
        app.id, ApplicationStatus.REJECTED, actor_telegram_id=111, reason="spam"
    )
    await session.commit()

    logs = await services.applications.logs_for(app.id)
    reject_log = next(log for log in logs if log.action == "status_rejected")
    assert reject_log.details == "reason=spam"


async def test_find_by_prefix_and_delete(services, session):
    app = await _submit(services, session)
    prefix = app.id[:8]
    assert await services.applications.find_by_prefix(prefix) is not None

    deleted = await services.applications.delete_by_prefix(prefix)
    await session.commit()
    assert deleted is not None
    assert await services.applications.find_by_prefix(prefix) is None


async def test_set_layer_score_validates_and_persists(services, session):
    app = await _submit(services, session)
    updated = await services.applications.set_layer_score(
        app.id, 1, 87.5, actor_telegram_id=111
    )
    await session.commit()
    assert updated.layer_1_team_result == 87.5
    assert updated.total_score == 87.5


async def test_list_pending_pagination(services, session):
    for i in range(7):
        await _submit(services, session, telegram_id=2000 + i, nickname=f"U{i}",
                      email=f"u{i}@example.com")
    assert await services.applications.count_pending() == 7
    page1 = await services.applications.list_pending(limit=5, offset=0)
    page2 = await services.applications.list_pending(limit=5, offset=5)
    assert len(page1) == 5
    assert len(page2) == 2


async def test_update_status_unknown_id_returns_none(services):
    assert await services.applications.update_status(
        "does-not-exist", ApplicationStatus.APPROVED
    ) is None
