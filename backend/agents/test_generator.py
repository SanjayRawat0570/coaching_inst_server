"""Test Generator — personalized MCQ tests targeting each student's weak concepts.

Pulls the concept-level weakness map, retrieves the institute's matching material
and PYQs from RAG_SERVER (one query per weak concept), and asks the LLM for a
balanced difficulty set based on that material. Each question carries a `source`
({source, page}, or null when it isn't based on retrieved material). Designed to
sit in a reviewer loop: review_feedback (if present) is fed back in to improve
the next attempt, and the retrieved chunks are kept in state for the reviewer.
"""

import json

from graph.state import CoachingState


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()  # one shared client per process (a new one costs ~1 s)


def _weak_concepts(student_id: str, subject: str = None, limit: int = 6) -> list[dict]:
    """Lowest-scoring concepts for this student (most in need of practice)."""
    try:
        q = (
            _supabase()
            .table("weakness_map")
            .select("subject, chapter, concept, score, attempts")
            .eq("student_id", student_id)
            .order("score", desc=False)
        )
        if subject:
            q = q.eq("subject", subject)
        res = q.limit(limit).execute()
        return res.data or []
    except Exception as e:
        print(f"[test_generator] weakness fetch failed: {e}")
        return []


# F4: adaptive difficulty. A 1–5 level derived from the student's last test, mapped
# to an easy/medium/hard mix the LLM is asked to follow.
_LEVEL_MIX = {
    1: (60, 35, 5),    # struggling → mostly easy
    2: (45, 45, 10),
    3: (30, 50, 20),   # balanced (default / no history)
    4: (15, 50, 35),
    5: (5, 45, 50),    # strong → mostly hard
}
_LEVEL_NAME = {1: "very easy", 2: "easy", 3: "balanced", 4: "hard", 5: "very hard"}


def _last_score_percent(student_id: str) -> float | None:
    """Most recent evaluated test's percentage for this student (None if none)."""
    try:
        rows = (_supabase().table("tests").select("score, total_marks, status")
                .eq("student_id", student_id).eq("status", "evaluated")
                .order("created_at", desc=True).limit(1).execute().data) or []
        if rows and rows[0].get("total_marks"):
            return max(0.0, rows[0]["score"] / rows[0]["total_marks"] * 100)
    except Exception as e:
        print(f"[test_generator] last score lookup failed: {e}")
    return None


def _difficulty_level(percent: float | None) -> int:
    """Map last score % → difficulty level 1–5 for the NEXT test."""
    if percent is None:
        return 3
    if percent < 30:
        return 1
    if percent < 50:
        return 2
    if percent < 70:
        return 3
    if percent < 85:
        return 4
    return 5


def test_generator_node(state: CoachingState, num_questions: int = 10) -> CoachingState:
    """Generate state['test_questions'] targeting the student's weak concepts."""
    try:
        from graph.llm import get_llm
        from rag import grounding
        from rag.rag_server_client import format_context

        subject = state.get("subject")
        weak = _weak_concepts(state["student_id"], subject)
        concept_names = [w["concept"] for w in weak if w.get("concept")]
        focus = ", ".join(concept_names) if concept_names else (subject or "the syllabus")

        # Institute material / PYQs from RAG_SERVER, one query per weak concept.
        # Retrieved once and reused across reviewer retries. Optional context: on
        # failure or no hits the LLM uses its own syllabus knowledge (source: null).
        chunks = state.get("test_context_chunks")
        if chunks is None:
            queries = [" ".join(filter(None, [w["concept"], w.get("subject") or subject,
                                              "previous year question"]))
                       for w in weak if w.get("concept")]
            if not queries:
                queries = [f"{subject or 'JEE NEET'} previous year questions"]
            try:
                chunks = grounding.retrieve(queries, state.get("institute_id"), top_k=3)
            except Exception as e:
                print(f"[test_generator] retrieval failed, generating without context: {e}")
                chunks = []
        pyq_context = format_context(chunks)

        feedback = state.get("review_feedback") or ""
        retry_note = (
            f"\nThe previous attempt was rejected. Fix this: {feedback}"
            if state.get("iteration_count", 0) > 0 and feedback else ""
        )

        question_type = "theory" if state.get("question_type") == "theory" else "mcq"

        # F4: pick difficulty from the student's last score (stable across the
        # reviewer loop — computed once, then carried in state).
        level = state.get("difficulty_level")
        if not level:
            level = _difficulty_level(_last_score_percent(state["student_id"]))
        easy, med, hard = _LEVEL_MIX.get(level, _LEVEL_MIX[3])

        if pyq_context:
            material = f"""Reference material from the institute's notes and PYQs (numbered):
{pyq_context}

- Base the questions on this material and its PYQs, keeping the JEE/NEET exam pattern.
- Set "source_ref" to the number [n] of the material a question is based on, or null
  if it isn't based on any of it. Never cite material that doesn't support the question."""
        else:
            material = """Reference material: (none available — use your own knowledge of the syllabus)
- Set "source_ref" to null for every question."""

        common = f"""Target these weak concepts first: {focus}
Subject: {subject or "mixed"}
{material}

Rules:
- Overall difficulty: {_LEVEL_NAME[level]} (level {level}/5).
- Difficulty mix: ~{easy}% easy, ~{med}% medium, ~{hard}% hard.
- Tag each with the specific concept it tests.{retry_note}"""

        if question_type == "theory":
            prompt = f"""Create a {num_questions}-question THEORETICAL (subjective, written-answer) test for a JEE/NEET student.

{common}
- These are NOT multiple choice. Each question expects a written explanation/derivation.
- Provide a concise model answer / marking scheme for each so it can be graded later.

Return ONLY a JSON array, no preamble, each element:
{{"question": "...", "model_answer": "concise expected answer / key points",
  "difficulty": "easy|medium|hard", "concept": "...", "marks": 5, "type": "theory",
  "source_ref": 1}}"""
        else:
            prompt = f"""Create a {num_questions}-question MCQ test for a JEE/NEET student.

{common}
- Each question has exactly 4 options and exactly one correct answer.

Return ONLY a JSON array, no preamble, each element:
{{"question": "...", "options": ["A","B","C","D"], "answer_index": 0,
  "difficulty": "easy|medium|hard", "concept": "...", "marks": 4, "negative": 1, "type": "mcq",
  "source_ref": 1}}"""

        llm = get_llm(temperature=0.4)
        raw = llm.invoke(prompt).content
        try:
            start, end = raw.find("["), raw.rfind("]") + 1
            questions = json.loads(raw[start:end])
        except Exception as e:
            print(f"[test_generator] JSON parse failed: {e}")
            questions = []

        # Every question carries its type (even if the LLM omitted it) and a
        # source: the retrieved chunk it cites as {source, page}, else null.
        questions = [q for q in questions if isinstance(q, dict)]
        for q in questions:
            q.setdefault("type", question_type)
            q["source"] = grounding.source_of(chunks, q.pop("source_ref", None))

        return {**state, "test_questions": questions, "subject": subject,
                "question_type": question_type, "difficulty_level": level,
                "difficulty_mix": {"easy": easy, "medium": med, "hard": hard},
                "test_context_chunks": chunks}

    except Exception as e:
        return {**state, "error": str(e), "test_questions": []}
