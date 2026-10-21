"""Per-user rate limits that protect the free LLM / RAG quotas. In memory, per process.

Limits are "count/seconds" strings, overridable by env:
    RATE_LIMIT_DOUBT     default 8/60    (doubts per student per minute)
    RATE_LIMIT_TEST_GEN  default 5/60    (test generations per user per minute)
"""

import os
import threading
import time
from collections import deque

DEFAULTS = {"doubt": "8/60", "test_gen": "5/60"}
MESSAGES = {
    "doubt": "You're asking very fast. Please wait a few seconds.",
    "test_gen": "You're generating tests very fast. Please wait a minute and try again.",
}

_hits: dict[tuple[str, str], deque] = {}
_lock = threading.Lock()


def _limit(action: str) -> tuple[int, float]:
    raw = os.getenv(f"RATE_LIMIT_{action.upper()}", DEFAULTS[action])
    count, seconds = raw.split("/")
    return int(count), float(seconds)


def allow(action: str, user_id: str) -> bool:
    """Record one attempt; False when the user is over the limit (not recorded)."""
    count, window = _limit(action)
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault((action, user_id or "?"), deque())
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= count:
            return False
        q.append(now)
        return True


def message(action: str) -> str:
    return MESSAGES[action]


def reset() -> None:
    with _lock:
        _hits.clear()
