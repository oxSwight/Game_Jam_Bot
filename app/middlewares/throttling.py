import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject, Update


class ThrottlingMiddleware(BaseMiddleware):
    """Per-user anti-spam throttle.

    Keeps a tiny in-memory map of ``user_id -> last-allowed monotonic timestamp``
    and drops events that arrive within ``rate`` seconds of the previous one.
    Messages are silently ignored; callback queries still get an ``answer()`` so
    the client's loading spinner clears and the user gets a gentle hint.

    In-memory is intentional: throttling is best-effort per-process protection
    against accidental double-taps and floods, not a distributed rate limiter.
    A single polling instance (guaranteed by InstanceLock) makes this sufficient.
    """

    def __init__(self, rate: float = 0.5, cleanup_every: int = 500) -> None:
        self.rate = rate
        self._last_seen: dict[int, float] = {}
        self._cleanup_every = cleanup_every
        self._calls_since_cleanup = 0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user") or _extract_user(event)
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last_seen.get(user.id)
        self._maybe_cleanup(now)

        if last is not None and (now - last) < self.rate:
            inner = event.event if isinstance(event, Update) else event
            if isinstance(inner, CallbackQuery):
                await inner.answer("Не так быстро 🙂")
            # Messages: drop silently to avoid a feedback loop of warnings.
            return None

        self._last_seen[user.id] = now
        return await handler(event, data)

    def _maybe_cleanup(self, now: float) -> None:
        """Evict stale entries periodically so the map can't grow unbounded."""
        self._calls_since_cleanup += 1
        if self._calls_since_cleanup < self._cleanup_every:
            return
        self._calls_since_cleanup = 0
        cutoff = now - max(self.rate * 10, 60)
        self._last_seen = {
            uid: ts for uid, ts in self._last_seen.items() if ts > cutoff
        }


def _extract_user(event: TelegramObject):
    if isinstance(event, Update):
        event = event.event
    return getattr(event, "from_user", None)
