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

    # student_id must be a real students.id (UUID). Give a clear 400 instead of a
    # 500 when a teacher pastes something that isn't (e.g. a roll number like "9098").
    student_uuid = _as_uuid(req.student_id)
    if not student_uuid:
        raise HTTPException(
            status_code=400,
            detail="Student ID must be the student's UUID (students.id), not a roll number.",
        )
    student = (sb.table("students").select("id, institute_id")
               .eq("id", student_uuid).limit(1).execute()).data
    if not student:
        raise HTTPException(status_code=404, detail="No student found with that ID.")

    # Prefer the student's institute; fall back to the one the teacher sent. Empty
    # strings must become NULL — "" is not valid for a UUID column.
    institute_uuid = _as_uuid(student[0].get("institute_id")) or _as_uuid(req.institute_id)

    state = {
        "student_id": student_uuid,
        "institute_id": institute_uuid or "",
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

    # Auto-publish: the generated (and AI self-reviewed) test goes straight to the
    # student as "ready" — no separate teacher approval step.
    row = sb.table("tests").insert({
        "student_id": student_uuid,
        "institute_id": institute_uuid,
        "subject": req.subject,
        "questions": state.get("test_questions") or [],
        "status": "ready",
        "teacher_approved": True,
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
    background.add_task(_award_activity, student_id, "test")
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
            "student_name": student.get("name"),
            "summary": _week_summary(sb, student["id"]),
            "latest_report": latest[0]["report_text"] if latest else None,
        })

    first = children[0]
    return {**first, "children": children}


# ── Admin ─────────────────────────────────────────────────────────────────────
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
        la = s.get("last_active")
        if not la:
            return False
        try:
            return datetime.fromisoformat(str(la).replace("Z", "+00:00")) >= week_ago
        except Exception:
            return False

    active = sum(1 for s in students if _active(s))

    aq = sb.table("alerts").select("id", count="exact").eq("is_read", False)
    if iid:
        aq = aq.eq("institute_id", iid)
    at_risk = aq.execute().count or 0

    tq = sb.table("tests").select("id", count="exact").gte("created_at", week_ago.isoformat())
    if iid:
        tq = tq.eq("institute_id", iid)
    tests_week = tq.execute().count or 0

    renewal_pct = round((active / total) * 100, 1) if total else 0.0

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
        "renewal_pct": renewal_pct,
        "engagement": [],  # wire up a weekly rollup table later
        "revenue_signals": [
            {"label": "Total enrolled", "value": total},
            {"label": "Engaged (7d)", "value": active},
            {"label": "Predicted renewals", "value": round(total * renewal_pct / 100)},
        ],
        "counts": {
            "students": len(accounts["student"]),
            "teachers": len(accounts["teacher"]),
            "parents": len(accounts["parent"]),
            "admins": len(accounts["admin"]),
        },
        "students": students,
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
        row = (sb.table("students").select("xp_points, streak_days, last_active")
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
    except Exception as e:
        print(f"[gamify] award failed for {student_id}: {e}")


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
