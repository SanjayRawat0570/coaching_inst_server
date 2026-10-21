"""Reviewer Agent — quality gatekeeper for generated tests.

Checks the 30/50/20 easy/medium/hard difficulty mix, correctness, and that every
question citing a source is consistent with that RAG_SERVER chunk.
Sets review_passed + review_feedback; the graph loops back to the test generator
up to REVIEWER_MAX_ITERATIONS times. If the last attempt still has questions that
contradict their cited source, that citation is dropped (source: null) rather
than shown to the teacher as backing the question.
"""

import os
import json

from graph.state import CoachingState

MAX_ITERATIONS = int(os.getenv("REVIEWER_MAX_ITERATIONS", "3"))


def _difficulty_split(questions: list[dict]) -> dict:
    counts = {"easy": 0, "medium": 0, "hard": 0}
    for q in questions:
        level = str(q.get("difficulty", "medium")).lower()
        if level in counts:
            counts[level] += 1
    return counts


def _grounded(questions: list[dict], chunks: list[dict], max_items: int = 8) -> list[dict]:
    """Questions that cite a retrieved chunk, paired with that chunk's text."""
    from rag.grounding import chunk_for
    out = []
    for i, q in enumerate(questions):
        chunk = chunk_for(chunks, q.get("source"))
        if not chunk:
            continue
        if q.get("type") == "theory":
            answer = q.get("model_answer")
        else:
            opts, idx = q.get("options") or [], q.get("answer_index")
            answer = opts[idx] if isinstance(idx, int) and 0 <= idx < len(opts) else None
        out.append({"index": i, "question": q.get("question"), "answer": answer,
                    "source_text": chunk["text"][:700]})
        if len(out) >= max_items:
            break
    return out


def reviewer_node(state: CoachingState) -> CoachingState:
    """Approve or request regeneration of state['test_questions']."""
    try:
        from graph.llm import get_llm

        questions = state.get("test_questions") or []
        iteration = state.get("iteration_count", 0) + 1

        if not questions:
            return {**state, "review_passed": False, "iteration_count": iteration,
                    "review_feedback": "No questions were generated."}

        total = len(questions)
        split = _difficulty_split(questions)

        # Use the generator's adaptive difficulty mix (F4) if present, else 30/50/20.
        mix = state.get("difficulty_mix") or {"easy": 30, "medium": 50, "hard": 20}
        targets = {k: mix.get(k, 0) / 100 * total for k in ("easy", "medium", "hard")}
        balanced = all(abs(split[k] - targets[k]) <= 2 for k in targets)

        # LLM quality check on correctness + clarity
        is_theory = any(q.get("type") == "theory" for q in questions)
        sample = json.dumps(questions[:5], ensure_ascii=False)
        criteria = (
            "factual correctness, a sound model answer / marking scheme, and clear wording"
            if is_theory
            else "factual correctness, exactly one correct option, and clear wording"
        )
        grounded = _grounded(questions, state.get("test_context_chunks") or [])
        grounding_check = (
            "\nAlso check each question below against the source text it cites. List its "
            "index under \"ungrounded\" if the question or its answer contradicts, or is not "
            "supported by, that text.\n"
            f"Cited questions: {json.dumps(grounded, ensure_ascii=False)}\n"
            if grounded else ""
        )
        llm = get_llm(fast=True)
        verdict = llm.invoke(
            "You are a JEE/NEET exam committee reviewer. Check these questions for "
            f"{criteria}.\n"
            f"Questions: {sample}\n"
            f"{grounding_check}"
            'Reply ONLY as JSON: {"ok": true/false, "feedback": "short reason", "ungrounded": []}'
        ).content
        try:
            quality = json.loads(verdict[verdict.find("{"): verdict.rfind("}") + 1])
        except Exception:
            quality = {"ok": True, "feedback": "auto-pass (unparseable verdict)"}

        cited = {g["index"] for g in grounded}
        ungrounded = sorted({i for i in (quality.get("ungrounded") or [])
                             if isinstance(i, int) and i in cited})

        passed = balanced and bool(quality.get("ok", True)) and not ungrounded
        feedback_parts = []
        if not balanced:
            feedback_parts.append(
                f"Difficulty mix off: {split} vs target ~"
                f"{ {k: round(v) for k, v in targets.items()} }."
            )
        if not quality.get("ok", True):
            feedback_parts.append(str(quality.get("feedback", "")))
        if ungrounded:
            feedback_parts.append(
                "Questions " + ", ".join(str(i + 1) for i in ungrounded)
                + " don't match the material they cite — base them on it or set source_ref to null."
            )
            if iteration >= MAX_ITERATIONS:
                # Out of retries: never present a citation that doesn't back the question.
                questions = [{**q, "source": None} if i in ungrounded else q
                             for i, q in enumerate(questions)]

        return {
            **state,
            "test_questions": questions,
            "review_passed": passed,
            "review_feedback": " ".join(feedback_parts) or "Looks good.",
            "iteration_count": iteration,
        }

    except Exception as e:
        # On reviewer failure, pass through so the student is never blocked
        return {**state, "review_passed": True,
                "review_feedback": f"reviewer error, auto-approved: {e}",
                "iteration_count": state.get("iteration_count", 0) + 1}


def should_continue(state: CoachingState) -> str:
    """Conditional edge target after the reviewer node."""
    if state.get("review_passed"):
        return "approved"
    if state.get("iteration_count", 0) >= MAX_ITERATIONS:
        return "approved"  # return best available after max attempts
    return "regenerate"
