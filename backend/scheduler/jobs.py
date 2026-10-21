"""APScheduler job registration — no Celery, no Redis.

  Nightly 11PM  -> at_risk_agent.run_nightly      (flag dropouts 7 days early)
  Nightly 9PM   -> inactivity_alert_agent.run_nightly (F7: email teacher+parent on 3-day no-login / skipped test)
  Nightly 2AM   -> doubt_cluster_agent.run_nightly (F3: cluster similar doubts)
  Sunday 8PM    -> parent_report_agent.run_weekly  (email progress to parents)
  Monday 7AM    -> study_plan_agent.run_weekly      (rebuild weekly timetables)
  Every 5 min   -> flashcard reminder checker (cron */5, so workers fire together)

Each job runs through scheduler.locks.run_exclusive (one worker / replica runs it,
the others skip), in the scheduler's own threads — never on the API's. Duration and
outcome are logged and kept in LAST_RUNS (for the admin health card).
"""

import threading
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from scheduler.locks import SKIPPED, run_exclusive

_scheduler: BackgroundScheduler | None = None

LAST_RUNS: dict[str, dict] = {}
_runs_lock = threading.Lock()


def _guarded(job_id: str, fn):
    """The job as the scheduler runs it: exclusive, timed, never raising."""
    def run():
        started, t0 = datetime.now(timezone.utc).isoformat(), time.perf_counter()
        try:
            out = run_exclusive(job_id, fn)
            status = "skipped" if out == SKIPPED else "ok"
        except Exception as e:  # a failing job must not kill the scheduler thread
            print(f"[scheduler] {job_id} failed: {e}")
            status = "failed"
        duration = round(time.perf_counter() - t0, 2)
        with _runs_lock:
            LAST_RUNS[job_id] = {"started_at": started, "duration_s": duration, "status": status}
        print(f"[scheduler] {job_id} {status} in {duration} s")
    run.__name__ = f"guarded_{job_id}"
    return run


def _nightly_at_risk():
    from agents.at_risk_agent import run_nightly
    print("[scheduler] at-risk nightly:", run_nightly())


def _weekly_parent_reports():
    from agents.parent_report_agent import run_weekly
    print("[scheduler] parent reports:", run_weekly())


def _weekly_study_plans():
    from agents.study_plan_agent import run_weekly
    print("[scheduler] study plans:", run_weekly())


def _nightly_doubt_clusters():
    from agents.doubt_cluster_agent import run_nightly
    print("[scheduler] doubt clusters:", run_nightly())


def _nightly_inactivity_alerts():
    from agents.inactivity_alert_agent import run_nightly
    print("[scheduler] inactivity alerts:", run_nightly())


def _flashcard_reminders():
    """Notify students who have flashcards due now."""
    from auth.supabase_auth import get_supabase
    from agents.flashcard_agent import due_counts_by_student
    from notifications import notify

    # One paged read of all due cards instead of one query per student.
    due = due_counts_by_student()
    if not due:
        return
    sb = get_supabase()
    ids, students = list(due), []
    for i in range(0, len(ids), 200):  # chunks keep the id list's URL short
        students += (sb.table("students").select("id, name, email")
                     .in_("id", ids[i:i + 200]).execute().data or [])
    for s in students:
        if due.get(s["id"]):
            notify(
                to_email=s.get("email"),
                subject="Flashcards due",
                body=f"{s.get('name','You')} have {due[s['id']]} flashcards to revise today.",
            )


def start_scheduler() -> BackgroundScheduler:
    """Create, register jobs on, and start the background scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    # One run at a time per job; a run missed while busy happens once, late.
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata", job_defaults={
        "coalesce": True, "max_instances": 1, "misfire_grace_time": 300})
    jobs = [
        ("at_risk_nightly", _nightly_at_risk, dict(hour=23, minute=0)),
        ("parent_reports_weekly", _weekly_parent_reports, dict(day_of_week="sun", hour=20, minute=0)),
        ("study_plans_weekly", _weekly_study_plans, dict(day_of_week="mon", hour=7, minute=0)),
        ("doubt_clusters_nightly", _nightly_doubt_clusters, dict(hour=2, minute=0)),
        ("inactivity_alerts_nightly", _nightly_inactivity_alerts, dict(hour=21, minute=0)),
        # cron, not interval: an interval counts from each process's start, so
        # several workers would fire minutes apart and the lock couldn't pair them.
        ("flashcard_reminders", _flashcard_reminders, dict(minute="*/5")),
    ]
    for job_id, fn, when in jobs:
        scheduler.add_job(_guarded(job_id, fn), "cron", id=job_id, **when)
    scheduler.start()
    _scheduler = scheduler
    print("[scheduler] started with jobs:", [j.id for j in scheduler.get_jobs()])
    return scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
