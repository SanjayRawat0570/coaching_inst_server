"""Smart Coaching Platform — FastAPI entry point.

Runs all endpoints + Supabase Auth + SSE streaming + APScheduler jobs.
Local: uvicorn main:app --reload --port 8000   |   HF Spaces: port 7860 (Dockerfile)
"""

import os
import uuid
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
    question_type: str = "mcq"  # "mcq" | "theory"


class ApproveTestRequest(BaseModel):
    test_id: str
    approved: bool = True
    edited_questions: list[dict] | None = None
    due_date: str | None = None  # F7: ISO date the student must take it by


class ParentGoalRequest(BaseModel):
    student_id: str
    target_college: str | None = None
    target_rank: int | None = None


class CreateChallengeRequest(BaseModel):
    opponent_email: str
    subject: str | None = None
    num_questions: int = 5


class GenerateClassTestRequest(BaseModel):
    institute_id: str | None = None
    subject: str | None = None
    num_questions: int = 10


class SubmitChallengeRequest(BaseModel):
    challenge_id: str
    answers: list = []  # chosen option index per question (null if skipped)


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
    parent_email: str | None = None  # for students: the parent's email used to link the parent account


class ProfileUpdateRequest(BaseModel):
    target_exam: str | None = None
    exam_date: str | None = None  # ISO date string, e.g. "2027-05-01"


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
    # institute_id maps to a UUID column; keep only valid UUIDs, else store NULL.
    institute_id = _as_uuid(req.institute_id)
    # Normalise the parent email (students only) so linking is case/space-insensitive.
    parent_email = (req.parent_email or "").strip().lower() or None
    try:
        res = sb.auth.admin.create_user({
            "email": req.email,
            "password": req.password,
            "email_confirm": True,
            "user_metadata": {
                "role": role, "name": req.name,
                "institute_id": institute_id, "parent_email": parent_email,
            },
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
                "parent_email": parent_email,
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
        background.add_task(_award_activity, student_id, "doubt")
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
        import re
        streamed = False        # did we forward any live tokens?
        final_answer = ""       # node's full answer, used as a fallback
        node_error = None       # node-level error captured from state
        try:
            async for event in graph.astream_events(initial, version="v2"):
                kind = event["event"]
                # Only stream the FINAL answer — the doubt node tags it "final_answer".
                # Without this filter the RAG pipeline's internal LLM calls (query
                # planning, HyDE, CRAG scoring) leak their tokens into the answer.
                if kind == "on_chat_model_stream" and "final_answer" in event.get("tags", []):
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        streamed = True
                        yield f"data: {chunk}\n\n"
                elif kind == "on_chain_start" and event.get("name") == "doubt":
                    yield "data: [STATUS]Searching notes and thinking…\n\n"
                elif kind == "on_chain_end" and event.get("name") == "doubt":
                    out = event.get("data", {}).get("output") or {}
                    if isinstance(out, dict):
                        final_answer = out.get("agent_output") or ""
                        node_error = out.get("error")
        except Exception as e:
            yield f"data: [ERROR]{e}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Fallback: the node ran but no tokens streamed (e.g. the model returned
        # all at once, or an internal step failed and was caught in state). Send
        # the final answer so the user never sees an empty bubble.
        if not streamed:
            if node_error:
                # node_error holds the real exception; agent_output is just a placeholder
                yield f"data: [ERROR]{node_error}\n\n"
            elif final_answer:
                # Collapse blank lines so they don't clash with the SSE "\n\n" delimiter.
                safe = re.sub(r"\n{2,}", "\n", final_answer.replace("\r\n", "\n"))
                yield f"data: {safe}\n\n"
            else:
                yield "data: [ERROR]No answer was generated. Please try again.\n\n"

        # Reward the student only when a real answer went out (not on error).
        if not node_error and (streamed or final_answer):
            _award_activity(student_id, "doubt")

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Tests ─────────────────────────────────────────────────────────────────────
@app.post("/test/generate")
def generate_test(req: GenerateTestRequest, user=Depends(require_role("teacher", "admin"))):
    """Generate a personalized test and publish it straight to the student (status 'ready')."""
    from agents.test_generator import test_generator_node
    from agents.reviewer_agent import reviewer_node, should_continue, MAX_ITERATIONS

    sb = get_supabase()

    # Teachers identify the student by email (e.g. their Gmail). For backward
    # compatibility we still accept a raw students.id (UUID) if one is passed.
    raw = (req.student_id or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Enter the student's email address.")

    if "@" in raw:
        student = (sb.table("students").select("id, institute_id")
                   .ilike("email", raw).limit(1).execute()).data
        if not student:
            raise HTTPException(
                status_code=404,
                detail=f"No student found with email '{raw}'.",
            )
        student_uuid = student[0]["id"]
    else:
        student_uuid = _as_uuid(raw)
        if not student_uuid:
            raise HTTPException(
                status_code=400,
                detail="Enter the student's email address (e.g. name@gmail.com).",
            )
        student = (sb.table("students").select("id, institute_id")
                   .eq("id", student_uuid).limit(1).execute()).data
        if not student:
            raise HTTPException(status_code=404, detail="No student found with that ID.")

    # Prefer the student's institute; fall back to the one the teacher sent. Empty
    # strings must become NULL — "" is not valid for a UUID column.
    institute_uuid = _as_uuid(student[0].get("institute_id")) or _as_uuid(req.institute_id)

    question_type = "theory" if str(req.question_type).lower() == "theory" else "mcq"
    state = {
        "student_id": student_uuid,
        "institute_id": institute_uuid or "",
        "action_type": "test",
        "subject": req.subject,
        "question_type": question_type,
        "iteration_count": 0,
        "conversation_history": [],
    }
    # Generate -> review -> regenerate loop (bounded)
    while True:
        state = test_generator_node(state, num_questions=req.num_questions)
        state = reviewer_node(state)
        if should_continue(state) == "approved" or state["iteration_count"] >= MAX_ITERATIONS:
            break

    # Save as "pending" so the teacher can review, adjust per-question marks, and
    # approve before it reaches the student (HITL — see /test/approve).
    row = sb.table("tests").insert({
        "student_id": student_uuid,
        "institute_id": institute_uuid,
        "subject": req.subject,
        "questions": state.get("test_questions") or [],
        "status": "pending",
        "teacher_approved": False,
    }).execute().data
    test_id = row[0]["id"] if row else None
    return {"test_id": test_id, "questions": state.get("test_questions"),
            "review_feedback": state.get("review_feedback"),
            "difficulty_level": state.get("difficulty_level"),
            "difficulty_mix": state.get("difficulty_mix")}


@app.post("/test/approve")
def approve_test(req: ApproveTestRequest, user=Depends(require_role("teacher", "admin"))):
    """HITL: teacher approves or edits a pending test before it reaches the student."""
    from datetime import date, timedelta
    sb = get_supabase()
    update = {"teacher_approved": bool(req.approved),
              "status": "ready" if req.approved else "rejected"}
    if req.edited_questions is not None:
        update["questions"] = req.edited_questions
    # F7: when sending to the student, set a due date (default 3 days out) so the
    # nightly job can flag it as "skipped" if it's never taken.
    if req.approved:
        update["due_date"] = req.due_date or (date.today() + timedelta(days=3)).isoformat()
    sb.table("tests").update(update).eq("id", req.test_id).execute()
    _audit("test_approved" if req.approved else "test_rejected", entity=req.test_id,
           actor_email=user.get("email"), role="teacher",
           detail={"status": update["status"]})  # F18
    return {"test_id": req.test_id, **update}


@app.post("/test/submit")
def submit_test(req: SubmitTestRequest, background: BackgroundTasks,
                user=Depends(get_current_user)):
    """Student submits answers -> evaluate -> progress/rank/flashcards (post-test flow)."""
    from agents.answer_evaluator import evaluator_node
    student_id = _resolve_student_id(user)
    sb = get_supabase()
    sb.table("tests").update({"answers": req.answers}).eq("id", req.test_id).execute()

    base_state = {
        "student_id": student_id,
        "institute_id": "",
        "action_type": "evaluate",
        "test_id": req.test_id,
        "iteration_count": 0,
        "conversation_history": [],
    }

    # 1) Evaluate FIRST and directly — this writes score/total_marks/status='evaluated'
    #    to the tests row, which is what every dashboard reads. Doing it here (instead
    #    of relying on the graph) guarantees the result is persisted even if a later
    #    post-test branch fails.
    ev = evaluator_node(base_state)
    evaluation = ev.get("evaluation_result")

    # 2) Run the post-test agents (progress / rank / flashcards) best-effort. Each is
    #    isolated so one failing never hides the result the student just earned.
    post_state = {**base_state, **ev}
    result = {}
    try:
        from agents.rank_predictor import rank_predictor_node
        r = rank_predictor_node(post_state) or {}
        result["air_rank"] = r.get("air_rank")
        result["air_rank_context"] = r.get("air_rank_context")
        post_state = {**post_state, **r}
    except Exception as e:
        print(f"[submit] rank prediction failed: {e}")
    try:
        from agents.progress_tracker import progress_tracker_node
        p = progress_tracker_node(post_state) or {}
        result["weakness_update"] = p.get("weakness_update")
    except Exception as e:
        print(f"[submit] progress update failed: {e}")
    try:
        from agents.flashcard_agent import flashcard_gen_node
        flashcard_gen_node(post_state)  # side effects only
    except Exception as e:
        print(f"[submit] flashcard generation failed: {e}")

    background.add_task(_award_activity, student_id, "test")

    # 3) Return the authoritative numbers from the DB row (evaluator wrote them).
    row = (sb.table("tests").select("score, total_marks, status")
           .eq("id", req.test_id).limit(1).execute().data) or []
    saved = row[0] if row else {}
    _audit("test_submitted", entity=req.test_id, actor_email=user.get("email"),
           role="student", detail={"score": saved.get("score"),
                                   "total_marks": saved.get("total_marks"),
                                   "integrity_flags": (evaluation or {}).get("integrity_flags", [])})  # F18 + F17
    return {
        "score": saved.get("score", ev.get("score")),
        "total_marks": saved.get("total_marks",
                                 (evaluation or {}).get("total_marks")),
        "evaluation": evaluation,
        "air_rank": result.get("air_rank"),
        "air_rank_context": result.get("air_rank_context"),
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
    student = (sb.table("students").select(
        "xp_points, streak_days, target_exam, "
        "predicted_rank, predicted_rank_context, predicted_rank_at")
               .eq("id", student_id).limit(1).execute()).data
    return {"weakness_map": weakness, "profile": student[0] if student else {},
            "recent_tests": _recent_results(sb, [student_id])}


@app.post("/activity/ping")
def activity_ping(user=Depends(get_current_user)):
    """F6: record that the logged-in student is active now (login/app-open signal)."""
    from datetime import datetime, timezone
    sb = get_supabase()
    _log_activity_event(sb, user.get("email"), "login")
    try:
        sb.table("students").update(
            {"last_active": datetime.now(timezone.utc).isoformat()}
        ).eq("id", _resolve_student_id(user)).execute()
    except Exception:
        pass
    return {"ok": True}


@app.post("/profile")
def update_profile(req: ProfileUpdateRequest, user=Depends(get_current_user)):
    """Let a student set their target exam (and exam date) shown on the progress page."""
    student_id = _resolve_student_id(user)
    update = {}
    if req.target_exam is not None:
        update["target_exam"] = req.target_exam.strip() or None
    if req.exam_date is not None:
        update["exam_date"] = req.exam_date or None
    if update:
        get_supabase().table("students").update(update).eq("id", student_id).execute()
    return {"ok": True, **update}


@app.get("/flashcards/due")
def flashcards_due(user=Depends(get_current_user)):
    from agents.flashcard_agent import due_cards
    return {"cards": due_cards(_resolve_student_id(user))}


@app.post("/flashcards/review")
def review_flashcard(req: ReviewCardRequest, background: BackgroundTasks,
                     user=Depends(get_current_user)):
    from agents.flashcard_agent import review_card
    result = review_card(req.card_id, req.quality)
    background.add_task(_award_activity, _resolve_student_id(user), "flashcard")
    return result


# ── F1: 7-day study plan ──────────────────────────────────────────────────────
@app.get("/student/plan")
def get_study_plan(user=Depends(get_current_user)):
    """Latest saved 7-day study plan for the logged-in student."""
    from agents.study_plan_agent import latest_plan
    return {"plan": latest_plan(_resolve_student_id(user))}


@app.post("/student/plan/generate")
def generate_study_plan(user=Depends(get_current_user)):
    """Generate a fresh 7-day plan from the student's weak concepts (Groq)."""
    from agents.study_plan_agent import build_plan
    sb = get_supabase()
    sid = _resolve_student_id(user)
    row = sb.table("students").select("*").eq("id", sid).limit(1).execute().data
    if not row:
        raise HTTPException(status_code=404, detail="No student profile.")
    return {"plan": build_plan(row[0])}


# ── F2: concept dependency map ────────────────────────────────────────────────
@app.get("/student/concept-map")
def get_concept_map(user=Depends(get_current_user)):
    """Tree of the student's weak concepts and their prerequisites (cached edges)."""
    from graph.knowledge_graph import prerequisites_of
    sb = get_supabase()
    sid = _resolve_student_id(user)
    weak = (sb.table("weakness_map").select("subject, concept, score")
            .eq("student_id", sid).order("score", desc=False).limit(6).execute()).data or []
    nodes = [{"concept": w["concept"], "subject": w.get("subject"),
              "score": w.get("score"), "prerequisites": prerequisites_of(w["concept"])}
             for w in weak]
    has_edges = any(n["prerequisites"] for n in nodes)
    return {"nodes": nodes, "built": has_edges}


@app.post("/student/concept-map/build")
def build_concept_map(user=Depends(get_current_user)):
    """Infer & cache prerequisites (via LLM) for the student's weak concepts."""
    from graph.knowledge_graph import link_prerequisites, prerequisites_of
    sb = get_supabase()
    sid = _resolve_student_id(user)
    weak = (sb.table("weakness_map").select("subject, concept, score")
            .eq("student_id", sid).order("score", desc=False).limit(6).execute()).data or []
    nodes = []
    for w in weak:
        link_prerequisites(w["concept"], subject=w.get("subject"))
        nodes.append({"concept": w["concept"], "subject": w.get("subject"),
                      "score": w.get("score"), "prerequisites": prerequisites_of(w["concept"])})
    return {"nodes": nodes, "built": True}


# ── Gamification (F10 leaderboard · F11 badges · F12 challenges) ───────────────
@app.get("/leaderboard")
def leaderboard(user=Depends(get_current_user)):
    """F10: top-10 students by XP within the requester's institute."""
    sb = get_supabase()
    sid = _resolve_student_id(user)
    me = (sb.table("students").select("institute_id").eq("id", sid).limit(1).execute().data) or []
    inst = _as_uuid(me[0].get("institute_id")) if me else None
    q = sb.table("students").select("id, name, email, xp_points, streak_days")
    q = q.eq("institute_id", inst) if inst else q.is_("institute_id", "null")
    rows = q.order("xp_points", desc=True).limit(10).execute().data or []
    board = [{
        "rank": i + 1,
        "name": r.get("name") or r.get("email") or "Student",
        "xp": r.get("xp_points") or 0,
        "streak": r.get("streak_days") or 0,
        "is_me": r["id"] == sid,
    } for i, r in enumerate(rows)]
    return {"leaderboard": board}


@app.get("/badges")
def get_badges(user=Depends(get_current_user)):
    """F11: badge shelf — re-evaluates + awards, then returns earned/locked state."""
    sid = _resolve_student_id(user)
    earned = _award_badges(sid)
    shelf = [{**b, "earned": b["key"] in earned} for b in BADGE_CATALOG]
    return {"badges": shelf, "earned_count": len(earned)}


def _grade_mcq(questions: list, answers: list) -> tuple:
    """F12: auto-grade an MCQ challenge by answer_index. Returns (score, total)."""
    score, total = 0, 0
    for i, q in enumerate(questions or []):
        marks = q.get("marks", 4)
        total += marks
        ans = answers[i] if i < len(answers) else None
        if ans is None:
            continue
        if ans == q.get("answer_index"):
            score += marks
        else:
            score -= q.get("negative", 1)
    return max(0, score), total


@app.post("/challenge/create")
def create_challenge(req: CreateChallengeRequest, user=Depends(get_current_user)):
    """F12: challenge a classmate — generates one shared MCQ test for both to take."""
    from agents.test_generator import test_generator_node
    sb = get_supabase()
    me = _resolve_student_id(user)
    opp = (sb.table("students").select("id, institute_id")
           .ilike("email", req.opponent_email.strip()).limit(1).execute().data) or []
    if not opp:
        raise HTTPException(status_code=404, detail=f"No classmate found with email '{req.opponent_email}'.")
    if opp[0]["id"] == me:
        raise HTTPException(status_code=400, detail="You can't challenge yourself.")

    state = {"student_id": me, "institute_id": opp[0].get("institute_id") or "",
             "subject": req.subject, "question_type": "mcq",
             "iteration_count": 0, "conversation_history": []}
    state = test_generator_node(state, num_questions=req.num_questions)
    qs = [q for q in (state.get("test_questions") or []) if q.get("options")]
    if not qs:
        raise HTTPException(status_code=502, detail="Could not generate a challenge test, try again.")

    row = sb.table("challenges").insert({
        "challenger_id": me, "opponent_id": opp[0]["id"],
        "subject": req.subject, "questions": qs, "status": "pending",
    }).execute().data
    return {"challenge_id": row[0]["id"] if row else None, "questions_count": len(qs)}


@app.get("/challenges")
def my_challenges(user=Depends(get_current_user)):
    """F12: all challenges I'm part of, with names, scores and a comparison view."""
    sb = get_supabase()
    me = _resolve_student_id(user)
    rows = (sb.table("challenges").select("*")
            .or_(f"challenger_id.eq.{me},opponent_id.eq.{me}")
            .order("created_at", desc=True).limit(30).execute().data) or []
    ids = {r["challenger_id"] for r in rows} | {r["opponent_id"] for r in rows}
    names = {}
    if ids:
        ns = sb.table("students").select("id, name, email").in_("id", list(ids)).execute().data or []
        names = {n["id"]: (n.get("name") or n.get("email") or "Student") for n in ns}
    out = []
    for r in rows:
        mine = "challenger" if r["challenger_id"] == me else "opponent"
        other = "opponent" if mine == "challenger" else "challenger"
        my_done = r.get(f"{mine}_score") is not None
        out.append({
            "id": r["id"], "subject": r.get("subject"), "status": r.get("status"),
            "questions_count": len(r.get("questions") or []),
            "my_turn": not my_done,
            "my_score": r.get(f"{mine}_score"), "my_total": r.get(f"{mine}_total"),
            "opp_name": names.get(r[f"{other}_id"]),
            "opp_score": r.get(f"{other}_score"), "opp_total": r.get(f"{other}_total"),
            "challenger_name": names.get(r["challenger_id"]),
        })
    return {"challenges": out}


@app.get("/challenge/{challenge_id}/take")
def take_challenge(challenge_id: str, user=Depends(get_current_user)):
    """F12: fetch the shared questions to take (answer keys stripped)."""
    sb = get_supabase()
    me = _resolve_student_id(user)
    ch = (sb.table("challenges").select("*").eq("id", challenge_id).limit(1).execute().data) or []
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found.")
    c = ch[0]
    if me not in (c["challenger_id"], c["opponent_id"]):
        raise HTTPException(status_code=403, detail="Not your challenge.")
    mine = "challenger" if me == c["challenger_id"] else "opponent"
    if c.get(f"{mine}_score") is not None:
        raise HTTPException(status_code=400, detail="You've already taken this challenge.")
    qs = [{k: v for k, v in q.items() if k != "answer_index"} for q in (c.get("questions") or [])]
    return {"id": c["id"], "subject": c.get("subject"), "questions": qs}


@app.post("/challenge/submit")
def submit_challenge(req: SubmitChallengeRequest, background: BackgroundTasks,
                     user=Depends(get_current_user)):
    """F12: grade my attempt; mark complete once both sides have played."""
    sb = get_supabase()
    me = _resolve_student_id(user)
    ch = (sb.table("challenges").select("*").eq("id", req.challenge_id).limit(1).execute().data) or []
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found.")
    c = ch[0]
    if me not in (c["challenger_id"], c["opponent_id"]):
        raise HTTPException(status_code=403, detail="Not your challenge.")
    mine = "challenger" if me == c["challenger_id"] else "opponent"
    if c.get(f"{mine}_score") is not None:
        raise HTTPException(status_code=400, detail="You've already taken this challenge.")

    score, total = _grade_mcq(c.get("questions") or [], req.answers or [])
    other = "opponent" if mine == "challenger" else "challenger"
    update = {f"{mine}_score": score, f"{mine}_total": total,
              "status": "complete" if c.get(f"{other}_score") is not None else "awaiting_opponent"}
    sb.table("challenges").update(update).eq("id", req.challenge_id).execute()
    background.add_task(_award_activity, me, "test")
    return {"score": score, "total": total, "status": update["status"]}


# ── Teacher / admin ───────────────────────────────────────────────────────────
@app.get("/teacher/alerts")
def teacher_alerts(institute_id: str, user=Depends(require_role("teacher", "admin"))):
    sb = get_supabase()
    alerts = (sb.table("alerts").select("*")
              .eq("institute_id", institute_id).eq("is_read", False)
              .order("risk_score", desc=True).execute()).data
    return {"alerts": alerts}


@app.get("/teacher/overview")
def teacher_overview(institute_id: str = "", user=Depends(require_role("teacher", "admin"))):
    """Class heatmap (avg concept mastery) + at-risk alerts + most-asked doubts.

    Scopes to the teacher's institute when given a valid one; otherwise spans all
    students (single-institute / demo setups where accounts have no institute).
    """
    from datetime import datetime, timedelta, timezone
    sb = get_supabase()
    inst = _as_uuid(institute_id)

    students_q = sb.table("students").select("id")
    if inst:
        students_q = students_q.eq("institute_id", inst)
    student_ids = [s["id"] for s in (students_q.execute().data or [])]

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

    alerts_q = sb.table("alerts").select("*").eq("is_read", False)
    if inst:
        alerts_q = alerts_q.eq("institute_id", inst)
    alerts = (alerts_q.order("risk_score", desc=True).execute().data or [])

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
def teacher_pending_tests(institute_id: str = "", user=Depends(require_role("teacher", "admin"))):
    sb = get_supabase()
    q = (sb.table("tests").select("id, student_id, subject, questions, status, created_at")
         .eq("status", "pending").order("created_at", desc=True))
    inst = _as_uuid(institute_id)
    if inst:
        q = q.eq("institute_id", inst)
    return {"tests": q.execute().data or []}


@app.get("/teacher/submissions")
def teacher_submissions(institute_id: str = "", user=Depends(require_role("teacher", "admin"))):
    """Tests students have submitted (status 'evaluated'), with scores — newest first.

    Filters by institute when a valid institute_id is given; otherwise returns all
    submissions (single-institute / demo setups where students have no institute).
    """
    sb = get_supabase()
    q = (sb.table("tests")
         .select("id, student_id, subject, score, total_marks, status, created_at")
         .eq("status", "evaluated").order("created_at", desc=True))
    inst = _as_uuid(institute_id)
    if inst:
        q = q.eq("institute_id", inst)
    tests = q.limit(100).execute().data or []

    # Attach the student's name/email to each submission.
    ids = list({t["student_id"] for t in tests if t.get("student_id")})
    names = {}
    if ids:
        srows = (sb.table("students").select("id, name, email")
                 .in_("id", ids).execute().data or [])
        names = {s["id"]: s for s in srows}
    for t in tests:
        s = names.get(t.get("student_id")) or {}
        t["student_name"] = s.get("name") or s.get("email") or "Unknown"
        t["percent"] = (round((t.get("score") or 0) / t["total_marks"] * 100)
                        if t.get("total_marks") else None)
    return {"submissions": tests}


@app.get("/teacher/students")
def teacher_students(institute_id: str = "", user=Depends(require_role("teacher", "admin"))):
    """Roster of students (name + email) so a teacher can pick one to generate a test for.

    Filters by institute when a valid institute_id is given; otherwise returns all
    students (single-institute / demo setups where students have no institute).
    """
    sb = get_supabase()
    q = (sb.table("students")
         .select("id, name, email, target_exam, institute_id")
         .order("name"))
    inst = _as_uuid(institute_id)
    if inst:
        q = q.eq("institute_id", inst)
    students = q.limit(500).execute().data or []
    return {"students": students}


# ── F13: generate one personalized test per student in a class ─────────────────
@app.post("/teacher/tests/generate-class")
def generate_class_tests(req: GenerateClassTestRequest, user=Depends(require_role("teacher", "admin"))):
    """F13: loop the class and generate a weakness-targeted test for each student."""
    from agents.test_generator import test_generator_node
    sb = get_supabase()
    inst = _as_uuid(req.institute_id)
    q = sb.table("students").select("id, name, email, institute_id")
    q = q.eq("institute_id", inst) if inst else q.is_("institute_id", "null")
    students = q.limit(100).execute().data or []

    results = []
    for s in students:
        label = s.get("name") or s.get("email") or s["id"]
        try:
            state = {"student_id": s["id"], "institute_id": s.get("institute_id") or "",
                     "subject": req.subject, "question_type": "mcq",
                     "iteration_count": 0, "conversation_history": []}
            state = test_generator_node(state, num_questions=req.num_questions)
            qs = state.get("test_questions") or []
            if not qs:
                results.append({"student": label, "ok": False, "reason": "no questions generated"})
                continue
            sb.table("tests").insert({
                "student_id": s["id"], "institute_id": _as_uuid(s.get("institute_id")),
                "subject": req.subject, "questions": qs,
                "status": "pending", "teacher_approved": False,
            }).execute()
            results.append({"student": label, "ok": True, "questions": len(qs)})
        except Exception as e:
            results.append({"student": label, "ok": False, "reason": str(e)})

    return {"students": len(students),
            "generated": sum(1 for r in results if r["ok"]), "results": results}


# ── F15: month-vs-month class scores ──────────────────────────────────────────
@app.get("/teacher/monthly-scores")
def teacher_monthly_scores(institute_id: str = "", student_id: str = "", months: int = 6,
                           user=Depends(require_role("teacher", "admin"))):
    """F15: average evaluated-test score (%) per calendar month.

    Scoped to one student when `student_id` is given, else the whole class.
    """
    from datetime import datetime, timezone, timedelta
    sb = get_supabase()
    since = (datetime.now(timezone.utc) - timedelta(days=months * 31)).isoformat()
    q = (sb.table("tests").select("score, total_marks, created_at")
         .eq("status", "evaluated").gte("created_at", since))
    sid = _as_uuid(student_id)
    if sid:
        q = q.eq("student_id", sid)
    else:
        inst = _as_uuid(institute_id)
        if inst:
            q = q.eq("institute_id", inst)
    rows = q.limit(5000).execute().data or []

    buckets = {}
    for r in rows:
        if not r.get("total_marks"):
            continue
        try:
            dt = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
        except Exception:
            continue
        buckets.setdefault(dt.strftime("%Y-%m"), []).append(r["score"] / r["total_marks"] * 100)
    monthly = [{"month": k, "avg_pct": round(sum(v) / len(v), 1), "tests": len(v)}
               for k, v in sorted(buckets.items())]
    return {"monthly": monthly}


# ── F3: doubt clusters ────────────────────────────────────────────────────────
@app.get("/teacher/doubt-clusters")
def teacher_doubt_clusters(institute_id: str = "", user=Depends(require_role("teacher", "admin"))):
    """Top clusters of similar student doubts (computed nightly)."""
    from agents.doubt_cluster_agent import top_clusters
    return {"clusters": top_clusters(institute_id)}


@app.post("/teacher/doubt-clusters/build")
def teacher_build_doubt_clusters(user=Depends(require_role("teacher", "admin"))):
    """Recompute doubt clusters now (also runs nightly via the scheduler)."""
    from agents.doubt_cluster_agent import cluster_doubts
    return cluster_doubts(days=7)


@app.post("/teacher/inactivity-check")
def run_inactivity_check(user=Depends(require_role("teacher", "admin"))):
    """F7: run the inactivity / skipped-test check now (also runs nightly at 9PM).

    Emails teacher+parent for each flagged student and returns the reasons so the
    rule can be verified even if email delivery isn't configured.
    """
    from agents.inactivity_alert_agent import run_nightly
    return run_nightly()


@app.get("/teacher/activity-heatmap")
def teacher_activity_heatmap(institute_id: str = "", days: int = 14,
                             user=Depends(require_role("teacher", "admin"))):
    """F6: 24-hour activity heatmap (IST) for the teacher's whole class.

    The class roster is resolved by institute, then activity is matched by the
    students' emails (the tracking key).
    """
    sb = get_supabase()
    iid = _as_uuid(institute_id)
    q = sb.table("students").select("email")
    q = q.eq("institute_id", iid) if iid else q.is_("institute_id", "null")
    emails = [s["email"] for s in (q.execute().data or []) if s.get("email")]
    return _activity_heatmap(emails=emails, days=days)


@app.post("/teacher/alerts/read")
def mark_alert_read(req: MarkAlertRequest, user=Depends(require_role("teacher", "admin"))):
    sb = get_supabase()
    sb.table("alerts").update({"is_read": True}).eq("id", req.alert_id).execute()
    return {"alert_id": req.alert_id, "is_read": True}


# ── Parent ────────────────────────────────────────────────────────────────────
@app.get("/parent/report")
def parent_report(user=Depends(require_role("parent"))):
    """Latest weekly report + this week's summary for each of the parent's children.

    A parent is linked to a student by students.parent_email == the parent's login
    email. The child enters this address when signing up. A parent may have more
    than one child, so we return a `children` list; the top-level fields mirror the
    first child for backward compatibility.
    """
    from agents.parent_report_agent import _week_summary
    sb = get_supabase()

    # Match case-insensitively against the normalised (lowercased) parent_email.
    parent_email = (user.get("email") or "").strip().lower()
    students = (sb.table("students").select("*")
                .eq("parent_email", parent_email)
                .order("created_at").execute().data) or []
    if not students:
        return {"student_name": None, "summary": {}, "latest_report": None, "children": []}

    children = []
    for student in students:
        latest = (sb.table("parent_reports").select("report_text, week_start")
                  .eq("student_id", student["id"]).order("week_start", desc=True)
                  .limit(1).execute().data)
        children.append({
            "student_id": student["id"],
            "student_name": student.get("name"),
            "summary": _week_summary(sb, student["id"]),
            "latest_report": latest[0]["report_text"] if latest else None,
            "recent_tests": _recent_results(sb, [student["id"]]),
            # F9: goal + progress toward it (from the F5 predicted rank).
            "predicted_rank": student.get("predicted_rank"),
            "target_college": student.get("target_college"),
            "target_rank": student.get("target_rank"),
            "goal_progress": _goal_progress(student.get("predicted_rank"), student.get("target_rank")),
        })

    first = children[0]
    return {**first, "children": children}


@app.post("/parent/goal")
def set_parent_goal(req: ParentGoalRequest, user=Depends(require_role("parent"))):
    """F9: parent sets a target college + rank for one of their children."""
    sb = get_supabase()
    parent_email = (user.get("email") or "").strip().lower()
    child = (sb.table("students").select("id, predicted_rank")
             .eq("id", req.student_id).eq("parent_email", parent_email)
             .limit(1).execute().data) or []
    if not child:
        raise HTTPException(status_code=403, detail="That student is not linked to your account.")
    update = {}
    if req.target_college is not None:
        update["target_college"] = req.target_college.strip() or None
    if req.target_rank is not None:
        update["target_rank"] = req.target_rank
    if update:
        sb.table("students").update(update).eq("id", req.student_id).execute()
        _audit("goal_set", entity=req.student_id, actor_email=user.get("email"),
               role="parent", detail=update)  # F18
    return {"ok": True, **update,
            "goal_progress": _goal_progress(child[0].get("predicted_rank"), update.get("target_rank", req.target_rank))}


@app.post("/parent/report/send")
def parent_report_send_now(user=Depends(require_role("parent"))):
    """F8: build + email this week's report for the parent's children right now
    (the same report the Sunday 8PM job sends). Useful for testing/preview."""
    from agents.parent_report_agent import build_report
    sb = get_supabase()
    parent_email = (user.get("email") or "").strip().lower()
    students = (sb.table("students").select("*")
                .eq("parent_email", parent_email).execute().data) or []
    results = []
    for s in students:
        r = build_report(s)
        results.append({"student_name": s.get("name"),
                        "delivered": r["delivery"].get("ok"),
                        "channels": r.get("channels")})
    return {"children": len(students), "results": results}


@app.get("/parent/activity-heatmap")
def parent_activity_heatmap(days: int = 14, user=Depends(require_role("parent"))):
    """F6: 24-hour activity heatmap (IST) across the parent's linked children."""
    sb = get_supabase()
    parent_email = (user.get("email") or "").strip().lower()
    students = (sb.table("students").select("email")
                .eq("parent_email", parent_email).execute().data) or []
    return _activity_heatmap(emails=[s["email"] for s in students], days=days)


# ── Admin ─────────────────────────────────────────────────────────────────────
@app.get("/admin/audit-logs")
def admin_audit_logs(action: str = "", q: str = "", limit: int = 200,
                     user=Depends(require_role("admin"))):
    """F18: filterable audit trail of test / badge / goal actions."""
    sb = get_supabase()
    query = sb.table("audit_logs").select("*").order("created_at", desc=True)
    if action:
        query = query.eq("action", action)
    rows = query.limit(max(1, min(limit, 1000))).execute().data or []
    if q:
        ql = q.strip().lower()
        rows = [r for r in rows
                if ql in (r.get("actor_email") or "").lower()
                or ql in (r.get("entity") or "").lower()
                or ql in str(r.get("detail") or "").lower()]
    return {"logs": rows,
            "actions": ["test_submitted", "test_approved", "test_rejected",
                        "badge_earned", "goal_set"]}


@app.get("/admin/analytics")
def admin_analytics(institute_id: str = "", user=Depends(require_role("admin"))):
    """Full institute view for an admin: headline metrics, every student record,
    and every auth account grouped by role (students / teachers / parents / admins).

    `institute_id` is optional — when blank (or not a UUID) the admin gets a
    platform-wide view across all institutes. Uses the service-role key, so it
    bypasses RLS and can read every account.
    """
    from datetime import datetime, timedelta, timezone
    sb = get_supabase()
    iid = _as_uuid(institute_id)  # None → no institute filter (see everything)

    # ── Students (full records) ────────────────────────────────────────────
    sq = sb.table("students").select(
        "id, name, email, parent_email, phone, target_exam, exam_date, "
        "xp_points, streak_days, last_active, institute_id, created_at"
    )
    if iid:
        sq = sq.eq("institute_id", iid)
    students = sq.order("created_at", desc=True).execute().data or []
    total = len(students)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    def _active(s):
        dt = _parse_dt(s.get("last_active"))
        return bool(dt and dt >= week_ago)

    active = sum(1 for s in students if _active(s))

    aq = sb.table("alerts").select("id", count="exact").eq("is_read", False)
    if iid:
        aq = aq.eq("institute_id", iid)
    at_risk = aq.execute().count or 0

    tq = sb.table("tests").select("id", count="exact").gte("created_at", week_ago.isoformat())
    if iid:
        tq = tq.eq("institute_id", iid)
    tests_week = tq.execute().count or 0

    engagement_rate = round((active / total) * 100, 1) if total else 0.0

    # ── All auth accounts, grouped by role ─────────────────────────────────
    accounts = {"student": [], "teacher": [], "parent": [], "admin": []}
    try:
        res = sb.auth.admin.list_users()
        users = res if isinstance(res, list) else getattr(res, "users", []) or []
        for u in users:
            meta = u.user_metadata or {}
            role = meta.get("role") or "student"
            entry = {
                "id": u.id,
                "email": u.email,
                "name": meta.get("name") or u.email,
                "role": role,
                "institute_id": meta.get("institute_id"),
                "parent_email": meta.get("parent_email"),
                "created_at": str(getattr(u, "created_at", "") or ""),
                "last_sign_in": str(getattr(u, "last_sign_in_at", "") or ""),
            }
            accounts.setdefault(role, []).append(entry)
    except Exception as e:
        print(f"[admin] list_users failed: {e}")

    return {
        "active_students": active,
        "at_risk_count": at_risk,
        "tests_week": tests_week,
        "engagement_rate": engagement_rate,  # active/total % — a real, computed metric
        "engagement": _weekly_engagement(sb, [s["id"] for s in students]),
        "counts": {
            "students": len(accounts["student"]),
            "teachers": len(accounts["teacher"]),
            "parents": len(accounts["parent"]),
            "admins": len(accounts["admin"]),
        },
        "students": students,
        "recent_results": _recent_results(sb, [s["id"] for s in students],
                                          limit=20, with_names=True),
        "teachers": accounts["teacher"],
        "parents": accounts["parent"],
        "admins": accounts["admin"],
        "student_accounts": accounts["student"],
    }


# ── Debug (time-travel) ───────────────────────────────────────────────────────
@app.get("/debug/history/{thread_id}")
def debug_history(thread_id: str, user=Depends(require_role("admin", "teacher"))):
    """Replay/inspect every checkpoint of a past graph run (time-travel debugging)."""
    from graph.checkpointer import get_state_history
    return {"thread_id": thread_id, "history": get_state_history(thread_id)}


# ── helpers ───────────────────────────────────────────────────────────────────
def _as_uuid(value) -> str | None:
    """Return value as a canonical UUID string, or None if it isn't a valid UUID."""
    try:
        return str(uuid.UUID(str(value))) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _parse_dt(value):
    """Parse a stored timestamp to a tz-aware datetime (naive values are treated as
    UTC). Returns None if unparseable. Avoids the naive-vs-aware comparison crash."""
    from datetime import datetime, timezone
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _weekly_engagement(sb, student_ids: list[str], weeks: int = 6) -> list[dict]:
    """Real weekly active-student counts over the last `weeks` weeks.

    A student is 'active' in a week if they asked a doubt or took a test that week.
    Returns a continuous series [{week, active}] so the chart never has gaps.
    """
    from datetime import datetime, timezone, timedelta
    ids = [i for i in (student_ids or []) if i]
    if not ids:
        return []
    now = datetime.now(timezone.utc)
    start = now - timedelta(weeks=weeks)
    buckets = {}  # Monday-of-week date -> set(student_id)
    for tbl in ("doubt_logs", "tests"):
        try:
            rows = (sb.table(tbl).select("student_id, created_at")
                    .in_("student_id", ids)
                    .gte("created_at", start.isoformat()).execute().data) or []
        except Exception as e:
            print(f"[engagement] {tbl} fetch failed: {e}")
            rows = []
        for r in rows:
            dt = _parse_dt(r.get("created_at"))
            if not dt:
                continue
            monday = (dt - timedelta(days=dt.weekday())).date()
            buckets.setdefault(monday, set()).add(r.get("student_id"))
    this_monday = (now - timedelta(days=now.weekday())).date()
    series = []
    for i in range(weeks - 1, -1, -1):
        wk = this_monday - timedelta(weeks=i)
        series.append({"week": wk.strftime("%b %d"), "active": len(buckets.get(wk, set()))})
    return series


def _recent_results(sb, student_ids: list[str], limit: int = 10,
                    with_names: bool = False) -> list[dict]:
    """Recent evaluated test results for the given students, newest first.

    Returns each test's score, total and computed percent so the student, parent
    and admin dashboards can all show the same result once a test is submitted.
    Set with_names=True (admin/multi-student views) to attach the student's name.
    """
    ids = [i for i in (student_ids or []) if i]
    if not ids:
        return []
    rows = (sb.table("tests")
            .select("id, student_id, subject, score, total_marks, status, created_at")
            .in_("student_id", ids)
            .eq("status", "evaluated")
            .order("created_at", desc=True)
            .limit(limit).execute().data) or []
    names = {}
    if with_names:
        srows = (sb.table("students").select("id, name, email")
                 .in_("id", ids).execute().data) or []
        names = {s["id"]: s for s in srows}
    for t in rows:
        t["percent"] = (round((t.get("score") or 0) / t["total_marks"] * 100)
                        if t.get("total_marks") else None)
        if with_names:
            s = names.get(t.get("student_id")) or {}
            t["student_name"] = s.get("name") or s.get("email") or "Unknown"
    return rows


# XP granted per activity — keeps the progress page's gamification meaningful.
XP_REWARDS = {"doubt": 10, "test": 50, "flashcard": 5}


def _award_activity(student_id: str, kind: str) -> None:
    """Grant XP for an activity and roll the daily streak forward.

    Streak rules (by calendar day, UTC):
      • already active today      -> streak unchanged (min 1)
      • last active yesterday     -> streak + 1
      • never / older than a day  -> streak reset to 1

    Best-effort: it swallows errors so a DB hiccup can never break the
    user-facing response (doubt answer, test result, etc.).
    """
    from datetime import datetime, timedelta, timezone
    try:
        sb = get_supabase()
        row = (sb.table("students").select("xp_points, streak_days, last_active, email")
               .eq("id", student_id).limit(1).execute()).data
        cur = row[0] if row else {}

        today = datetime.now(timezone.utc).date()
        last_date = None
        if cur.get("last_active"):
            try:
                last_date = datetime.fromisoformat(
                    str(cur["last_active"]).replace("Z", "+00:00")
                ).date()
            except ValueError:
                last_date = None

        streak = int(cur.get("streak_days") or 0)
        if last_date == today:
            new_streak = max(streak, 1)
        elif last_date == today - timedelta(days=1):
            new_streak = streak + 1
        else:
            new_streak = 1

        sb.table("students").update({
            "xp_points": int(cur.get("xp_points") or 0) + XP_REWARDS.get(kind, 0),
            "streak_days": new_streak,
            "last_active": datetime.now(timezone.utc).isoformat(),
        }).eq("id", student_id).execute()
        # F6: timestamped event for the 24-hour activity heatmap (tracked by email).
        _log_activity_event(sb, cur.get("email"), kind)
        # F11: re-check badge criteria after each activity (best-effort).
        _award_badges(student_id)
    except Exception as e:
        print(f"[gamify] award failed for {student_id}: {e}")


def _audit(action: str, entity: str = None, actor_email: str = None,
           role: str = None, detail: dict = None) -> None:
    """F18: append an immutable audit row. Best-effort — never breaks the caller."""
    try:
        get_supabase().table("audit_logs").insert({
            "actor_email": (actor_email or "").strip().lower() or None,
            "role": role,
            "action": action,
            "entity": entity,
            "detail": detail or {},
        }).execute()
    except Exception as e:
        print(f"[audit] log failed ({action}): {e}")


# F11 — badge catalog (icon names map to frontend Icon component).
BADGE_CATALOG = [
    {"key": "first_doubt", "name": "Curious Mind", "desc": "Asked your first doubt", "icon": "doubt"},
    {"key": "streak_7",    "name": "On Fire",      "desc": "7-day study streak",     "icon": "streak"},
    {"key": "doubts_100",  "name": "Question Master", "desc": "Asked 100 doubts",    "icon": "doubts"},
    {"key": "score_90",    "name": "Ace",          "desc": "Scored 90%+ on a test",  "icon": "trophy"},
]


def _evaluate_badges(sb, student_id: str) -> set:
    """F11: which badge keys the student currently qualifies for (from live data)."""
    earned = set()
    try:
        prof = (sb.table("students").select("streak_days")
                .eq("id", student_id).limit(1).execute().data) or []
        if prof and (prof[0].get("streak_days") or 0) >= 7:
            earned.add("streak_7")
        dcount = (sb.table("doubt_logs").select("id", count="exact")
                  .eq("student_id", student_id).execute()).count or 0
        if dcount >= 1:
            earned.add("first_doubt")
        if dcount >= 100:
            earned.add("doubts_100")
        tests = (sb.table("tests").select("score, total_marks")
                 .eq("student_id", student_id).eq("status", "evaluated").execute().data) or []
        if any(t.get("total_marks") and (t["score"] / t["total_marks"]) >= 0.9 for t in tests):
            earned.add("score_90")
    except Exception as e:
        print(f"[badges] evaluate failed: {e}")
    return earned


def _award_badges(student_id: str) -> set:
    """F11: persist any newly-earned badges; returns the full earned set."""
    sb = get_supabase()
    earned = _evaluate_badges(sb, student_id)
    try:
        already = {b["badge_key"] for b in (sb.table("badges").select("badge_key")
                   .eq("student_id", student_id).execute().data or [])}
        new_keys = earned - already
        if new_keys:
            prof = (sb.table("students").select("email")
                    .eq("id", student_id).limit(1).execute().data) or []
            email = prof[0].get("email") if prof else None
            for key in new_keys:
                try:
                    sb.table("badges").insert({"student_id": student_id, "badge_key": key}).execute()
                    _audit("badge_earned", entity=key, actor_email=email, role="student",
                           detail={"badge": key})  # F18
                except Exception as e:
                    print(f"[badges] insert {key} failed: {e}")
    except Exception as e:
        print(f"[badges] award failed: {e}")
    return earned


def _log_activity_event(sb, student_email: str, kind: str) -> None:
    """F6: append a timestamped row to activity_log, keyed by student email.

    Best-effort — a logging failure must never break the caller's response.
    """
    if not student_email:
        return
    try:
        sb.table("activity_log").insert({
            "student_email": (student_email or "").strip().lower(),
            "kind": kind,
        }).execute()
    except Exception as e:
        print(f"[activity] log failed for {student_email}: {e}")


# IST (Asia/Kolkata) — activity is bucketed by local hour so the heatmap reads
# naturally for Indian students/teachers, even though timestamps are stored in UTC.
from datetime import timezone as _tz, timedelta as _td
_IST = _tz(_td(hours=5, minutes=30))


def _rank_band_midpoint(text):
    """F9: pull a single number out of a predicted-rank band like 'AIR 8,000 - 12,000'."""
    import re
    if not text:
        return None
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", str(text))]
    nums = [n for n in nums if n > 0]
    return sum(nums) / len(nums) if nums else None


def _goal_progress(predicted_text, target_rank):
    """F9: progress toward the goal rank (lower AIR is better). Returns 0–100 or None."""
    cur = _rank_band_midpoint(predicted_text)
    if not cur or not target_rank:
        return None
    if cur <= target_rank:
        return 100
    return max(0, min(100, round(target_rank / cur * 100)))


def _activity_heatmap(emails=None, days: int = 14) -> dict:
    """Aggregate activity_log into 24 hour-of-day buckets (IST) over `days`.

    Scoped to the given list of student `emails` (a class roster or a parent's
    children). Returns {hours: [24 ints], total, days}.
    """
    from datetime import datetime
    buckets = [0] * 24
    emails = [e.strip().lower() for e in (emails or []) if e]
    if not emails:
        return {"hours": buckets, "total": 0, "days": days}
    try:
        sb = get_supabase()
        since = (datetime.now(_tz.utc) - _td(days=days)).isoformat()
        rows = (sb.table("activity_log").select("created_at")
                .in_("student_email", emails)
                .gte("created_at", since).limit(50000).execute().data) or []
        for r in rows:
            try:
                dt = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz.utc)
                buckets[dt.astimezone(_IST).hour] += 1
            except Exception:
                continue
    except Exception as e:
        print(f"[activity] heatmap failed: {e}")
    return {"hours": buckets, "total": sum(buckets), "days": days}


def _resolve_student_id(user: dict) -> str:
    """Map an authenticated user to their students.id row.

    Lazily provisions the profile row the first time we see a student. The
    frontend also upserts on login, but that runs with the anon key and can be
    blocked by RLS; this backend call uses the service-role key, so it always
    succeeds and prevents a "no student profile" 404 on a freshly signed-up user.
    """
    sb = get_supabase()
    res = (sb.table("students").select("id").eq("auth_id", user["id"])
           .limit(1).execute()).data
    if res:
        return res[0]["id"]

    # Only students get an auto-created profile; other roles genuinely have none.
    if (user.get("role") or "student") != "student":
        raise HTTPException(status_code=404, detail="No student profile for this account")

    parent_email = (user.get("parent_email") or "").strip().lower() or None
    created = (sb.table("students").insert({
        "auth_id": user["id"],
        "name": user.get("name") or user.get("email"),
        "email": user.get("email"),
        # institute_id is a UUID column — ignore non-UUID values (e.g. "678909")
        "institute_id": _as_uuid(user.get("institute_id")),
        "parent_email": parent_email,
    }).execute()).data
    if not created:
        raise HTTPException(status_code=404, detail="Could not create student profile")
    return created[0]["id"]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
