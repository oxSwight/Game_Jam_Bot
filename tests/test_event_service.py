import pytest

from app.models.application import ApplicationStatus
from app.models.event import EventStatus
from app.services.event import EventError
from tests.conftest import make_payload


async def _approved(services, session, n):
    """Register + approve n players, returning the ORM Application rows (not the
    ApplicationRead DTOs) so callers can mutate them."""
    ids = []
    for i in range(n):
        read = await services.applications.submit_registration(
            make_payload(telegram_id=100 + i, nickname=f"Player{i}", email=f"p{i}@x.com")
        )
        await services.applications.update_status(read.id, ApplicationStatus.APPROVED)
        ids.append(read.id)
    await session.commit()
    return [await services.applications.find_by_prefix(app_id) for app_id in ids]


async def test_create_event_and_duplicate(services, session):
    ev = await services.events.create_event("Winter Jam")
    await session.commit()
    assert ev.id is not None
    with pytest.raises(EventError):
        await services.events.create_event("Winter Jam")


async def test_create_event_too_short(services):
    with pytest.raises(EventError):
        await services.events.create_event("x")


async def test_activate_deactivates_previous(services, session):
    a = await services.events.create_event("Jam A")
    b = await services.events.create_event("Jam B")
    await session.commit()
    await services.events.set_status(a, EventStatus.ACTIVE)
    await services.events.set_status(b, EventStatus.ACTIVE)
    await session.commit()
    active = await services.events.events.get_active()
    assert active.id == b.id  # only one active at a time


async def test_create_team_duplicate_within_event(services, session):
    ev = await services.events.create_event("Jam")
    await session.commit()
    await services.events.create_team(ev, "Red")
    await session.commit()
    with pytest.raises(EventError):
        await services.events.create_team(ev, "Red")


async def test_auto_balance_round_robin(services, session):
    ev = await services.events.create_event("Jam")
    await session.commit()
    await services.events.create_team(ev, "Red")
    await services.events.create_team(ev, "Blue")
    await session.commit()
    await _approved(services, session, 5)

    assigned, teams = await services.events.auto_balance(ev)
    await session.commit()
    assert assigned == 5
    assert teams == 2

    team_list = await services.events.teams.list_for_event(ev.id)
    sizes = sorted(len(t.members) for t in team_list)
    assert sizes == [2, 3]  # balanced


async def test_auto_balance_without_teams_errors(services, session):
    ev = await services.events.create_event("Jam")
    await session.commit()
    with pytest.raises(EventError):
        await services.events.auto_balance(ev)


async def test_assign_member_logs(services, session):
    ev = await services.events.create_event("Jam")
    await session.commit()
    team = await services.events.create_team(ev, "Red")
    await session.commit()
    (app,) = await _approved(services, session, 1)
    await services.events.assign_member(app, team)
    await session.commit()

    logs = await services.applications.logs_for(app.id)
    assert any(log.action == "team_assigned" for log in logs)
