"""Progress Tracker — updates the concept-level weakness map after every test.

Runs in parallel with rank/flashcard/parent agents after evaluation. Uses an
exponential moving average per concept so recent performance counts more, and
records episodic milestones when a weak concept crosses into mastery.
"""


from graph.state import CoachingState

EMA_ALPHA = 0.4  # weight of the newest result
MASTERY_THRESHOLD = 0.8


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()  # one shared client per process (a new one costs ~1 s)


def _update_concepts(sb, student_id, subject, new_scores: dict[str, float]) -> dict[str, dict]:
    """Upsert the EMA score of several concepts in weakness_map with one read and
    one write (it used to be a read + a write per concept). Returns per concept
    the new row state."""
    concepts = list(new_scores)
    if not concepts:
        return {}
    existing = {}
    for row in (sb.table("weakness_map").select("concept, score, attempts")
                .eq("student_id", student_id).eq("subject", subject)
                .in_("concept", concepts).execute().data or []):
        existing.setdefault(row["concept"], row)  # first match, as limit(1) did

    rows, out = [], {}
    for concept, new_score in new_scores.items():
        if concept in existing:
            prev = existing[concept]["score"] or 0.0
            attempts = (existing[concept]["attempts"] or 0) + 1
            score = round((1 - EMA_ALPHA) * prev + EMA_ALPHA * new_score, 3)
        else:
            prev = 0.0
            attempts = 1
            score = round(new_score, 3)
        rows.append({"student_id": student_id, "subject": subject, "concept": concept,
                     "score": score, "attempts": attempts})
        out[concept] = {"concept": concept, "previous": prev, "score": score,
                        "crossed_mastery": prev < MASTERY_THRESHOLD <= score}

    sb.table("weakness_map").upsert(rows, on_conflict="student_id,subject,concept").execute()
    return out


def progress_tracker_node(state: CoachingState) -> CoachingState:
    """Translate per-concept correctness from evaluation into weakness_map updates."""
    try:
        from memory.episodic import record_milestone
        from graph.knowledge_graph import ensure_concept, link_prerequisites

        result = state.get("evaluation_result") or {}
        per_concept = result.get("per_concept") or {}
        subject = state.get("subject")
        student_id = state["student_id"]
        sb = _supabase()

        ratios = {}
        for concept, stats in per_concept.items():
            total = stats.get("total", 0) or 1
            ratios[concept] = stats.get("correct", 0) / total  # 0..1 mastery signal
        new_state = _update_concepts(sb, student_id, subject, ratios)

        updates = []
        for concept, ratio in ratios.items():
            update = new_state[concept]

            # Knowledge graph: register the concept node; for weak concepts also
            # infer + wire prerequisite edges (recommend what to fix first).
            ensure_concept(concept, subject=subject)
            if ratio < 0.5:
                update["prerequisites"] = link_prerequisites(concept, subject=subject)

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
