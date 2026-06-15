"""Flashcard Agent — SM-2 spaced repetition.

Generates flashcards for concepts a student got wrong, schedules reviews with the
SM-2 algorithm, and surfaces cards that are due (for the daily reminder job).
"""

import os
from datetime import date, timedelta

from graph.state import CoachingState


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def sm2(ease_factor: float, interval_days: int, repetitions: int, quality: int):
    """SM-2 update. quality 0-5 (>=3 = correct recall). Returns new schedule fields."""
    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        if repetitions == 0:
            interval_days = 1
        elif repetitions == 1:
            interval_days = 6
        else:
            interval_days = round(interval_days * ease_factor)
        repetitions += 1

    ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ease_factor = max(1.3, ease_factor)
    next_review = date.today() + timedelta(days=interval_days)
    return {
        "ease_factor": round(ease_factor, 3),
        "interval_days": interval_days,
        "repetitions": repetitions,
        "next_review": next_review.isoformat(),
    }


def review_card(card_id: str, quality: int) -> dict:
    """Apply an SM-2 review result to a stored flashcard."""
    sb = _supabase()
    row = sb.table("flashcards").select("*").eq("id", card_id).limit(1).execute().data
    if not row:
        return {"error": "card_not_found"}
    c = row[0]
    update = sm2(c.get("ease_factor", 2.5), c.get("interval_days", 1),
                 c.get("repetitions", 0), quality)
    sb.table("flashcards").update(update).eq("id", card_id).execute()
    return update


def due_cards(student_id: str) -> list[dict]:
    """Cards whose next_review is today or earlier."""
    try:
        res = (
            _supabase()
            .table("flashcards")
            .select("id, question, answer, subject, concept, next_review")
            .eq("student_id", student_id)
            .lte("next_review", date.today().isoformat())
            .order("next_review", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[flashcard_agent] due fetch failed: {e}")
        return []


def flashcard_gen_node(state: CoachingState) -> CoachingState:
    """After a test, generate flashcards for the concepts the student got wrong."""
    try:
        from graph.llm import get_llm
        import json

        result = state.get("evaluation_result") or {}
        wrong_concepts = sorted({
            d["concept"] for d in result.get("details", [])
            if d.get("outcome") == "wrong"
        })
        if not wrong_concepts:
            return {**state}

        subject = state.get("subject")
        llm = get_llm(temperature=0.3)
        raw = llm.invoke(
            "Create one concise flashcard per concept for JEE/NEET revision.\n"
            f"Concepts: {', '.join(wrong_concepts)}\n"
            'Return ONLY a JSON array: [{"concept": "...", "question": "...", "answer": "..."}]'
        ).content
        try:
            cards = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        except Exception:
            cards = []

        sb = _supabase()
        for card in cards:
            sb.table("flashcards").insert({
                "student_id": state["student_id"],
                "question": card.get("question"),
                "answer": card.get("answer"),
                "subject": subject,
                "concept": card.get("concept"),
            }).execute()

        return {**state}

    except Exception as e:
        return {**state, "error": str(e)}
