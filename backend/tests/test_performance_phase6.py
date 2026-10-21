"""Performance Phase 6: request ids, timing logs (no personal data), slow-request
warnings, request metrics, and the admin System health endpoint."""

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
import observability
from auth import supabase_auth
from auth.supabase_auth import get_current_user

INST = "99999999-9999-9999-9999-999999999999"


@pytest.fixture
def client(monkeypatch, fake_sb):
    monkeypatch.setattr(main, "get_supabase", lambda: fake_sb)
    observability.reset()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "smartcoaching.request"]


# ── request ids ───────────────────────────────────────────────────────────────
def test_every_response_carries_a_request_id(client, caplog):
    caplog.set_level(logging.INFO, logger="smartcoaching.request")
    r = client.get("/health")
    rid = r.headers["x-request-id"]
    assert len(rid) == 32
    assert f"id={rid}" in _lines(caplog)[-1]


def test_a_sane_incoming_request_id_is_kept_and_a_bad_one_replaced(client):
    assert client.get("/health", headers={"X-Request-ID": "trace-abc12345"}).headers["x-request-id"] == "trace-abc12345"
    bad = client.get("/health", headers={"X-Request-ID": "x\r\nSet-Cookie: a=b"}).headers["x-request-id"]
    assert bad != "x\r\nSet-Cookie: a=b" and len(bad) == 32


# ── what a log line holds ─────────────────────────────────────────────────────
class _FakeAuth:
    def get_user(self, token):
        meta = {"role": "student", "institute_id": INST, "name": "Asha"}
        return SimpleNamespace(user=SimpleNamespace(id="auth-7", email="asha@example.com",
                                                    user_metadata=meta))


def test_log_line_has_method_route_status_ms_role_and_nothing_personal(client, fake_sb, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="smartcoaching.request")
    fake_sb.auth = _FakeAuth()
    monkeypatch.setattr(supabase_auth, "get_supabase", lambda: fake_sb)
    fake_sb.results[("students", "select")] = [{"id": "s1", "institute_id": INST}]
    client.get("/leaderboard?secret=asha@example.com", headers={"Authorization": "Bearer tok-123"})
    line = _lines(caplog)[-1]
    for part in ("method=GET", "path=/leaderboard", "status=200", "ms=", "role=student"):
        assert part in line
    for leaked in ("asha", "example.com", "auth-7", "tok-123", "secret"):
        assert leaked not in line


def test_route_templates_are_logged_not_ids(client, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="smartcoaching.request")
    import jobs
    monkeypatch.setattr(jobs, "get", lambda job_id, owner: None)
    main.app.dependency_overrides[get_current_user] = lambda: {"id": "a", "role": "teacher"}
    client.get("/jobs/0f1e2d3c-1111-2222-3333-444455556666")
    assert "path=/jobs/{job_id}" in _lines(caplog)[-1]


def test_failures_are_logged_with_their_status(client, caplog):
    caplog.set_level(logging.INFO, logger="smartcoaching.request")
    client.get("/progress")  # no token
    assert "status=403" in _lines(caplog)[-1] or "status=401" in _lines(caplog)[-1]


# ── slow requests ─────────────────────────────────────────────────────────────
def test_slow_requests_are_warnings_naming_the_endpoint(client, caplog, monkeypatch):
    caplog.set_level(logging.INFO, logger="smartcoaching.request")
    monkeypatch.setenv("SLOW_REQUEST_MS", "-1")
    client.get("/health")
    rec = [r for r in caplog.records if r.name == "smartcoaching.request"][-1]
    assert rec.levelno == logging.WARNING and "SLOW /health" in rec.getMessage()


