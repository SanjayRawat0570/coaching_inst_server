"""APScheduler job registration — no Celery, no Redis.

  Nightly 11PM  -> at_risk_agent.run_nightly      (flag dropouts 7 days early)
  Sunday 8PM    -> parent_report_agent.run_weekly  (WhatsApp progress to parents)
  Monday 7AM    -> study_plan_agent.run_weekly      (rebuild weekly timetables)
  Every 5 min   -> flashcard reminder checker
"""

import os

from apscheduler.schedulers.background import BackgroundScheduler

_scheduler: BackgroundScheduler | None = None


def _nightly_at_risk():
    from agents.at_risk_agent import run_nightly
    print("[scheduler] at-risk nightly:", run_nightly())


def _weekly_parent_reports():
    from agents.parent_report_agent import run_weekly
    print("[scheduler] parent reports:", run_weekly())


def _weekly_study_plans():
    from agents.study_plan_agent import run_weekly
    print("[scheduler] study plans:", run_weekly())


def _flashcard_reminders():
    """Notify students who have flashcards due now."""
    from supabase import create_client
    from agents.flashcard_agent import due_cards
    from notifications import notify

    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))
    students = sb.table("students").select("id, name, email, parent_phone").execute().data or []
    for s in students:
        cards = due_cards(s["id"])
        if cards:
            notify(
                to_phone=s.get("parent_phone"),
                to_email=s.get("email"),
                subject="Flashcards due",
                body=f"{s.get('name','You')} have {len(cards)} flashcards to revise today.",
            )


def start_scheduler() -> BackgroundScheduler:
    """Create, register jobs on, and start the background scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(_nightly_at_risk, "cron", hour=23, minute=0, id="at_risk_nightly")
    scheduler.add_job(_weekly_parent_reports, "cron", day_of_week="sun", hour=20,
                      minute=0, id="parent_reports_weekly")
    scheduler.add_job(_weekly_study_plans, "cron", day_of_week="mon", hour=7,
                      minute=0, id="study_plans_weekly")
    scheduler.add_job(_flashcard_reminders, "interval", minutes=5,
                      id="flashcard_reminders")
    scheduler.start()
    _scheduler = scheduler
    print("[scheduler] started with jobs:", [j.id for j in scheduler.get_jobs()])
    return scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
