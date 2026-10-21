"""Performance Phase 1: shared clients, LLM failover + circuit breaker, warm start
/ready, gzip (never on the SSE stream), cached student lookup, bounded lists."""

import asyncio
import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

import main
from auth import supabase_auth
from auth.supabase_auth import get_current_user
from graph import llm as llm_mod
from rag import rag_server_client

INST = "99999999-9999-9999-9999-999999999999"


def _as(role, uid="auth-1"):
    return lambda: {"id": uid, "email": "u@x.com", "role": role, "institute_id": INST}


@pytest.fixture
def client(monkeypatch, fake_sb):
    monkeypatch.setattr(main, "get_supabase", lambda: fake_sb)
    yield TestClient(main.app)  # not a context manager -> no lifespan / scheduler
    main.app.dependency_overrides.clear()


# ── one Supabase client per process ───────────────────────────────────────────
AGENT_MODULES = [
    "agents.answer_evaluator", "agents.at_risk_agent", "agents.doubt_agent",
    "agents.doubt_cluster_agent", "agents.flashcard_agent", "agents.inactivity_alert_agent",
    "agents.parent_report_agent", "agents.progress_tracker", "agents.rank_predictor",
    "agents.study_plan_agent", "agents.test_generator", "graph.knowledge_graph",
    "memory.episodic",
]


@pytest.mark.parametrize("name", AGENT_MODULES)
def test_agents_use_the_shared_supabase_client(monkeypatch, name):
    shared = object()
    monkeypatch.setattr(supabase_auth, "get_supabase", lambda: shared)
    mod = importlib.import_module(name)
    assert mod._supabase() is shared
    assert mod._supabase() is shared  # no new client per call


# ── LLM failover + circuit breaker ────────────────────────────────────────────
class _Reply:
    def __init__(self, content):
        self.content = content


class _Provider:
    def __init__(self, name, fail=False, chunks=("a", "b"), fail_after=None):
        self.name, self.fail, self.chunks, self.fail_after = name, fail, chunks, fail_after
        self.calls = 0

    def invoke(self, prompt, **_):
        self.calls += 1
        if self.fail:
            raise TimeoutError(f"{self.name} timed out")
        return _Reply(self.name)

    async def astream(self, prompt, **_):
        self.calls += 1
        if self.fail:
            raise TimeoutError(f"{self.name} timed out")
        for i, c in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise ConnectionError("dropped")
            yield _Reply(c)


def _llm(providers):
    by_name = {p.name: p for p in providers}
    return llm_mod.FailoverLLM(providers=tuple(by_name), builder=lambda n, t, to: by_name[n])


def test_invoke_fails_over_at_call_time():
    groq, gemini = _Provider("groq", fail=True), _Provider("gemini")
    assert _llm([groq, gemini]).invoke("hi").content == "gemini"
    assert groq.calls == 1 and gemini.calls == 1


def test_failed_provider_is_skipped_while_its_circuit_is_open():
    groq, gemini = _Provider("groq", fail=True), _Provider("gemini")
    _llm([groq, gemini]).invoke("hi")
    _llm([groq, gemini]).invoke("hi again")
    assert groq.calls == 1        # skipped on the second request
    assert gemini.calls == 2


def test_circuit_closes_after_cooldown(monkeypatch):
    groq, gemini = _Provider("groq", fail=True), _Provider("gemini")
    _llm([groq, gemini]).invoke("hi")
    groq.fail = False
    now = llm_mod.time.monotonic()
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now + llm_mod.COOLDOWN_SECONDS + 1)
    assert _llm([groq, gemini]).invoke("later").content == "groq"


def test_all_circuits_open_still_tries_everyone():
    groq, gemini = _Provider("groq", fail=True), _Provider("gemini", fail=True)
    with pytest.raises(TimeoutError):
        _llm([groq, gemini]).invoke("hi")
    gemini.fail = False
    assert _llm([groq, gemini]).invoke("hi").content == "gemini"


def test_cooling_provider_is_still_tried_last():
    # groq is cooling down after a 404; gemini now fails too -> groq gets a last try.
    groq, gemini = _Provider("groq", fail=True), _Provider("gemini")
    _llm([groq, gemini]).invoke("hi")
    groq.fail, gemini.fail = False, True
    assert _llm([groq, gemini]).invoke("hi").content == "groq"
    assert groq.calls == 2 and gemini.calls == 2


def test_unbuildable_provider_is_skipped():
    gemini = _Provider("gemini")

    def builder(name, t, to):
        if name == "groq":
            raise ValueError("GROQ_API_KEY missing")
        return gemini

    out = llm_mod.FailoverLLM(providers=("groq", "gemini"), builder=builder).invoke("hi")
    assert out.content == "gemini"


def test_astream_fails_over_before_the_first_chunk():
    groq, gemini = _Provider("groq", fail=True), _Provider("gemini", chunks=("x", "y"))

    async def collect():
        return [c.content async for c in _llm([groq, gemini]).astream("hi")]

    assert asyncio.run(collect()) == ["x", "y"]


def test_astream_broken_midway_raises_instead_of_mixing_answers():
    groq = _Provider("groq", chunks=("x", "y"), fail_after=1)
    gemini = _Provider("gemini")

    async def collect():
        return [c.content async for c in _llm([groq, gemini]).astream("hi")]

    with pytest.raises(ConnectionError):
        asyncio.run(collect())
    assert gemini.calls == 0


