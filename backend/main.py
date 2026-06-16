"""Smart Coaching Platform — FastAPI entry point.

Runs all endpoints + Supabase Auth + SSE streaming + APScheduler jobs.
Local: uvicorn main:app --reload --port 8000   |   HF Spaces: port 7860 (Dockerfile)
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from auth.supabase_auth import get_current_user, require_role, get_supabase  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduled jobs on boot
    try:
        from scheduler.jobs import start_scheduler, shutdown_scheduler
        start_scheduler()
    except Exception as e:
        print(f"[main] scheduler not started: {e}")
        shutdown_scheduler = lambda: None  # noqa: E731
    yield
    try:
        shutdown_scheduler()
    except Exception:
        pass


app = FastAPI(title="Smart Coaching Platform", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request models ────────────────────────────────────────────────────────────
class DoubtRequest(BaseModel):
    institute_id: str
    question: str
    subject: str | None = None
    student_level: str = "intermediate"
    image_b64: str | None = None
    socratic: bool = False
    conversation_history: list[dict] = []


class GenerateTestRequest(BaseModel):
    student_id: str
    institute_id: str
    subject: str | None = None
    num_questions: int = 10


class ApproveTestRequest(BaseModel):
    test_id: str
    approved: bool = True
    edited_questions: list[dict] | None = None


class SubmitTestRequest(BaseModel):
    test_id: str
    answers: list


class EvaluateHandwrittenRequest(BaseModel):
    model_config = {"protected_namespaces": ()}
    image_b64: str
    question: str
    model_answer: str = ""


class ReviewCardRequest(BaseModel):
    card_id: str
    quality: int  # 0-5


class MarkAlertRequest(BaseModel):
    alert_id: str


class SignupRequest(BaseModel):
    email: str
    password: str
    role: str = "student"
    name: str = ""
    institute_id: str | None = None


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.post("/auth/signup")
def signup(req: SignupRequest):
    """Pre-confirmed signup via the admin API — no confirmation email, no rate limit.

    Creates the auth user with email already confirmed, and (for students) provisions
    their students profile row so the app works on first login. The frontend then signs
    in with the same password to get a session.
    """
    sb = get_supabase()
    role = req.role if req.role in ("student", "teacher", "parent", "admin") else "student"
    institute_id = req.institute_id or None
    try:
        res = sb.auth.admin.create_user({
            "email": req.email,
            "password": req.password,
            "email_confirm": True,
            "user_metadata": {"role": role, "name": req.name, "institute_id": institute_id},
        })
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower() or "registered" in msg.lower() or "exists" in msg.lower():
            raise HTTPException(status_code=400, detail="Email already registered — please log in.")
        raise HTTPException(status_code=400, detail=f"Signup failed: {msg}")

    uid = res.user.id
    if role == "student":
        try:
            sb.table("students").upsert({
                "auth_id": uid,
                "name": req.name or req.email,
                "email": req.email,
                "institute_id": institute_id,
            }, on_conflict="auth_id").execute()
        except Exception as e:
            print(f"[signup] student profile creation failed: {e}")

    return {"ok": True, "user_id": uid, "role": role}


# ── Doubt ─────────────────────────────────────────────────────────────────────
@app.post("/doubt")
def doubt(req: DoubtRequest, background: BackgroundTasks, user=Depends(get_current_user)):
    from agents.doubt_agent import answer_doubt, persist_doubt
    student_id = _resolve_student_id(user)
    # Answer now; defer the doubt_logs + long-term memory writes to a background task
    result = answer_doubt(
        student_id=student_id,
        institute_id=req.institute_id,
        question=req.question,
        subject=req.subject,
        student_level=req.student_level,
        image_b64=req.image_b64,
        socratic=req.socratic,
        conversation_history=req.conversation_history,
        persist=False,
    )
    if not result.get("error"):
        background.add_task(
            persist_doubt, student_id, result["question"], result["answer"],
            req.subject, result["sources"], result["confidence"], result["input_type"],
        )
    return result


@app.post("/doubt/stream")
async def doubt_stream(req: DoubtRequest, user=Depends(get_current_user)):
    from graph.doubt_subgraph import get_doubt_graph
    student_id = _resolve_student_id(user)
    graph = get_doubt_graph()

    initial = {
        "student_id": student_id,
        "institute_id": req.institute_id,
        "action_type": "doubt",
        "input_text": req.question,
        "input_image": req.image_b64,
        "subject": req.subject,
        "student_level": req.student_level,
        "conversation_history": req.conversation_history or [],
        "current_topic": "socratic" if req.socratic else None,
        "iteration_count": 0,
    }

    async def generate():
        try:
            async for event in graph.astream_events(initial, version="v2"):
                kind = event["event"]
                # Only stream the FINAL answer — the doubt node tags it "final_answer".
                # Without this filter the RAG pipeline's internal LLM calls (query
                # planning, HyDE, CRAG scoring) leak their tokens into the answer.
                if kind == "on_chat_model_stream" and "final_answer" in event.get("tags", []):
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        yield f"data: {chunk}\n\n"
                elif kind == "on_chain_start" and event.get("name") == "doubt":
                    yield "data: [STATUS]Searching notes and thinking…\n\n"
        except Exception as e:
            yield f"data: [ERROR]{e}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Tests ─────────────────────────────────────────────────────────────────────
@app.post("/test/generate")
def generate_test(req: GenerateTestRequest, user=Depends(require_role("teacher", "admin"))):
    """Generate a personalized test (status 'pending' awaiting teacher approval)."""
    from agents.test_generator import test_generator_node
    from agents.reviewer_agent import reviewer_node, should_continue, MAX_ITERATIONS

    state = {
        "student_id": req.student_id,
        "institute_id": req.institute_id,
        "action_type": "test",
        "subject": req.subject,
        "iteration_count": 0,
        "conversation_history": [],
    }
    # Generate -> review -> regenerate loop (bounded)
    while True:
        state = test_generator_node(state, num_questions=req.num_questions)
        state = reviewer_node(state)
        if should_continue(state) == "approved" or state["iteration_count"] >= MAX_ITERATIONS:
            break

    sb = get_supabase()
    row = sb.table("tests").insert({
        "student_id": req.student_id,
        "institute_id": req.institute_id,
        "subject": req.subject,
        "questions": state.get("test_questions") or [],
        "status": "pending",
        "teacher_approved": False,
    }).execute().data
    test_id = row[0]["id"] if row else None
    return {"test_id": test_id, "questions": state.get("test_questions"),
            "review_feedback": state.get("review_feedback")}


@app.post("/test/approve")
def approve_test(req: ApproveTestRequest, user=Depends(require_role("teacher", "admin"))):
    """HITL: teacher approves or edits a pending test before it reaches the student."""
    sb = get_supabase()
    update = {"teacher_approved": bool(req.approved),
              "status": "ready" if req.approved else "rejected"}
    if req.edited_questions is not None:
        update["questions"] = req.edited_questions
    sb.table("tests").update(update).eq("id", req.test_id).execute()
    return {"test_id": req.test_id, **update}


@app.post("/test/submit")
def submit_test(req: SubmitTestRequest, background: BackgroundTasks,
                user=Depends(get_current_user)):
    """Student submits answers -> evaluate -> progress/rank/flashcards (post-test flow)."""
    student_id = _resolve_student_id(user)
    sb = get_supabase()
    sb.table("tests").update({"answers": req.answers}).eq("id", req.test_id).execute()

    from graph.coaching_graph import get_graph
    from graph.checkpointer import get_checkpointer
    # Checkpointer records every step under thread_id=test_id (time-travel via /debug)
    graph = get_graph(checkpointer=get_checkpointer())
    config = {"configurable": {"thread_id": req.test_id}}
    result = graph.invoke({
        "student_id": student_id,
        "institute_id": "",
        "action_type": "evaluate",
        "test_id": req.test_id,
        "iteration_count": 0,
        "conversation_history": [],
    }, config)
    return {
        "score": result.get("score"),
        "evaluation": result.get("evaluation_result"),
        "air_rank": result.get("air_rank"),
        "weakness_update": result.get("weakness_update"),
    }


@app.post("/answer/evaluate")
def evaluate_handwritten(req: EvaluateHandwrittenRequest, user=Depends(get_current_user)):
    from agents.answer_evaluator import evaluate_handwritten as grade
    return grade(req.image_b64, req.question, req.model_answer)


# ── Progress / flashcards ─────────────────────────────────────────────────────
@app.get("/progress")
def progress(user=Depends(get_current_user)):
    student_id = _resolve_student_id(user)
    sb = get_supabase()
    weakness = (sb.table("weakness_map").select("subject, concept, score, attempts")
                .eq("student_id", student_id).order("score", desc=False).execute()).data
    student = (sb.table("students").select("xp_points, streak_days, target_exam")
               .eq("id", student_id).limit(1).execute()).data
    return {"weakness_map": weakness, "profile": student[0] if student else {}}


@app.get("/flashcards/due")
def flashcards_due(user=Depends(get_current_user)):
    from agents.flashcard_agent import due_cards
    return {"cards": due_cards(_resolve_student_id(user))}


@app.post("/flashcards/review")
def review_flashcard(req: ReviewCardRequest, user=Depends(get_current_user)):
    from agents.flashcard_agent import review_card
    return review_card(req.card_id, req.quality)


# ── Teacher / admin ───────────────────────────────────────────────────────────
@app.get("/teacher/alerts")
def teacher_alerts(institute_id: str, user=Depends(require_role("teacher", "admin"))):
    sb = get_supabase()
    alerts = (sb.table("alerts").select("*")
              .eq("institute_id", institute_id).eq("is_read", False)
              .order("risk_score", desc=True).execute()).data
    return {"alerts": alerts}


@app.get("/teacher/overview")
def teacher_overview(institute_id: str, user=Depends(require_role("teacher", "admin"))):
    """Class heatmap (avg concept mastery) + at-risk alerts + most-asked doubts."""
    from datetime import datetime, timedelta, timezone
    sb = get_supabase()

    student_ids = [s["id"] for s in (
        sb.table("students").select("id").eq("institute_id", institute_id).execute().data or []
    )]

    # Heatmap: average mastery per concept across the class
    heatmap = []
    if student_ids:
        rows = (sb.table("weakness_map").select("concept, score")
                .in_("student_id", student_ids).execute().data or [])
        agg = {}
        for r in rows:
            agg.setdefault(r["concept"], []).append(r.get("score") or 0)
        heatmap = sorted(
            ({"concept": c, "avg_score": round(sum(v) / len(v), 3)} for c, v in agg.items()),
            key=lambda x: x["avg_score"],
        )

    alerts = (sb.table("alerts").select("*")
              .eq("institute_id", institute_id).eq("is_read", False)
              .order("risk_score", desc=True).execute().data or [])

    # Top doubts this week (simple frequency over recent questions)
    top_doubts = []
    if student_ids:
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        doubts = (sb.table("doubt_logs").select("question")
                  .in_("student_id", student_ids).gte("created_at", week_ago)
                  .limit(500).execute().data or [])
        freq = {}
        for d in doubts:
            key = (d.get("question") or "").strip()[:120]
            if key:
                freq[key] = freq.get(key, 0) + 1
        top_doubts = [{"question": q, "count": n}
                      for q, n in sorted(freq.items(), key=lambda x: -x[1])[:10]]

    return {"heatmap": heatmap, "alerts": alerts, "top_doubts": top_doubts}


@app.get("/teacher/tests/pending")
def teacher_pending_tests(institute_id: str, user=Depends(require_role("teacher", "admin"))):
    sb = get_supabase()
    tests = (sb.table("tests").select("id, student_id, subject, questions, status, created_at")
             .eq("institute_id", institute_id).eq("status", "pending")
             .order("created_at", desc=True).execute().data or [])
    return {"tests": tests}


@app.post("/teacher/alerts/read")
def mark_alert_read(req: MarkAlertRequest, user=Depends(require_role("teacher", "admin"))):
    sb = get_supabase()
    sb.table("alerts").update({"is_read": True}).eq("id", req.alert_id).execute()
    return {"alert_id": req.alert_id, "is_read": True}


# ── Parent ────────────────────────────────────────────────────────────────────
@app.get("/parent/report")
def parent_report(user=Depends(require_role("parent"))):
    """Latest weekly report + this week's summary for the parent's child.

    A parent is linked to a student by sharing parent's email == students.email,
    or by parent_phone. Adjust the linkage to your enrollment model as needed.
    """
    from agents.parent_report_agent import _week_summary
    sb = get_supabase()

    student = (sb.table("students").select("*")
               .or_(f"email.eq.{user['email']},parent_phone.eq.{user.get('email')}")
               .limit(1).execute().data)
    if not student:
        return {"student_name": None, "summary": {}, "latest_report": None}
    student = student[0]

    latest = (sb.table("parent_reports").select("report_text, week_start")
              .eq("student_id", student["id"]).order("week_start", desc=True)
              .limit(1).execute().data)

    return {
        "student_name": student.get("name"),
        "summary": _week_summary(sb, student["id"]),
        "latest_report": latest[0]["report_text"] if latest else None,
    }


# ── Admin ─────────────────────────────────────────────────────────────────────
@app.get("/admin/analytics")
def admin_analytics(institute_id: str, user=Depends(require_role("admin"))):
    """Headline institute metrics + simple renewal/revenue signals."""
    from datetime import datetime, timedelta, timezone
    sb = get_supabase()

    students = (sb.table("students").select("id, last_active, streak_days")
                .eq("institute_id", institute_id).execute().data or [])
    total = len(students)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    def _active(s):
        la = s.get("last_active")
        if not la:
            return False
        try:
            return datetime.fromisoformat(str(la).replace("Z", "+00:00")) >= week_ago
        except Exception:
            return False

    active = sum(1 for s in students if _active(s))
    at_risk = (sb.table("alerts").select("id", count="exact")
               .eq("institute_id", institute_id).eq("is_read", False).execute().count or 0)
    tests_week = (sb.table("tests").select("id", count="exact")
                  .eq("institute_id", institute_id)
                  .gte("created_at", week_ago.isoformat()).execute().count or 0)

    renewal_pct = round((active / total) * 100, 1) if total else 0.0

    return {
        "active_students": active,
        "at_risk_count": at_risk,
        "tests_week": tests_week,
        "renewal_pct": renewal_pct,
        "engagement": [],  # wire up a weekly rollup table later
        "revenue_signals": [
            {"label": "Total enrolled", "value": total},
            {"label": "Engaged (7d)", "value": active},
            {"label": "Predicted renewals", "value": round(total * renewal_pct / 100)},
        ],
    }


# ── Debug (time-travel) ───────────────────────────────────────────────────────
@app.get("/debug/history/{thread_id}")
def debug_history(thread_id: str, user=Depends(require_role("admin", "teacher"))):
    """Replay/inspect every checkpoint of a past graph run (time-travel debugging)."""
    from graph.checkpointer import get_state_history
    return {"thread_id": thread_id, "history": get_state_history(thread_id)}


# ── helpers ───────────────────────────────────────────────────────────────────
def _resolve_student_id(user: dict) -> str:
    """Map an authenticated user to their students.id row."""
    sb = get_supabase()
    res = (sb.table("students").select("id").eq("auth_id", user["id"])
           .limit(1).execute()).data
    if not res:
        raise HTTPException(status_code=404, detail="No student profile for this account")
    return res[0]["id"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
