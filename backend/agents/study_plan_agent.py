"""Study Plan Agent — adaptive 7-day timetable from each student's weak concepts.

F1: builds a structured 7-day plan with Groq, persists it to `study_plans` (so the
student dashboard can show it), notifies the student, and also runs weekly for all.
"""

import os
import json
from datetime import date, timedelta

from graph.state import CoachingState

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()  # Monday of this week


def build_plan(student: dict) -> dict:
    """Generate, persist and notify a structured 7-day study plan for one student.

    Returns: {student_id, week_start, days: [{day, focus, slots}], summary, plan}.
    """
    from graph.llm import get_llm
    from agents.flashcard_agent import due_cards
    from notifications import notify

    sb = _supabase()
    student_id = student["id"]
    weak = (sb.table("weakness_map").select("subject, concept, score")
            .eq("student_id", student_id).order("score", desc=False).limit(8).execute()).data or []
    due = due_cards(student_id)

    days_left = ""
    if student.get("exam_date"):
        try:
            days_left = f"{(date.fromisoformat(str(student['exam_date'])) - date.today()).days} days to exam"
        except Exception:
            pass

    weak_list = ", ".join(f"{w['concept']} ({w['subject']})" for w in weak) or "general revision"

    days = []
    summary = f"Focus this week on {weak_list}."
    try:
        # Groq (get_llm primary) → structured JSON plan.
        raw = get_llm(temperature=0.4).invoke(
            "Build a realistic 7-day (Monday–Sunday) study timetable for a JEE/NEET student.\n"
            f"{days_left}\n"
            f"Prioritise these weak concepts first: {weak_list}.\n"
            f"They also have {len(due)} flashcards due for revision — work some in.\n"
            "Give each day a short focus and 2–3 concrete slots.\n"
            'Return ONLY JSON: {"summary": "one motivating line", '
            '"days": [{"day": "Monday", "focus": "...", "slots": ["...", "..."]}, ...]}'
        ).content
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        days = data.get("days") or []
        summary = (data.get("summary") or summary).strip()
    except Exception as e:
        print(f"[study_plan] LLM/plan parse failed, using fallback: {e}")

    if not days:  # robust fallback so the dashboard always has something
        concepts = [w["concept"] for w in weak] or ["revision"]
        days = [{"day": d, "focus": concepts[i % len(concepts)],
                 "slots": [f"Study {concepts[i % len(concepts)]}", "Revise due flashcards"]}
                for i, d in enumerate(DAYS)]

    saved = {"student_id": student_id, "week_start": _week_start(),
             "days": days, "summary": summary}
    try:
        sb.table("study_plans").insert(saved).execute()
    except Exception as e:
        print(f"[study_plan] save failed: {e}")

    text = summary + "\n\n" + "\n".join(
        f"{d.get('day')}: {d.get('focus')} — " + "; ".join(d.get("slots") or []) for d in days
    )
    notify(
        to_phone=student.get("parent_phone"),
        to_email=student.get("email"),
        subject="Your Study Plan for This Week",
        body=text,
    )
    return {**saved, "plan": text}


def latest_plan(student_id: str) -> dict | None:
    """Most recent saved study plan for a student (for the dashboard)."""
    try:
        rows = (_supabase().table("study_plans").select("*")
                .eq("student_id", student_id)
                .order("created_at", desc=True).limit(1).execute().data)
        return rows[0] if rows else None
    except Exception as e:
        print(f"[study_plan] latest_plan failed: {e}")
        return None


def study_plan_node(state: CoachingState) -> CoachingState:
    try:
        sb = _supabase()
        row = sb.table("students").select("*").eq("id", state["student_id"]).limit(1).execute().data
        if not row:
            return {**state, "error": "student_not_found"}
        outcome = build_plan(row[0])
        return {**state, "agent_output": outcome["plan"]}
    except Exception as e:
        return {**state, "error": str(e)}


def run_weekly() -> dict:
    """Scheduled Monday 7AM job — rebuild plans for everyone."""
    sb = _supabase()
    students = sb.table("students").select("*").execute().data or []
    built = 0
    for s in students:
        try:
            build_plan(s)
            built += 1
        except Exception as e:
            print(f"[study_plan] failed for {s.get('id')}: {e}")
    return {"students": len(students), "built": built}
