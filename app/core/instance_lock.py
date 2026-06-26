import sys
from pathlib import Path

from filelock import FileLock, Timeout

LOCK_PATH = Path(__file__).resolve().parent.parent.parent / ".bot.lock"


class InstanceLock:
    """Prevent multiple polling instances (causes TelegramConflict + broken FSM).

    Uses filelock for cross-platform file locking (works on Linux, macOS, Windows).
    """

    def __init__(self) -> None:
        self._lock = FileLock(str(LOCK_PATH), timeout=0)

    def acquire(self) -> None:
        try:
            self._lock.acquire()
        except Timeout:
            print(
                "ERROR: Another bot instance is already running. "
                "Stop it before starting a new one.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    def release(self) -> None:
        self._lock.release()
