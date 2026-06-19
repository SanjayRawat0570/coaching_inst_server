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
    prof = (sb.table("students").select("streak_days")
            .eq("id", student_id).limit(1).execute()).data or []
    return {
        "doubts": doubts.count or 0,
        "tests_taken": len(tests),
        "avg_pct": round(
            sum((t["score"] / t["total_marks"] * 100)
                for t in tests if t.get("total_marks")) / len(tests), 1
        ) if tests else None,
        "streak_days": (prof[0].get("streak_days") if prof else 0) or 0,
        "weak_concepts": [w["concept"] for w in weak],
        "strong_concepts": [s["concept"] for s in strong],
    }


def _report_html(name: str, report_text: str, summary: dict) -> str:
    """F8: parent email body — the narrative plus the headline scores/doubts/streak."""
    avg = f"{summary['avg_pct']}%" if summary.get("avg_pct") is not None else "—"
    return (
        f"<h2 style='margin:0 0 8px'>Weekly Progress — {name}</h2>"
        f"<p style='line-height:1.5'>{report_text}</p>"
        "<ul style='line-height:1.7'>"
        f"<li><b>Tests taken:</b> {summary.get('tests_taken', 0)}</li>"
        f"<li><b>Average score:</b> {avg}</li>"
        f"<li><b>Doubts asked:</b> {summary.get('doubts', 0)}</li>"
        f"<li><b>Current streak:</b> {summary.get('streak_days', 0)} day(s)</li>"
        "</ul>"
    )


def build_report(student: dict) -> dict:
    """Compose and send one parent report. Returns delivery status.

    F8: emails the PARENT via Resend (the primary channel), and also sends a
    WhatsApp nudge if a parent phone is on file. Includes scores, doubts and streak.
    """
    from graph.llm import get_llm
    from notifications import send_email, send_whatsapp

    sb = _supabase()
    summary = _week_summary(sb, student["id"])
    name = student.get("name", "their child")

    try:
        report_text = get_llm(temperature=0.5).invoke(
            f"Write a warm weekly progress report for the parent of {name}, "
            "a JEE/NEET student. Use simple language a non-expert parent understands. "
            "Be encouraging but honest. 4-6 sentences, no bullet points.\n"
            f"This week's data (scores, doubts, streak): {summary}"
        ).content.strip()
    except Exception:
        report_text = (
            f"This week {name} took {summary['tests_taken']} test(s), "
            f"asked {summary['doubts']} doubts, and is on a {summary['streak_days']}-day streak. "
            "Keep encouraging daily practice!"
        )

    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()

    # F8: email the PARENT via Resend; WhatsApp is a bonus channel if a phone exists.
    parent_email = student.get("parent_email")
    email_res = (send_email(parent_email, f"Weekly Progress Report — {name}",
                            _report_html(name, report_text, summary))
                 if parent_email else {"ok": False, "channel": "email", "error": "no parent email on file"})
    wa_res = (send_whatsapp(student.get("parent_phone"), report_text)
              if student.get("parent_phone") else {"ok": False, "channel": "whatsapp", "error": "no phone"})
    delivered = bool(email_res.get("ok") or wa_res.get("ok"))
    delivery = email_res if email_res.get("ok") else (wa_res if wa_res.get("ok") else email_res)

    try:
        sb.table("parent_reports").insert({
            "student_id": student["id"],
            "report_text": report_text,
            "week_start": week_start,
            "delivery_status": "sent" if delivered else "failed",
        }).execute()
    except Exception as e:
        print(f"[parent_report] log insert failed: {e}")

    return {"student_id": student["id"], "delivery": delivery,
            "channels": {"email": email_res, "whatsapp": wa_res}, "report": report_text}


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
