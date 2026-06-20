"""Answer Evaluator — grades MCQ answers and handwritten answer photos.

For MCQs: deterministic scoring with negative marking.
For handwritten subjective answers: Gemini Vision reads the photo and grades step by
step against a model answer.
"""

import os
import json

from graph.state import CoachingState


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _num(value, default: float) -> float:
    """Coerce a marks value to a number, falling back to a default (e.g. when a
    teacher left the field blank, sending "")."""
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_theory(q: dict) -> bool:
    """A question is theoretical if tagged so, or it has a model answer and no options."""
    if q.get("type") == "theory":
        return True
    return "options" not in q and "model_answer" in q


# F17: a written answer this close to the model answer is likely copied verbatim.
SIMILARITY_FLAG_THRESHOLD = 0.95


def _answer_similarity(student_answer: str, model_answer: str):
    """F17: cosine similarity between the student's and the model answer (0–1)."""
    student_answer = (student_answer or "").strip()
    model_answer = (model_answer or "").strip()
    if not student_answer or not model_answer:
        return None
    try:
        import math
        from rag.embedder import embed
        a, b = embed(student_answer), embed(model_answer)
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return round(dot / (na * nb), 4) if na and nb else None
    except Exception as e:
        print(f"[answer_evaluator] similarity check failed: {e}")
        return None


def grade_text_answer(question: str, model_answer: str, student_answer: str,
                      max_marks: float = 5) -> dict:
    """LLM-grade a written answer against the model answer. Returns marks + feedback."""
    student_answer = (student_answer or "").strip()
    if not student_answer:
        return {"marks_awarded": 0, "max_marks": max_marks, "feedback": "No answer given."}
    try:
        from graph.llm import get_llm
        llm = get_llm(temperature=0)
        raw = llm.invoke(
            "You are grading a JEE/NEET written (subjective) answer. Award partial marks "
            "for correct steps and reasoning; be fair but rigorous.\n"
            f"Question: {question}\n"
            f"Model answer / marking scheme: {model_answer or '(use standard JEE/NEET scheme)'}\n"
            f"Maximum marks: {max_marks}\n"
            f"Student's answer: {student_answer}\n"
            'Return ONLY JSON: {"marks_awarded": number, "feedback": "one-line feedback"}'
        ).content
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        awarded = float(data.get("marks_awarded", 0))
        awarded = max(0.0, min(awarded, float(max_marks)))  # clamp to [0, max]
        sim = _answer_similarity(student_answer, model_answer)
        return {"marks_awarded": round(awarded, 2), "max_marks": max_marks,
                "feedback": str(data.get("feedback", "")),
                "similarity": sim,
                "flagged": bool(sim is not None and sim > SIMILARITY_FLAG_THRESHOLD)}
    except Exception as e:
        print(f"[answer_evaluator] text grading failed: {e}")
        return {"marks_awarded": 0, "max_marks": max_marks,
                "feedback": "Could not grade this answer automatically.",
                "similarity": None, "flagged": False}


def score_test(questions: list[dict], answers: list) -> dict:
    """Score a test that may contain MCQ and/or theoretical questions.

    For MCQ, answers[i] is the chosen option index (or None). For theory, answers[i]
    is the student's written text. Theory answers are graded by the LLM.
    """
    score = 0.0
    total = 0
    per_concept = {}
    details = []
    for i, q in enumerate(questions):
        concept = q.get("concept", "unknown")
        per_concept.setdefault(concept, {"correct": 0, "total": 0})
        per_concept[concept]["total"] += 1
        given = answers[i] if i < len(answers) else None

        if _is_theory(q):
            marks = _num(q.get("marks"), 5)
            total += marks
            graded = grade_text_answer(q.get("question", ""), q.get("model_answer", ""),
                                       given if isinstance(given, str) else "", marks)
            awarded = graded["marks_awarded"]
            score += awarded
            # Count as "correct" for the concept if at least half marks were earned.
            if marks and awarded >= marks / 2:
                per_concept[concept]["correct"] += 1
            outcome = "skipped" if not (isinstance(given, str) and given.strip()) else "graded"
            details.append({"index": i, "concept": concept, "outcome": outcome,
                            "marks_awarded": awarded, "feedback": graded.get("feedback", ""),
                            "similarity": graded.get("similarity"),
                            "flagged": graded.get("flagged", False)})  # F17
        else:
            marks = _num(q.get("marks"), 4)
            negative = _num(q.get("negative"), 1)
            total += marks
            correct_idx = q.get("answer_index")
            if given is None:
                outcome = "skipped"
            elif given == correct_idx:
                score += marks
                per_concept[concept]["correct"] += 1
                outcome = "correct"
            else:
                score -= negative
                outcome = "wrong"
            details.append({"index": i, "concept": concept, "outcome": outcome})

    # F17: surface any answers that are suspiciously close to the model answer.
    integrity_flags = [{"index": d["index"], "concept": d["concept"],
                        "similarity": d.get("similarity")}
                       for d in details if d.get("flagged")]

    return {
        "score": round(score, 2),            # FLOAT column — fractions allowed (theory partials)
        "total_marks": int(round(total)),    # INTEGER column — must be a whole number
        "per_concept": per_concept,
        "details": details,
        "integrity_flags": integrity_flags,
    }


def score_mcq(questions: list[dict], answers: list) -> dict:
    """Backward-compatible alias — delegates to the mixed scorer."""
    return score_test(questions, answers)


def evaluate_handwritten(image_b64: str, question: str, model_answer: str = "") -> dict:
    """Gemini Vision: read a handwritten answer photo and grade it step by step."""
    try:
        from graph.llm import get_vision_llm
        from rag.image_utils import preprocess_b64
        from langchain_core.messages import HumanMessage

        image_b64 = preprocess_b64(image_b64)
        vision = get_vision_llm()
        instruction = (
            "You are grading a handwritten exam answer. Read the handwriting in the "
            "image, then grade it step by step.\n"
            f"Question: {question}\n"
            f"Model answer / marking scheme: {model_answer or '(use standard JEE/NEET scheme)'}\n"
            'Return ONLY JSON: {"marks_awarded": number, "max_marks": number, '
            '"steps": [{"step": "...", "correct": true/false, "comment": "..."}], '
            '"feedback": "overall feedback"}'
        )
        message = HumanMessage(content=[
            {"type": "text", "text": instruction},
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ])
        raw = vision.invoke([message]).content
        return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception as e:
        print(f"[answer_evaluator] vision grading failed: {e}")
        return {"marks_awarded": 0, "max_marks": 0, "steps": [],
                "feedback": "Could not read the answer image. Please retake the photo."}


def evaluator_node(state: CoachingState) -> CoachingState:
    """Evaluate a submitted test. Reads questions/answers from the tests row."""
    try:
        test_id = state.get("test_id")
        sb = _supabase()
        row = sb.table("tests").select("*").eq("id", test_id).limit(1).execute().data
        if not row:
            return {**state, "error": "test_not_found",
                    "agent_output": "Test not found."}
        test = row[0]
        questions = test.get("questions") or []
        answers = test.get("answers") or []

        result = score_test(questions, answers)

        sb.table("tests").update({
            "score": result["score"],
            "total_marks": result["total_marks"],
            "status": "evaluated",
        }).eq("id", test_id).execute()

        return {
            **state,
            "evaluation_result": result,
            "score": result["score"],
            "subject": test.get("subject"),
        }

    except Exception as e:
        return {**state, "error": str(e),
                "agent_output": "Evaluation failed. Please try again."}
