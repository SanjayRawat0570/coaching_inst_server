"""Episodic memory — learning-journey milestones in the episodic_memories table.

Used for personalized motivation during at-risk intervention ("remember when you
finally cracked rotational dynamics?"). Plain Supabase rows, no extra service.
"""

import os
from functools import lru_cache

from supabase import create_client, Client


@lru_cache(maxsize=1)
def _supabase() -> Client:
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def record_milestone(
    student_id: str,
    event_type: str,
    description: str,
    subject: str = None,
    significance: float = 1.0,
) -> bool:
    """Store a single learning milestone.

    event_type examples: 'first_test_passed', 'streak_7', 'weak_concept_mastered',
    'rank_improved', 'comeback_after_gap'.
    """
    try:
        _supabase().table("episodic_memories").insert({
            "student_id": student_id,
            "event_type": event_type,
            "description": description,
            "subject": subject,
            "significance": significance,
        }).execute()
        return True
    except Exception as e:
        print(f"[episodic] record failed: {e}")
        return False


def get_milestones(student_id: str, limit: int = 5) -> list[dict]:
    """Return the most significant recent milestones for a student."""
    try:
        res = (
            _supabase()
            .table("episodic_memories")
            .select("event_type, description, subject, significance, created_at")
            .eq("student_id", student_id)
            .order("significance", desc=True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[episodic] fetch failed: {e}")
        return []


def get_milestones_text(student_id: str, limit: int = 5) -> str:
    """Human-readable milestone summary for prompting (motivation messages)."""
    milestones = get_milestones(student_id, limit=limit)
    if not milestones:
        return ""
    lines = []
    for m in milestones:
        subj = f" ({m['subject']})" if m.get("subject") else ""
        lines.append(f"- {m['description']}{subj}")
    return "\n".join(lines)