def test_get_llm_passes_a_timeout(monkeypatch):
    seen = {}

    def builder(name, temperature, timeout):
        seen[name] = timeout
        return _Provider(name)

    monkeypatch.setattr(llm_mod, "_build", builder)
    monkeypatch.setenv("LLM_TIMEOUT", "12")
    llm_mod.FailoverLLM(builder=llm_mod._build).invoke("hi")
    assert seen == {"groq": 12.0}


# ── RAG_SERVER connector reuses its HTTP clients ──────────────────────────────
def _count_clients(monkeypatch, handler):
    made = {"sync": 0, "async": 0}
    transport = httpx.MockTransport(handler)
    real_async, real_sync = httpx.AsyncClient, httpx.Client

    def make_async(*a, **kw):
        made["async"] += 1
        return real_async(*a, transport=transport, **kw)

    def make_sync(*a, **kw):
        made["sync"] += 1
        return real_sync(*a, transport=transport, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", make_async)
    monkeypatch.setattr(httpx, "Client", make_sync)
    return made


def _hits(request):
    return httpx.Response(200, json={"hits": [{"id": "c1", "metadata": {"text": "t", "source": "s"}}]})


def test_sync_search_reuses_one_client(monkeypatch):
    made = _count_clients(monkeypatch, _hits)
    for _ in range(3):
        assert rag_server_client.search_sync("q")
    assert made["sync"] == 1


def test_async_calls_reuse_one_client_per_loop(monkeypatch):
    made = _count_clients(monkeypatch, _hits)

    async def three():
        for _ in range(3):
            assert await rag_server_client.search("q")
        await rag_server_client.aclose()

    asyncio.run(three())
    assert made["async"] == 1
    asyncio.run(three())  # a new event loop gets its own client
    assert made["async"] == 2


def test_search_still_fails_soft(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("down")
    _count_clients(monkeypatch, boom)
    assert rag_server_client.search_sync("q") == []


# ── /ready and /health ────────────────────────────────────────────────────────
def test_health_is_instant_and_touches_nothing(client, fake_sb):
    assert client.get("/health").json() == {"status": "ok"}
    assert fake_sb.calls == []


def test_ready_reports_each_check(client, fake_sb, monkeypatch):
    async def up():
        return True
    monkeypatch.setattr(rag_server_client, "health", up)
    monkeypatch.setitem(main._warm, "embedder", False)
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json()["supabase"] is True and r.json()["rag_server"] is True
    monkeypatch.setitem(main._warm, "embedder", True)
    assert client.get("/ready").status_code == 200


def test_ready_is_503_when_supabase_is_down(client, fake_sb, monkeypatch):
    fake_sb.results[("institutes", "select")] = RuntimeError("db down")
    monkeypatch.setitem(main._warm, "embedder", True)
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["supabase"] is False


# ── gzip ──────────────────────────────────────────────────────────────────────
def test_large_json_is_gzipped(client, fake_sb):
    fake_sb.results[("students", "select")] = [
        {"id": f"s{i}", "name": f"Student {i}", "email": f"s{i}@x.com"} for i in range(200)]
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    r = client.get("/teacher/students", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert len(r.json()["students"]) == 200


def test_small_json_is_not_gzipped(client):
    r = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in r.headers


def test_doubt_stream_is_never_gzipped(client, monkeypatch):
    from agents import doubt_agent

    async def fake_run(**_):
        yield "token", "x" * 5000
        yield "error", "busy"

    monkeypatch.setattr(doubt_agent, "run_doubt", fake_run)
    monkeypatch.setattr(main, "_resolve_student_id", lambda u: "s1")
    monkeypatch.setattr(main, "_caller_institute_id", lambda u: INST)
    main.app.dependency_overrides[get_current_user] = _as("student")
    r = client.post("/doubt/stream", json={"question": "q"}, headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in r.headers
    assert "[DONE]" in r.text


# ── cached student lookup ─────────────────────────────────────────────────────
def test_student_row_is_cached_across_lookups(client, fake_sb):
    fake_sb.results[("students", "select")] = [{"id": "s1", "institute_id": INST}]
    user = {"id": "auth-9", "role": "student"}
    assert main._resolve_student_id(user) == "s1"
    assert main._caller_institute_id(user) == INST
    assert main._resolve_student_id(user) == "s1"
    assert len(fake_sb.ops("students", "select")) == 1


def test_missing_student_row_is_not_cached(client, fake_sb):
    fake_sb.results[("students", "select")] = []
    fake_sb.results[("students", "insert")] = [{"id": "new"}]
    user = {"id": "auth-10", "role": "student", "email": "n@x.com"}
    assert main._resolve_student_id(user) == "new"
    fake_sb.results[("students", "select")] = [{"id": "new", "institute_id": None}]
    assert main._resolve_student_id(user) == "new"
    assert len(fake_sb.ops("students", "insert")) == 1


# ── bounded lists ─────────────────────────────────────────────────────────────
def test_teacher_alerts_rejects_a_blank_institute(client):
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    assert client.get("/teacher/alerts?institute_id=").status_code == 400


def test_teacher_alerts_is_paginated(client, fake_sb):
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    assert client.get(f"/teacher/alerts?institute_id={INST}&limit=50&offset=100").status_code == 200
    (call,) = fake_sb.ops("alerts", "select")
    assert ("range", None, (100, 149)) in call.filters


def test_overview_leaves_out_content_gap_alerts(client, fake_sb):
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    assert client.get(f"/teacher/overview?institute_id={INST}").status_code == 200
    (call,) = fake_sb.ops("alerts", "select")
    assert ("or", None, "alert_type.is.null,alert_type.neq.content_gap") in call.filters
