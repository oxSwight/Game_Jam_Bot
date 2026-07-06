import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """Per-user anti-spam throttle: a token bucket with an escalating shadowban.

    A hard "one action per second" limit made the inline questionnaire painful —
    legitimate quick taps (selecting several roles, tapping the captcha right after
    /register) were silently dropped. A token bucket fixes that while still
    stopping floods:

    * Each user has a bucket of ``burst`` tokens, refilled at ``refill_rate``
      tokens/second. A normal human taps a handful of buttons, pauses to read,
      and the bucket refills — they never run dry.
    * A flood script empties the bucket and then spends every further action
      over-budget. Each over-budget action is a strike; after ``spam_strikes`` of
      them the user is **shadowbanned** for ``ban_seconds`` — every update dropped
      with no reply at all, so the script gets zero feedback to adapt to.
    * A well-paced action decays one strike, so the odd fast burst never snowballs
      into a ban.

    In-memory is intentional (a single polling instance is guaranteed by
    InstanceLock); this is best-effort per-process protection, not a distributed
    rate limiter.
    """

    def __init__(
        self,
        refill_rate: float = 2.0,
        burst: int = 6,
        spam_strikes: int = 12,
        ban_seconds: float = 300.0,
        cleanup_every: int = 500,
    ) -> None:
        self.refill_rate = refill_rate
        self.burst = float(burst)
        self.spam_strikes = spam_strikes
        self.ban_seconds = ban_seconds
        self._tokens: dict[int, float] = {}
        self._last: dict[int, float] = {}
        self._strikes: dict[int, int] = {}
        self._banned_until: dict[int, float] = {}
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

        uid = user.id
        now = time.monotonic()
        self._maybe_cleanup(now)

        banned_until = self._banned_until.get(uid)
        if banned_until is not None:
            if now < banned_until:
                return None  # silent: shadowbanned, no feedback whatsoever
            self._banned_until.pop(uid, None)
            self._strikes.pop(uid, None)
            self._tokens.pop(uid, None)
            self._last.pop(uid, None)

        # Refill the bucket by however much time has passed since the last action.
        tokens = self._tokens.get(uid, self.burst)
        last = self._last.get(uid)
        if last is not None:
            tokens = min(self.burst, tokens + (now - last) * self.refill_rate)
        self._last[uid] = now

        if tokens >= 1.0:
            self._tokens[uid] = tokens - 1.0
            if self._strikes.get(uid):
                self._strikes[uid] -= 1
            return await handler(event, data)

        # Over budget: keep the (empty) bucket, record a strike, maybe shadowban.
        self._tokens[uid] = tokens
        strikes = self._strikes.get(uid, 0) + 1
        self._strikes[uid] = strikes
        if strikes >= self.spam_strikes:
            self._banned_until[uid] = now + self.ban_seconds
            logger.warning(
                "shadowbanning user %s for %.0fs after %d over-budget actions",
                uid,
                self.ban_seconds,
                strikes,
            )
        return None  # silent drop

    def _maybe_cleanup(self, now: float) -> None:
        """Evict stale entries periodically so the maps can't grow unbounded."""
        self._calls_since_cleanup += 1
        if self._calls_since_cleanup < self._cleanup_every:
            return
        self._calls_since_cleanup = 0
        cutoff = now - 60.0
        self._last = {uid: ts for uid, ts in self._last.items() if ts > cutoff}
        self._banned_until = {
            uid: until for uid, until in self._banned_until.items() if until > now
        }
        self._tokens = {uid: tk for uid, tk in self._tokens.items() if uid in self._last}
        self._strikes = {uid: n for uid, n in self._strikes.items() if uid in self._last}


def _extract_user(event: TelegramObject):
    if isinstance(event, Update):
        event = event.event
    return getattr(event, "from_user", None)
