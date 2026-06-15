"""At-Risk Detector — nightly engagement scorer that flags dropout 7 days early.

For each student it scores 7-day engagement (activity recency, doubt/test counts,
streak, recent scores), and when risk crosses AT_RISK_THRESHOLD it writes an alert
and crafts a personalized, episodic-memory-aware intervention message.
"""

import os
from datetime import datetime, timedelta, timezone

from graph.state import CoachingState

AT_RISK_THRESHOLD = float(os.getenv("AT_RISK_THRESHOLD", "70"))


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _engagement_score(sb, student) -> tuple[float, dict]:
    """Return (risk_score 0-100, signals). Higher risk = more likely to drop out."""
    student_id = student["id"]
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    doubts = (
        sb.table("doubt_logs").select("id", count="exact")
        .eq("student_id", student_id).gte("created_at", week_ago).execute()
    )
    tests = (
        sb.table("tests").select("id", count="exact")
        .eq("student_id", student_id).gte("created_at", week_ago).execute()
    )
    doubt_count = doubts.count or 0
    test_count = tests.count or 0

    # Days since last active
    last_active = student.get("last_active")
    days_inactive = 7
    if last_active:
        try:
            la = datetime.fromisoformat(str(last_active).replace("Z", "+00:00"))
            days_inactive = (datetime.now(timezone.utc) - la).days
        except Exception:
            pass

    streak = student.get("streak_days", 0) or 0

    # Weighted risk: inactivity dominates, low activity adds, streak reduces
    risk = 0.0
    risk += min(days_inactive, 7) / 7 * 50          # up to 50 pts for inactivity
    risk += 25 if doubt_count == 0 else max(0, 15 - doubt_count * 3)
    risk += 20 if test_count == 0 else 0
    risk -= min(streak, 7) / 7 * 15                 # active streak lowers risk
    risk = max(0.0, min(100.0, risk))

    signals = {
        "days_inactive": days_inactive,
        "doubts_7d": doubt_count,
        "tests_7d": test_count,
        "streak_days": streak,
    }
    return round(risk, 1), signals


def assess_student(student: dict) -> dict:
    """Score one student and, if at risk, write an alert with a personalized message."""
    from graph.llm import get_llm
    from memory.episodic import get_milestones_text

    sb = _supabase()
    risk, signals = _engagement_score(sb, student)
    if risk < AT_RISK_THRESHOLD:
        return {"student_id": student["id"], "risk": risk, "alerted": False}

    milestones = get_milestones_text(student["id"])
    try:
        message = get_llm(temperature=0.6).invoke(
            f"A student named {student.get('name', 'the student')} is at risk of "
            f"disengaging (risk {risk}/100). Signals: {signals}.\n"
            f"Past wins to reference for motivation:\n{milestones or '(none yet)'}\n"
            "Write a warm, 2-sentence WhatsApp nudge that references a past win if "
            "available and invites them back. No preamble."
        ).content.strip()
    except Exception:
        message = (f"Hi {student.get('name', '')}, we miss you! Jump back in with a "
                   "quick 5-minute practice today — small steps add up.")

    alert = {
        "student_id": student["id"],
        "institute_id": student.get("institute_id"),
        "alert_type": "at_risk_dropout",
        "risk_score": risk,
        "message": message,
        "suggested_action": "Teacher call + assign a short confidence-building test.",
    }
    try:
        sb.table("alerts").insert(alert).execute()
    except Exception as e:
        print(f"[at_risk] alert insert failed: {e}")

    return {"student_id": student["id"], "risk": risk, "alerted": True,
            "message": message}


def at_risk_node(state: CoachingState) -> CoachingState:
    """Graph node form: assess the single student in state."""
    try:
        sb = _supabase()
        row = sb.table("students").select("*").eq("id", state["student_id"]).limit(1).execute().data
        if not row:
            return {**state, "error": "student_not_found"}
        outcome = assess_student(row[0])
        return {**state, "agent_output": outcome.get("message", "No risk detected."),
                "score": outcome["risk"]}
    except Exception as e:
        return {**state, "error": str(e)}


def run_nightly() -> dict:
    """Scheduled 11PM job — assess every student."""
    sb = _supabase()
    students = sb.table("students").select("*").execute().data or []
    alerted = 0
    for s in students:
        try:
            if assess_student(s).get("alerted"):
                alerted += 1
        except Exception as e:
            print(f"[at_risk] failed for {s.get('id')}: {e}")
    return {"assessed": len(students), "alerted": alerted}
