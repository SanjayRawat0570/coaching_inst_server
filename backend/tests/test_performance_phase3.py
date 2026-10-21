"""Performance Phase 3: background jobs, parallel LLM work, short-task model use,
per-user rate limits, and the doubt stream's first byte."""

import threading
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import jobs
import main
import ratelimit
from agents import answer_evaluator, progress_tracker
from auth.supabase_auth import get_current_user
from concurrency import parallel_map
from graph import knowledge_graph
from graph import llm as llm_mod

INST = "99999999-9999-9999-9999-999999999999"


def _as(role, uid="auth-1"):
    return lambda: {"id": uid, "email": "u@x.com", "role": role, "institute_id": INST}


@pytest.fixture
def client(monkeypatch, fake_sb):
    monkeypatch.setattr(main, "get_supabase", lambda: fake_sb)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def memory_jobs(monkeypatch):
    """Jobs table missing (migration not run) -> the in-memory fallback is used."""
    class _NoTable:
        def table(self, name):
            raise RuntimeError('relation "jobs" does not exist')
    monkeypatch.setattr(jobs, "_db", lambda: _NoTable())
    jobs._memory.clear()
    yield
    jobs.shutdown()


def _wait(job_id, owner="auth-1", timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = jobs.get(job_id, owner)
        if j and j["status"] in ("done", "failed"):
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


# ── parallel_map ──────────────────────────────────────────────────────────────
def test_parallel_map_keeps_order_and_runs_concurrently():
    def slow(x):
        time.sleep(0.2)
        return x * 2
    t = time.perf_counter()
    assert parallel_map(slow, [1, 2, 3], limit=3) == [2, 4, 6]
    assert time.perf_counter() - t < 0.45


def test_parallel_map_respects_the_limit():
    running, peak, lock = [0], [0], threading.Lock()

    def track(_):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
    parallel_map(track, range(8), limit=2)
    assert peak[0] == 2


def test_parallel_map_raises_like_the_loop():
    def boom(x):
        raise ValueError(x)
    with pytest.raises(ValueError):
        parallel_map(boom, [1, 2])


# ── grading theory answers in parallel ────────────────────────────────────────
def test_theory_answers_are_graded_side_by_side(monkeypatch):
    calls = []

    def fake_grade(q, model, answer, marks, grounding=None, institute_id=None):
        if not (answer or "").strip():
            return {"marks_awarded": 0, "feedback": "No answer given."}
        calls.append(q)
        time.sleep(0.2)
        return {"marks_awarded": marks, "feedback": "ok"}

    monkeypatch.setattr(answer_evaluator, "grade_text_answer", fake_grade)
    monkeypatch.setattr(answer_evaluator, "_retrieve_for", lambda qs, iid: [[] for _ in qs])
    qs = [{"question": f"Q{i}", "type": "theory", "marks": 5, "concept": "c"} for i in range(3)]
    qs.append({"question": "Q3", "type": "theory", "marks": 5, "concept": "c"})
    t = time.perf_counter()
    out = answer_evaluator.score_test(qs, ["a", "b", "c", ""])
    assert time.perf_counter() - t < 0.45                    # 3 x 0.2 s ran together
    assert out["score"] == 15 and out["total_marks"] == 20
    assert [d["outcome"] for d in out["details"]] == ["graded", "graded", "graded", "skipped"]
    assert sorted(calls) == ["Q0", "Q1", "Q2"]                # no LLM for the empty answer


# ── knowledge graph: shared prerequisites aren't inserted twice ───────────────
def test_ensure_concept_is_serialised_per_name(fake_sb, monkeypatch):
    monkeypatch.setattr(knowledge_graph, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(knowledge_graph, "embed", lambda text: [0.0])
    inserted = []

    def select(q):
        time.sleep(0.05)  # widen the race window
        return [{"id": "c1"}] if inserted else []

    def insert(q):
        inserted.append(q.payload["name"])
        return [{"id": "c1"}]

    fake_sb.results[("concepts", "select")] = select
    fake_sb.results[("concepts", "insert")] = insert
    parallel_map(lambda _: knowledge_graph.ensure_concept("Atomic Structure"), range(4), limit=4)
    assert inserted == ["Atomic Structure"]


def test_weak_concepts_are_linked_side_by_side(fake_sb, monkeypatch):
    monkeypatch.setattr(progress_tracker, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(knowledge_graph, "ensure_concept", lambda *a, **k: "id")

    def slow_link(concept, subject=None):
        time.sleep(0.2)
        return [f"pre-{concept}"]

    monkeypatch.setattr(knowledge_graph, "link_prerequisites", slow_link)
    import memory.episodic as episodic
    monkeypatch.setattr(episodic, "record_milestone", lambda *a, **k: None)
    state = {"student_id": "s1", "subject": "Physics", "evaluation_result": {"per_concept": {
        "A": {"correct": 0, "total": 2}, "B": {"correct": 0, "total": 2},
        "C": {"correct": 0, "total": 2}, "D": {"correct": 2, "total": 2}}}}
    t = time.perf_counter()
    out = progress_tracker.progress_tracker_node(state)["weakness_update"]["concepts"]
    assert time.perf_counter() - t < 0.45
    assert {u["concept"]: u.get("prerequisites") for u in out} == {
        "A": ["pre-A"], "B": ["pre-B"], "C": ["pre-C"], "D": None}


# ── /test/submit: post-test agents side by side ───────────────────────────────
def _patch_submit(monkeypatch, fake_sb, delay=0.2):
    from agents import flashcard_agent, rank_predictor
    fake_sb.results[("tests", "select")] = [{"score": 8, "total_marks": 10, "status": "evaluated"}]
    monkeypatch.setattr(main, "_resolve_student_id", lambda u: "s1")
    monkeypatch.setattr(main, "_caller_institute_id", lambda u: INST)
    monkeypatch.setattr(main, "_audit", lambda *a, **k: None)
    awarded = []
    monkeypatch.setattr(main, "_award_activity", lambda sid, kind: awarded.append((sid, kind)))
    monkeypatch.setattr(answer_evaluator, "evaluator_node",
                        lambda s: {**s, "evaluation_result": {"score": 8}, "score": 8})

    def node(out):
        def run(state):
            time.sleep(delay)
            return out
        return run
    monkeypatch.setattr(rank_predictor, "rank_predictor_node", node({"air_rank": "AIR 5,000"}))
    monkeypatch.setattr(progress_tracker, "progress_tracker_node",
                        node({"weakness_update": {"concepts": []}}))
    monkeypatch.setattr(flashcard_agent, "flashcard_gen_node", node({}))
    return awarded


def test_submit_runs_post_test_agents_in_parallel(client, fake_sb, monkeypatch):
    awarded = _patch_submit(monkeypatch, fake_sb)
    main.app.dependency_overrides[get_current_user] = _as("student")
    t = time.perf_counter()
    body = client.post("/test/submit", json={"test_id": "t1", "answers": [0]}).json()
    assert time.perf_counter() - t < 0.5                     # max(0.2), not 3 x 0.2
    assert body["air_rank"] == "AIR 5,000" and body["score"] == 8
    assert body["weakness_update"] == {"concepts": []}
    assert awarded == [("s1", "test")]


def test_one_failing_post_test_agent_doesnt_hide_the_result(client, fake_sb, monkeypatch):
    _patch_submit(monkeypatch, fake_sb, delay=0)
    from agents import rank_predictor

    def broken(state):
        raise RuntimeError("cutoffs table missing")
    monkeypatch.setattr(rank_predictor, "rank_predictor_node", broken)
    main.app.dependency_overrides[get_current_user] = _as("student")
    body = client.post("/test/submit", json={"test_id": "t1", "answers": [0]}).json()
    assert body["score"] == 8 and body["air_rank"] is None


def test_submit_as_a_job(client, fake_sb, monkeypatch, memory_jobs):
    awarded = _patch_submit(monkeypatch, fake_sb, delay=0)
    main.app.dependency_overrides[get_current_user] = _as("student")
    r = client.post("/test/submit?job=1", json={"test_id": "t1", "answers": [0]}).json()
    assert r["status"] == "queued" and r["kind"] == "test_submit"
    done = _wait(r["job_id"])
    assert done["status"] == "done" and done["result"]["score"] == 8
    assert awarded == [("s1", "test")]


# ── jobs ──────────────────────────────────────────────────────────────────────
def test_generate_test_job_and_sync_mode(client, monkeypatch, memory_jobs):
    monkeypatch.setattr(main, "_generate_test", lambda req: {"test_id": "t9", "questions": []})
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    body = {"student_id": "a@x.com", "institute_id": INST}
    assert client.post("/test/generate", json=body).json()["test_id"] == "t9"   # old behaviour
    job = client.post("/test/generate?job=1", json=body).json()
    _wait(job["job_id"])
    r = client.get(f"/jobs/{job['job_id']}")
    assert r.status_code == 200 and r.json()["result"]["test_id"] == "t9"


def test_jobs_are_private_to_their_owner(client, memory_jobs):
    j = jobs.submit("test_generate", "auth-1", lambda: {"ok": True})
    _wait(j["job_id"])
    main.app.dependency_overrides[get_current_user] = _as("teacher", uid="auth-2")
    assert client.get(f"/jobs/{j['job_id']}").status_code == 404


def test_failed_jobs_carry_a_friendly_message(memory_jobs):
    def not_found():
        raise HTTPException(status_code=404, detail="No student found with email 'x'.")

    def crash():
        raise RuntimeError("psycopg2 OperationalError: secret dsn here")

    a = _wait(jobs.submit("test_generate", "auth-1", not_found)["job_id"])
    b = _wait(jobs.submit("test_generate", "auth-1", crash)["job_id"])
    assert a["status"] == "failed" and a["error"] == "No student found with email 'x'."
    assert b["status"] == "failed" and b["error"] == jobs.FRIENDLY_ERROR


def test_a_job_left_running_by_a_restart_reports_failed(memory_jobs):
    jobs._memory["old"] = {"id": "old", "kind": "test_generate", "status": "running",
                           "owner_id": "auth-1", "updated_at": "2020-01-01T00:00:00+00:00"}
    j = jobs.get("old", "auth-1")
    assert j["status"] == "failed" and "interrupted" in j["error"]


def test_jobs_use_the_table_when_it_exists(fake_sb, monkeypatch):
    monkeypatch.setattr(jobs, "_db", lambda: fake_sb)
    jobs._memory.clear()
    j = jobs.submit("answer_evaluate", "auth-1", lambda: {"marks": 3})
    deadline = time.time() + 5
    while time.time() < deadline and not any(
            c.payload.get("status") == "done" for c in fake_sb.ops("jobs", "upsert")):
        time.sleep(0.02)
    statuses = [c.payload["status"] for c in fake_sb.ops("jobs", "upsert")]
    assert statuses == ["queued", "running", "done"] and not jobs._memory
    jobs.shutdown()
    assert j["status"] == "queued"


def test_class_generation_runs_students_in_parallel(client, fake_sb, monkeypatch):
    from agents import test_generator
    fake_sb.results[("students", "select")] = [{"id": f"s{i}", "name": f"S{i}"} for i in range(3)]

    def slow(state, num_questions=10):
        time.sleep(0.2)
        return {**state, "test_questions": [{"q": 1}]}
    monkeypatch.setattr(test_generator, "test_generator_node", slow)
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    t = time.perf_counter()
    body = client.post("/teacher/tests/generate-class", json={"institute_id": INST}).json()
    assert time.perf_counter() - t < 0.5
    assert body["generated"] == 3 and [r["student"] for r in body["results"]] == ["S0", "S1", "S2"]


# ── rate limits ───────────────────────────────────────────────────────────────
def test_rate_limit_window(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DOUBT", "2/60")
    assert ratelimit.allow("doubt", "u") and ratelimit.allow("doubt", "u")
    assert not ratelimit.allow("doubt", "u")
    assert ratelimit.allow("doubt", "someone-else")
    now = ratelimit.time.monotonic()
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now + 61)
    assert ratelimit.allow("doubt", "u")


def test_doubt_stream_rate_limit_is_a_friendly_sse_error(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DOUBT", "0/60")
    main.app.dependency_overrides[get_current_user] = _as("student")
    r = client.post("/doubt/stream", json={"question": "q"})
    assert r.status_code == 200
    assert f"data: [ERROR]{ratelimit.message('doubt')}" in r.text and "[DONE]" in r.text


def test_test_generation_rate_limit_is_a_429(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TEST_GEN", "1/60")
    monkeypatch.setattr(main, "_generate_test", lambda req: {"test_id": "t"})
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    body = {"student_id": "a@x.com", "institute_id": INST}
    assert client.post("/test/generate", json=body).status_code == 200
    r = client.post("/test/generate", json=body)
    assert r.status_code == 429 and r.json()["detail"] == ratelimit.message("test_gen")


# ── doubt stream: first event at once ─────────────────────────────────────────
def test_doubt_stream_sends_a_status_first(client, monkeypatch):
    from agents import doubt_agent

    async def slow_run(**_):
        import asyncio
        await asyncio.sleep(0.3)
        yield "error", "busy"

    monkeypatch.setattr(doubt_agent, "run_doubt", slow_run)
    monkeypatch.setattr(main, "_resolve_student_id", lambda u: "s1")
    monkeypatch.setattr(main, "_caller_institute_id", lambda u: INST)
    main.app.dependency_overrides[get_current_user] = _as("student")
    with client.stream("POST", "/doubt/stream", json={"question": "q"}) as r:
        t = time.perf_counter()
        first = next(line for line in r.iter_lines() if line)
        assert first.startswith("data: [STATUS]") and time.perf_counter() - t < 0.25


# ── short tasks: fast model + answer cap ──────────────────────────────────────
def test_fast_reaches_the_provider_builder():
    seen = {}

    def builder(name, temperature, timeout, **extra):
        seen[name] = extra

        class _P:
            def invoke(self, prompt):
                return type("R", (), {"content": "ok"})()
        return _P()

    llm_mod.FailoverLLM(builder=builder, fast=True).invoke("label")
    assert seen == {"groq": {"fast": True}}


def test_groq_fast_model_env(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "big")
    assert llm_mod._groq_model(fast=True) == "big"          # default: same model
    monkeypatch.setenv("GROQ_FAST_MODEL", "small")
    assert llm_mod._groq_model(fast=True) == "small"
    assert llm_mod._groq_model(fast=False) == "big"
