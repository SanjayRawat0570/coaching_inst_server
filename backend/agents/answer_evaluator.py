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


def score_mcq(questions: list[dict], answers: list) -> dict:
    """Deterministic MCQ scoring with negative marking.

    answers[i] is the option index the student chose, or None if skipped.
    """
    score = 0.0
    total = 0
    per_concept = {}
    details = []
    for i, q in enumerate(questions):
        marks = q.get("marks", 4)
        negative = q.get("negative", 1)
        total += marks
        chosen = answers[i] if i < len(answers) else None
        correct_idx = q.get("answer_index")
        concept = q.get("concept", "unknown")
        per_concept.setdefault(concept, {"correct": 0, "total": 0})
        per_concept[concept]["total"] += 1

        if chosen is None:
            outcome = "skipped"
        elif chosen == correct_idx:
            score += marks
            per_concept[concept]["correct"] += 1
            outcome = "correct"
        else:
            score -= negative
            outcome = "wrong"
        details.append({"index": i, "concept": concept, "outcome": outcome})

    return {
        "score": round(score, 2),
        "total_marks": total,
        "per_concept": per_concept,
        "details": details,
    }


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

        result = score_mcq(questions, answers)

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
