"""Flashcard Agent — SM-2 spaced repetition.

Generates flashcards for concepts a student got wrong, schedules reviews with the
SM-2 algorithm, and surfaces cards that are due (for the daily reminder job).

Cards are built from the institute's material retrieved from RAG_SERVER for each
wrong concept, and each card stores its `source` ({source, page}). A concept with
nothing retrieved is skipped. If RAG_SERVER isn't configured at all, cards fall
back to the LLM's own knowledge with source null.
"""

from datetime import date, timedelta

from graph.state import CoachingState


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()  # one shared client per process (a new one costs ~1 s)


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
            # "*" so `source` comes back once the Phase 4 migration adds it.
            .select("*")
            .eq("student_id", student_id)
            .lte("next_review", date.today().isoformat())
            .order("next_review", desc=False)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[flashcard_agent] due fetch failed: {e}")
        return []


def due_counts_by_student(page_size: int = 1000) -> dict[str, int]:
    """{student_id: number of cards due today or earlier} for every student, read
    in pages (instead of one due_cards() query per student)."""
    counts: dict[str, int] = {}
    sb, start = _supabase(), 0
    while True:
        rows = (sb.table("flashcards").select("student_id")
                .lte("next_review", date.today().isoformat())
                .order("id").range(start, start + page_size - 1).execute().data or [])
        for r in rows:
            if r.get("student_id"):
                counts[r["student_id"]] = counts.get(r["student_id"], 0) + 1
        if len(rows) < page_size:
            return counts
        start += page_size


def _material_block(material: list[tuple[str, list[dict]]]) -> tuple[str, list[dict]]:
    """Prompt text with chunks numbered across all concepts, plus that flat chunk list."""
    lines, flat = [], []
    for concept, chunks in material:
        lines.append(f"Concept: {concept}")
        for c in chunks:
            flat.append(c)
            where = c["source"] + (f", p. {c['page']}" if c.get("page") else "")
            lines.append(f"[{len(flat)}] ({where})\n{c['text'].strip()[:800]}")
        lines.append("")
    return "\n".join(lines).strip(), flat


def _insert_card(sb, row: dict) -> None:
    try:
        sb.table("flashcards").insert(row).execute()
    except Exception as e:
        # Most likely the Phase 4 migration (flashcards.source) hasn't been run yet.
        print(f"[flashcard_agent] insert failed, retrying without source: {e}")
        sb.table("flashcards").insert({k: v for k, v in row.items() if k != "source"}).execute()


def flashcard_gen_node(state: CoachingState) -> CoachingState:
    """After a test, generate flashcards for the concepts the student got wrong."""
    try:
        from graph.llm import get_llm
        from rag import grounding
        import json

        result = state.get("evaluation_result") or {}
        wrong_concepts = sorted({
            d["concept"] for d in result.get("details", [])
            if d.get("outcome") == "wrong"
        })
        if not wrong_concepts:
            return {**state}

        subject = state.get("subject")
        institute_id = state.get("institute_id") or None
        if grounding.enabled(institute_id):
            found = grounding.retrieve_each(
                [" ".join(filter(None, [c, subject])) for c in wrong_concepts], institute_id, top_k=3)
            material = [(c, chunks) for c, chunks in zip(wrong_concepts, found) if chunks]
            if not material:
                print("[flashcard_agent] nothing retrieved for any wrong concept; no cards")
                return {**state}
            block, flat = _material_block(material)
            prompt = (
                "Create one concise flashcard per concept for JEE/NEET revision, built from the "
                "institute's material below. Rely on it; don't add facts it doesn't support.\n\n"
                f"{block}\n\n"
                'Return ONLY a JSON array: [{"concept": "...", "question": "...", "answer": "...", '
                '"source_ref": n}] where n is the number [n] of the material the card is based on.'
            )
        else:
            # RAG_SERVER not configured: plain LLM cards, no source.
            material, flat = [(c, []) for c in wrong_concepts], []
            prompt = (
                "Create one concise flashcard per concept for JEE/NEET revision.\n"
                f"Concepts: {', '.join(wrong_concepts)}\n"
                'Return ONLY a JSON array: [{"concept": "...", "question": "...", "answer": "..."}]'
            )

        llm = get_llm(temperature=0.3)
        raw = llm.invoke(prompt).content
        try:
            cards = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        except Exception:
            cards = []

        sb = _supabase()
        for card in cards:
            if not isinstance(card, dict) or not card.get("question"):
                continue
            _insert_card(sb, {
                "student_id": state["student_id"],
                "question": card.get("question"),
                "answer": card.get("answer"),
                "subject": subject,
                "concept": card.get("concept"),
                "source": grounding.source_of(flat, card.get("source_ref")),
            })

        return {**state}

    except Exception as e:
        return {**state, "error": str(e)}
