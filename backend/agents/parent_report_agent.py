"""Parent Reporter — Sunday 8PM weekly progress report to every parent.

Aggregates the week's activity, has the LLM write a warm plain-language paragraph
(parents are not exam experts), sends it on WhatsApp with an email backup, and logs
it to parent_reports.
"""

import os
from datetime import datetime, timedelta, timezone

from graph.state import CoachingState


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _week_summary(sb, student_id: str) -> dict:
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    doubts = (sb.table("doubt_logs").select("id", count="exact")
              .eq("student_id", student_id).gte("created_at", week_ago).execute())
    tests = (sb.table("tests").select("score, total_marks, subject, created_at")
             .eq("student_id", student_id).gte("created_at", week_ago).execute()).data or []
    weak = (sb.table("weakness_map").select("concept, score")
            .eq("student_id", student_id).order("score", desc=False).limit(3).execute()).data or []
    strong = (sb.table("weakness_map").select("concept, score")
              .eq("student_id", student_id).order("score", desc=True).limit(3).execute()).data or []
    return {
        "doubts": doubts.count or 0,
        "tests_taken": len(tests),
        "avg_pct": round(
            sum((t["score"] / t["total_marks"] * 100)
                for t in tests if t.get("total_marks")) / len(tests), 1
        ) if tests else None,
        "weak_concepts": [w["concept"] for w in weak],
        "strong_concepts": [s["concept"] for s in strong],
    }


def build_report(student: dict) -> dict:
    """Compose and send one parent report. Returns delivery status."""
    from graph.llm import get_llm
    from notifications import notify

    sb = _supabase()
    summary = _week_summary(sb, student["id"])

    try:
        report_text = get_llm(temperature=0.5).invoke(
            f"Write a warm weekly progress report for the parent of {student.get('name','their child')}, "
            "a JEE/NEET student. Use simple language a non-expert parent understands. "
            "Be encouraging but honest. 4-6 sentences, no bullet points.\n"
            f"This week's data: {summary}"
        ).content.strip()
    except Exception:
        report_text = (
            f"This week {student.get('name','your child')} took {summary['tests_taken']} test(s) "
            f"and asked {summary['doubts']} doubts. Keep encouraging daily practice!"
        )

    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
    delivery = notify(
        to_phone=student.get("parent_phone"),
        to_email=student.get("email"),
        subject="Weekly Progress Report",
        body=report_text,
    )

    try:
        sb.table("parent_reports").insert({
            "student_id": student["id"],
            "report_text": report_text,
            "week_start": week_start,
            "delivery_status": "sent" if delivery.get("ok") else "failed",
        }).execute()
    except Exception as e:
        print(f"[parent_report] log insert failed: {e}")

    return {"student_id": student["id"], "delivery": delivery, "report": report_text}


def parent_report_node(state: CoachingState) -> CoachingState:
    """Graph node form (used in the post-test parallel branch as a light notifier)."""
    try:
        sb = _supabase()
        row = sb.table("students").select("*").eq("id", state["student_id"]).limit(1).execute().data
        if not row:
            return {**state, "error": "student_not_found"}
        outcome = build_report(row[0])
        return {**state, "agent_output": outcome["report"]}
    except Exception as e:
        return {**state, "error": str(e)}


def run_weekly() -> dict:
    """Scheduled Sunday 8PM job — report to every parent."""
    sb = _supabase()
    students = sb.table("students").select("*").execute().data or []
    sent = 0
    for s in students:
        try:
            if build_report(s)["delivery"].get("ok"):
                sent += 1
        except Exception as e:
            print(f"[parent_report] failed for {s.get('id')}: {e}")
    return {"students": len(students), "sent": sent}
