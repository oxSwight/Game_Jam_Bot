from types import SimpleNamespace

from app.middlewares.throttling import ThrottlingMiddleware


class _User(SimpleNamespace):
    pass


async def _handler(event, data):
    data["calls"] = data.get("calls", 0) + 1
    return "ok"


async def test_burst_allows_quick_taps_then_throttles():
    # burst=3: three quick taps pass, the fourth (bucket empty) is dropped.
    mw = ThrottlingMiddleware(refill_rate=0.0, burst=3)
    user = _User(id=1)
    data = {"event_from_user": user, "calls": 0}

    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"
    assert await mw(_handler, event=SimpleNamespace(), data=data) is None  # bucket empty
    assert data["calls"] == 3


async def test_different_users_not_throttled():
    mw = ThrottlingMiddleware(refill_rate=0.0, burst=1)
    d1 = {"event_from_user": _User(id=1)}
    d2 = {"event_from_user": _User(id=2)}
    assert await mw(_handler, event=SimpleNamespace(), data=d1) == "ok"
    assert await mw(_handler, event=SimpleNamespace(), data=d2) == "ok"


async def test_bucket_refills_over_time():
    mw = ThrottlingMiddleware(refill_rate=10.0, burst=1)
    user = _User(id=7)
    data = {"event_from_user": user}
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"  # spends token
    # Rewind 'last' so the middleware thinks time passed → tokens refill.
    mw._last[7] -= 1.0
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"


async def test_no_user_passes_through():
    mw = ThrottlingMiddleware(burst=1)
    assert await mw(_handler, event=SimpleNamespace(), data={}) == "ok"


async def test_sustained_flood_triggers_shadowban():
    # No refill, tiny burst, ban after 3 over-budget strikes.
    mw = ThrottlingMiddleware(refill_rate=0.0, burst=1, spam_strikes=3, ban_seconds=300.0)
    user = _User(id=99)
    data = {"event_from_user": user}

    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"  # burst
    for _ in range(3):  # over-budget strikes → shadowban
        assert await mw(_handler, event=SimpleNamespace(), data=data) is None
    assert 99 in mw._banned_until
    # Now even a well-spaced action is dropped silently while banned.
    mw._last[99] -= 1000.0
    assert await mw(_handler, event=SimpleNamespace(), data=data) is None


async def test_shadowban_lifts_after_window():
    mw = ThrottlingMiddleware(refill_rate=0.0, burst=1, spam_strikes=2, ban_seconds=300.0)
    user = _User(id=5)
    data = {"event_from_user": user}
    await mw(_handler, event=SimpleNamespace(), data=data)  # burst
    for _ in range(2):
        await mw(_handler, event=SimpleNamespace(), data=data)
    assert 5 in mw._banned_until
    # Age the ban into the past → next call is allowed and clears the ban.
    mw._banned_until[5] -= 1000.0
    assert await mw(_handler, event=SimpleNamespace(), data=data) == "ok"
    assert 5 not in mw._banned_until
