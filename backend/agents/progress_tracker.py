"""Progress Tracker — updates the concept-level weakness map after every test.

Runs in parallel with rank/flashcard/parent agents after evaluation. Uses an
exponential moving average per concept so recent performance counts more, and
records episodic milestones when a weak concept crosses into mastery.
"""

import os

from graph.state import CoachingState

EMA_ALPHA = 0.4  # weight of the newest result
MASTERY_THRESHOLD = 0.8


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _update_concept(sb, student_id, subject, concept, new_score) -> dict:
    """Upsert one concept's EMA score in weakness_map. Returns the new row state."""
    existing = (
        sb.table("weakness_map")
        .select("score, attempts")
        .eq("student_id", student_id)
        .eq("subject", subject)
        .eq("concept", concept)
        .limit(1)
        .execute()
        .data
    )
    if existing:
        prev = existing[0]["score"] or 0.0
        attempts = (existing[0]["attempts"] or 0) + 1
        score = round((1 - EMA_ALPHA) * prev + EMA_ALPHA * new_score, 3)
    else:
        prev = 0.0
        attempts = 1
        score = round(new_score, 3)

    sb.table("weakness_map").upsert({
        "student_id": student_id,
        "subject": subject,
        "concept": concept,
        "score": score,
        "attempts": attempts,
    }, on_conflict="student_id,subject,concept").execute()

    return {"concept": concept, "previous": prev, "score": score,
            "crossed_mastery": prev < MASTERY_THRESHOLD <= score}


def progress_tracker_node(state: CoachingState) -> CoachingState:
    """Translate per-concept correctness from evaluation into weakness_map updates."""
    try:
        from memory.episodic import record_milestone

        result = state.get("evaluation_result") or {}
        per_concept = result.get("per_concept") or {}
        subject = state.get("subject")
        student_id = state["student_id"]
        sb = _supabase()

        updates = []
        for concept, stats in per_concept.items():
            total = stats.get("total", 0) or 1
            ratio = stats.get("correct", 0) / total  # 0..1 mastery signal
            update = _update_concept(sb, student_id, subject, concept, ratio)
            updates.append(update)
            if update["crossed_mastery"]:
                record_milestone(
                    student_id,
                    event_type="weak_concept_mastered",
                    description=f"Mastered '{concept}'",
                    subject=subject,
                    significance=2.0,
                )

        return {**state, "weakness_update": {"concepts": updates}}

    except Exception as e:
        return {**state, "error": str(e)}
