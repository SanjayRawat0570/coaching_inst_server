"""Test Generator — personalized MCQ tests targeting each student's weak concepts.

Pulls the concept-level weakness map, retrieves matching PYQs from Qdrant, and asks
the LLM for a balanced 30/50/20 difficulty set. Designed to sit in a reviewer loop:
review_feedback (if present) is fed back in to improve the next attempt.
"""

import os
import json

from graph.state import CoachingState


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


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


def test_generator_node(state: CoachingState, num_questions: int = 10) -> CoachingState:
    """Generate state['test_questions'] targeting the student's weak concepts."""
    try:
        from graph.llm import get_llm
        from rag.retriever import full_rag_pipeline

        subject = state.get("subject")
        weak = _weak_concepts(state["student_id"], subject)
        concept_names = [w["concept"] for w in weak if w.get("concept")]
        focus = ", ".join(concept_names) if concept_names else (subject or "the syllabus")

        # Retrieve relevant past-year questions / reference material for grounding.
        # RAG is optional context — a retrieval failure must not abort generation
        # (the LLM falls back to its own syllabus knowledge below).
        try:
            pyq_context = "\n\n".join(
                full_rag_pipeline(
                    question=f"Previous year questions on {focus}",
                    subject=subject,
                    institute_id=state.get("institute_id"),
                    student_level=state.get("student_level") or "intermediate",
                )
            )
        except Exception as e:
            print(f"[test_generator] RAG retrieval failed, generating without context: {e}")
            pyq_context = ""

        feedback = state.get("review_feedback") or ""
        retry_note = (
            f"\nThe previous attempt was rejected. Fix this: {feedback}"
            if state.get("iteration_count", 0) > 0 and feedback else ""
        )

        prompt = f"""Create a {num_questions}-question MCQ test for a JEE/NEET student.

Target these weak concepts first: {focus}
Subject: {subject or "mixed"}
Reference material (past-year style questions / notes):
{pyq_context or "(use your own knowledge of the syllabus)"}

Rules:
- Difficulty mix: ~30% easy, ~50% medium, ~20% hard.
- Each question has exactly 4 options and exactly one correct answer.
- Tag each with the specific concept it tests.{retry_note}

Return ONLY a JSON array, no preamble, each element:
{{"question": "...", "options": ["A","B","C","D"], "answer_index": 0,
  "difficulty": "easy|medium|hard", "concept": "...", "marks": 4, "negative": 1}}"""

        llm = get_llm(temperature=0.4)
        raw = llm.invoke(prompt).content
        try:
            start, end = raw.find("["), raw.rfind("]") + 1
            questions = json.loads(raw[start:end])
        except Exception as e:
            print(f"[test_generator] JSON parse failed: {e}")
            questions = []

        return {**state, "test_questions": questions, "subject": subject}

    except Exception as e:
        return {**state, "error": str(e), "test_questions": []}
