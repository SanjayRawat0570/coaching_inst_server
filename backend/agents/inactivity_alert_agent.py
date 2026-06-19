"""Inactivity & Skipped-Test Alerter (F7).

Nightly rule-based check: for each student, raise an alert and email the student's
teacher(s) + parent when either is true:
  • no login / activity for >= INACTIVE_DAYS days, OR
  • an assigned ('ready') test is past its due date and was never taken.

Distinct from at_risk_agent (which is a weighted engagement *score*) — this is the
hard, explainable rule the spec asks for, and it actually sends the emails.
"""

import os
from datetime import datetime, timezone, timedelta, date

INACTIVE_DAYS = int(os.getenv("INACTIVE_ALERT_DAYS", "3"))


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _days_since_active(student: dict) -> int:
    """Days since the student was last seen. Falls back to signup date so brand-new
    accounts get a grace period instead of an immediate alert."""
    ref = student.get("last_active") or student.get("created_at")
    if not ref:
        return 0  # no data at all → don't alert
    try:
        dt = datetime.fromisoformat(str(ref).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 0


def _skipped_tests(sb, student_id: str) -> list[dict]:
    """Assigned ('ready') tests whose due date has passed and were never taken."""
    today = date.today().isoformat()
    try:
        return (sb.table("tests")
                .select("id, subject, due_date")
                .eq("student_id", student_id).eq("status", "ready")
                .lt("due_date", today).execute().data) or []
    except Exception as e:
        print(f"[inactivity] skipped-test lookup failed: {e}")
        return []


def _teacher_emails(sb, institute_id) -> list[str]:
    """Emails of teachers in the student's institute (None matches None)."""
    try:
        res = sb.auth.admin.list_users()
        users = res if isinstance(res, list) else getattr(res, "users", []) or []
        out = []
        for u in users:
            md = getattr(u, "user_metadata", None) or {}
            if md.get("role") == "teacher" and (md.get("institute_id") or None) == (institute_id or None):
                if getattr(u, "email", None):
                    out.append(u.email)
        return out
    except Exception as e:
        print(f"[inactivity] teacher lookup failed: {e}")
        return []


def assess_student(student: dict) -> dict:
    """Apply the F7 rule to one student; email teacher+parent and log an alert if hit."""
    from notifications import notify

    sb = _supabase()
    name = student.get("name") or "Your student"
    reasons = []

    days = _days_since_active(student)
    if days >= INACTIVE_DAYS:
        reasons.append(f"no login for {days} days")

    skipped = _skipped_tests(sb, student["id"])
    if skipped:
        subs = ", ".join(sorted({s.get("subject") or "a test" for s in skipped}))
        reasons.append(f"{len(skipped)} assigned test(s) past due and not taken ({subs})")

    if not reasons:
        return {"student_id": student["id"], "alerted": False, "reasons": []}

    why = " and ".join(reasons)
    body = (f"Heads up about {name}: {why}. "
            "A quick nudge today can get them back on track.")

    # Email the parent (WhatsApp first if a phone is on file, else email).
    parent_results = []
    if student.get("parent_email") or student.get("parent_phone"):
        parent_results.append(notify(
            to_phone=student.get("parent_phone"),
            to_email=student.get("parent_email"),
            subject=f"Check in on {name}",
            body=body,
        ))

    # Email each teacher in the institute.
    teacher_emails = _teacher_emails(sb, student.get("institute_id"))
    teacher_results = [notify(to_email=e, subject=f"Student needs attention: {name}", body=body)
                       for e in teacher_emails]

    # Log an alert row so it also surfaces on the teacher dashboard.
    try:
        sb.table("alerts").insert({
            "student_id": student["id"],
            "institute_id": student.get("institute_id"),
            "alert_type": "inactivity_or_skipped_test",
            "message": body,
            "suggested_action": "Call the student; re-assign or extend the test deadline.",
        }).execute()
    except Exception as e:
        print(f"[inactivity] alert insert failed: {e}")

    return {"student_id": student["id"], "alerted": True, "reasons": reasons,
            "teachers_notified": teacher_emails,
            "parent_notified": bool(parent_results)}


def run_nightly() -> dict:
    """Scheduled job — check every student, email teacher+parent on a hit."""
    sb = _supabase()
    students = sb.table("students").select("*").execute().data or []
    details = []
    for s in students:
        try:
            r = assess_student(s)
            if r.get("alerted"):
                details.append({"name": s.get("name"), "email": s.get("email"),
                                "reasons": r["reasons"]})
        except Exception as e:
            print(f"[inactivity] failed for {s.get('id')}: {e}")
    return {"assessed": len(students), "alerted": len(details), "details": details}
