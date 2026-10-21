"""Background jobs for slow AI work (test generation, grading, handwriting checks).

POST endpoints called with ?job=1 return {"job_id", "status": "queued"} at once
and the work runs on a small thread pool. GET /jobs/{id} returns
{id, kind, status: queued|running|done|failed, result, error}.

Status lives in the Supabase `jobs` table (migrations/2026-10-22_jobs.sql), so a
page refresh can pick a job up again. Until that migration has run, jobs are kept
in memory (lost on restart). A job still queued/running after JOB_STALE_SECONDS
(the process restarted mid-job) is reported as failed.
"""

import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import HTTPException

log = logging.getLogger(__name__)

FRIENDLY_ERROR = "Something went wrong while working on this. Please try again."
JOB_STALE_SECONDS = 15 * 60

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_memory: dict[str, dict] = {}
_memory_lock = threading.Lock()


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=int(os.getenv("JOB_WORKERS", "2")),
                                           thread_name_prefix="job")
        return _executor


def shutdown() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _db():
    from auth.supabase_auth import get_supabase
    return get_supabase()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── storage: Supabase table, memory fallback ──────────────────────────────────
def _save(job: dict) -> None:
    try:
        _db().table("jobs").upsert(dict(job)).execute()
        return
    except Exception as e:
        log.warning("jobs table unavailable (run migrations/2026-10-22_jobs.sql?): %s", e)
    with _memory_lock:
        _memory[job["id"]] = dict(job)


def _load(job_id: str) -> dict | None:
    with _memory_lock:
        if job_id in _memory:
            return dict(_memory[job_id])
    try:
        rows = _db().table("jobs").select("*").eq("id", job_id).limit(1).execute().data
        return rows[0] if rows else None
    except Exception as e:
        log.warning("jobs lookup failed: %s", e)
        return None


def _update(job: dict, **fields) -> None:
    job.update(fields, updated_at=_now())
    _save(job)


# ── public API ────────────────────────────────────────────────────────────────
def submit(kind: str, owner_id: str, fn, *args, institute_id: str | None = None, **kwargs) -> dict:
    """Queue fn(*args, **kwargs). Returns the queued job (what the endpoint sends)."""
    job = {"id": str(uuid.uuid4()), "kind": kind, "status": "queued", "owner_id": owner_id,
           "institute_id": institute_id, "result": None, "error": None,
           "created_at": _now(), "updated_at": _now()}
    _save(job)
    _pool().submit(_run, job, fn, args, kwargs)
    return {"job_id": job["id"], "status": "queued", "kind": kind}


def _run(job: dict, fn, args, kwargs) -> None:
    started = time.perf_counter()
    _update(job, status="running")
    try:
        result = fn(*args, **kwargs)
    except HTTPException as e:  # the same message the synchronous endpoint returns
        _update(job, status="failed", error=str(e.detail))
    except Exception as e:  # the real reason is logged, never sent
        log.exception("job %s (%s) failed: %s", job["id"], job["kind"], e)
        _update(job, status="failed", error=FRIENDLY_ERROR)
    else:
        _update(job, status="done", result=result)
    log.info("job %s (%s) %s in %.1f s", job["id"], job["kind"], job["status"],
             time.perf_counter() - started)


def get(job_id: str, owner_id: str) -> dict | None:
    """The job if it belongs to owner_id, else None (callers answer 404)."""
    job = _load(job_id)
    if not job or job.get("owner_id") != owner_id:
        return None
    if job["status"] in ("queued", "running") and _age(job) > JOB_STALE_SECONDS:
        job.update(status="failed", error="This job was interrupted. Please start it again.")
    return {k: job.get(k) for k in ("id", "kind", "status", "result", "error",
                                   "created_at", "updated_at")}


def _age(job: dict) -> float:
    try:
        ts = datetime.fromisoformat(str(job.get("updated_at")).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (TypeError, ValueError):
        return 0.0
