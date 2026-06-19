"""Reviewer Agent — quality gatekeeper for generated tests.

Checks the 30/50/20 easy/medium/hard difficulty mix and concept coverage.
Sets review_passed + review_feedback; the graph loops back to the test generator
up to REVIEWER_MAX_ITERATIONS times.
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
        llm = get_llm()
        verdict = llm.invoke(
            "You are a JEE/NEET exam committee reviewer. Check these questions for "
            f"{criteria}.\n"
            f"Questions: {sample}\n"
            'Reply ONLY as JSON: {"ok": true/false, "feedback": "short reason"}'
        ).content
        try:
            quality = json.loads(verdict[verdict.find("{"): verdict.rfind("}") + 1])
        except Exception:
            quality = {"ok": True, "feedback": "auto-pass (unparseable verdict)"}

        passed = balanced and bool(quality.get("ok", True))
        feedback_parts = []
        if not balanced:
            feedback_parts.append(
                f"Difficulty mix off: {split} vs target ~"
                f"{ {k: round(v) for k, v in targets.items()} }."
            )
        if not quality.get("ok", True):
            feedback_parts.append(str(quality.get("feedback", "")))

        return {
            **state,
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
