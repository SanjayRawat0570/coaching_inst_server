"""Run a scheduled job in only one worker / instance at a time.

Every uvicorn worker (and every Railway replica) starts its own APScheduler, so
each job fires once per process. run_exclusive() lets the first one through and
makes the others skip:

  * Postgres advisory lock (SUPABASE_DB_URL, a direct / session connection —
    not the transaction pooler on port 6543, which drops session locks) — works
    across replicas.
  * Otherwise a file lock in /tmp — works across workers of one container.
  * Neither available (e.g. Windows dev): the job just runs.

The lock is held for at least MIN_HOLD_SECONDS, so a duplicate that fires a few
seconds later (workers' clocks / start times differ) still sees it taken.
"""

import logging
import os
import time
import zlib

log = logging.getLogger(__name__)

MIN_HOLD_SECONDS = 60
SKIPPED = "skipped: another worker is running it"


def _key(name: str) -> int:
    """Stable signed 32-bit key for pg_try_advisory_lock(int)."""
    k = zlib.crc32(f"smartcoaching:{name}".encode())
    return k - 2 ** 32 if k >= 2 ** 31 else k


def _hold_then(started: float) -> None:
    left = MIN_HOLD_SECONDS - (time.monotonic() - started)
    if left > 0:
        time.sleep(left)


def run_exclusive(name: str, fn):
    """fn() if this process got the job's lock, else SKIPPED."""
    started = time.monotonic()
    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url:
        conn = None
        try:
            import psycopg2
            conn = psycopg2.connect(db_url, connect_timeout=5)
            conn.autocommit = True
        except Exception as e:
            log.warning("[scheduler] no database lock for %s (%s); using a file lock", name, e)
        if conn is not None:
            try:
                cur = conn.cursor()
                cur.execute("SELECT pg_try_advisory_lock(%s)", (_key(name),))
                if not cur.fetchone()[0]:
                    return SKIPPED
                try:
                    return fn()
                finally:
                    _hold_then(started)
                    cur.execute("SELECT pg_advisory_unlock(%s)", (_key(name),))
            finally:
                conn.close()

    try:
        import fcntl
    except ImportError:  # Windows: no file locks, one dev process anyway
        return fn()
    with open(f"/tmp/smartcoaching-{name}.lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return SKIPPED
        try:
            return fn()
        finally:
            _hold_then(started)
