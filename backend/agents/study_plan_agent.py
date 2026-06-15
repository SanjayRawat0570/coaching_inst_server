"""Study Plan Agent — Monday 7AM adaptive weekly timetable rebuild.

Rebuilds a personalized week from the student's weakest concepts, exam date, and due
flashcards, and pushes the plan to the student over WhatsApp/email.
"""

import os
from datetime import date

from graph.state import CoachingState


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def build_plan(student: dict) -> dict:
    """Generate (and notify) a 7-day study plan for one student."""
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
    try:
        plan_text = get_llm(temperature=0.4).invoke(
            f"Build a realistic 7-day (Mon-Sun) study timetable for a JEE/NEET student. "
            f"{days_left}. Prioritize these weak concepts: {weak_list}. "
            f"They have {len(due)} flashcards due for revision. "
            "Give 2-3 focused slots per day. Keep it motivating and concise."
        ).content.strip()
    except Exception:
        plan_text = f"This week focus on: {weak_list}. Revise {len(due)} due flashcards daily."

    notify(
        to_phone=student.get("parent_phone"),
        to_email=student.get("email"),
        subject="Your Study Plan for This Week",
        body=plan_text,
    )
    return {"student_id": student_id, "plan": plan_text}


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
