"""Tiny per-process TTL cache for the heavy read endpoints (dashboards, leaderboard,
concept map). No extra dependency.

Keys are tuples whose first item is the kind (e.g. "leaderboard") and that always
include the institute / student and role the data belongs to, so cached data is
never shared across institutes or roles. Writes that change the data call one of
the invalidate_* helpers; the TTL bounds staleness for everything else (e.g. rows
written by the scheduler). Per process: with several workers each has its own.
"""

import os
import threading
import time
from typing import Any, Callable, Hashable

_store: dict[tuple, tuple[float, Any]] = {}
_lock = threading.Lock()
MAX_ENTRIES = 5000

# Kinds scoped to an institute (key[1] is the institute id, or None for the
# "no institute / platform-wide" view).
INSTITUTE_KINDS = ("leaderboard", "teacher_overview", "admin_analytics")


def get_or_set(key: tuple[Hashable, ...], ttl: float, compute: Callable[[], Any]) -> Any:
    if os.getenv("CACHE_DISABLED") == "1":  # benchmarking / debugging
        return compute()
    now = time.monotonic()
    with _lock:
        hit = _store.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = compute()
    with _lock:
        if len(_store) >= MAX_ENTRIES:
            _store.clear()
        _store[key] = (now + ttl, value)
    return value


def _drop(match: Callable[[tuple], bool]) -> None:
    with _lock:
        for k in [k for k in _store if match(k)]:
            del _store[k]


def invalidate_institute(institute_id: str | None) -> None:
    """Something changed for an institute's students (XP, scores, doubts, alerts):
    drop its dashboards plus the unscoped views that include everyone."""
    _drop(lambda k: k[0] in INSTITUTE_KINDS and (k[-1] == institute_id or k[-1] is None))


def invalidate_kind(kind: str) -> None:
    _drop(lambda k: k[0] == kind)


def invalidate_student(student_id: str) -> None:
    _drop(lambda k: k[0] == "concept_map" and k[-1] == student_id)


def clear() -> None:
    with _lock:
        _store.clear()
