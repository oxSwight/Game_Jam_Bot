from types import SimpleNamespace

from app.middlewares.throttling import ThrottlingMiddleware


class _User(SimpleNamespace):
    pass


async def _handler(event, data):
    data["calls"] = data.get("calls", 0) + 1
    return "ok"


async def test_second_rapid_call_is_dropped():
    mw = ThrottlingMiddleware(rate=10.0)
    user = _User(id=1)
    data = {"event_from_user": user, "calls": 0}

    r1 = await mw(_handler, event=SimpleNamespace(), data=data)
    r2 = await mw(_handler, event=SimpleNamespace(), data=data)

    assert r1 == "ok"
    assert r2 is None  # throttled
    assert data["calls"] == 1


async def test_different_users_not_throttled():
    mw = ThrottlingMiddleware(rate=10.0)
    d1 = {"event_from_user": _User(id=1)}
    d2 = {"event_from_user": _User(id=2)}
    assert await mw(_handler, event=SimpleNamespace(), data=d1) == "ok"
    assert await mw(_handler, event=SimpleNamespace(), data=d2) == "ok"


async def test_allowed_again_after_rate_window():
    mw = ThrottlingMiddleware(rate=0.01)
    user = _User(id=7)
    data = {"event_from_user": user}
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"
    # simulate the window elapsing by ageing the recorded timestamp
    mw._last_seen[7] -= 1.0
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"


async def test_no_user_passes_through():
    mw = ThrottlingMiddleware(rate=10.0)
    assert await mw(_handler, event=SimpleNamespace(), data={}) == "ok"