def test_a_stream_is_judged_by_its_first_byte(client, caplog, monkeypatch):
    from agents import doubt_agent
    import asyncio

    async def slow_answer(**_):
        await asyncio.sleep(0.3)  # long stream, but the first [STATUS] goes out at once
        yield "error", "busy"

    caplog.set_level(logging.INFO, logger="smartcoaching.request")
    monkeypatch.setenv("SLOW_REQUEST_MS", "200")
    monkeypatch.setattr(doubt_agent, "run_doubt", slow_answer)
    monkeypatch.setattr(main, "_resolve_student_id", lambda u: "s1")
    monkeypatch.setattr(main, "_caller_institute_id", lambda u: INST)
    main.app.dependency_overrides[get_current_user] = lambda: {"id": "a", "role": "student"}
    client.post("/doubt/stream", json={"question": "q"})
    rec = [r for r in caplog.records if r.name == "smartcoaching.request"][-1]
    assert rec.levelno == logging.INFO and "ttfb_ms=" in rec.getMessage()


# ── metrics + System health ───────────────────────────────────────────────────
def test_summary_counts_errors_slow_and_percentiles(monkeypatch):
    observability.reset()
    now = observability.time.monotonic()
    for i, (status, ms, slow) in enumerate([(200, 10, False), (200, 30, False), (500, 50, False),
                                             (200, 3000, True)]):
        observability._metrics.append((now, f"/r{i % 2}", status, ms, slow))
    observability._metrics.append((now - 7200, "/old", 500, 10, False))  # outside the hour
    s = observability.summary()
    assert s["requests"] == 4 and s["errors_5xx"] == 1 and s["slow"] == 1
    assert s["p50_ms"] == 50 and s["p95_ms"] == 3000
    assert s["slowest_routes"][0]["route"] == "/r1"


def test_system_health_is_admin_only(client):
    main.app.dependency_overrides[get_current_user] = lambda: {"id": "a", "role": "teacher"}
    assert client.get("/admin/system-health").status_code == 403


def test_system_health_reports_checks_jobs_and_requests(client, monkeypatch):
    from rag import rag_server_client
    from scheduler import jobs as sched

    async def up():
        return True
    monkeypatch.setattr(rag_server_client, "health", up)
    monkeypatch.setitem(main._warm, "embedder", True)
    monkeypatch.setattr(sched, "LAST_RUNS", {"at_risk_nightly": {
        "started_at": "2026-10-22T17:30:00+00:00", "duration_s": 4.2, "status": "ok"}})
    main.app.dependency_overrides[get_current_user] = lambda: {"id": "a", "role": "admin"}
    client.get("/health")
    body = client.get("/admin/system-health").json()
    assert body["ready"] is True
    assert body["checks"] == {"supabase": True, "rag_server": True, "embedder_loaded": True}
    assert body["scheduler"]["jobs"] == [{"id": "at_risk_nightly", "next_run": None, "last_run": {
        "started_at": "2026-10-22T17:30:00+00:00", "duration_s": 4.2, "status": "ok"}}]
    assert body["requests"]["requests"] >= 1
    assert "uptime_s" in body


# ── shared Supabase client: HTTP/1.1 where the library allows choosing ────────
def test_shared_supabase_client_uses_http1_when_configurable():
    import dataclasses
    from supabase import ClientOptions
    opts = supabase_auth._http1_options()
    if "httpx_client" in {f.name for f in dataclasses.fields(ClientOptions)}:
        transport = opts.httpx_client._transport
        assert getattr(transport._pool, "_http2", False) is False
    else:  # pinned supabase 2.5: already HTTP/1.1, nothing to pass
        assert opts is None


# ── load test never touches the live RAG_SERVER ───────────────────────────────
@pytest.mark.parametrize("url", ["https://rag.example.com", "", "https://my-rag.up.railway.app"])
def test_loadtest_refuses_doubts_against_a_remote_rag_server(monkeypatch, url):
    from scripts import loadtest
    monkeypatch.setenv("RAG_SERVER_URL", url)
    with pytest.raises(SystemExit):
        loadtest._check_doubts_allowed()


def test_loadtest_allows_doubts_against_a_local_copy(monkeypatch):
    from scripts import loadtest
    monkeypatch.setenv("RAG_SERVER_URL", "http://localhost:8100")
    loadtest._check_doubts_allowed()
