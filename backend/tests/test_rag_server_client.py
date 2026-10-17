"""rag/rag_server_client.py against a mocked RAG_SERVER (no network)."""

import asyncio
import json

import httpx

from rag import rag_server_client as rsc


def _run(coro):
    return asyncio.run(coro)


async def _collect(agen):
    return [ev async for ev in agen]


HITS = {"hits": [
    {"id": "c1", "rrf_score": 0.9, "score": 0.1,
     "metadata": {"text": "F = ma", "source": "Physics_Notes.pdf", "page": 12}},
    {"id": "c2", "score": 0.5, "metadata": {"text": "Newton's third law", "title": "NCERT Ch 5"}},
    {"id": "c3", "score": 0.4},  # no metadata -> dropped
]}


def _search_handler(request):
    assert request.url.path == "/api/v1/search/hybrid"
    return httpx.Response(200, json=HITS)


# ── Disabled ──────────────────────────────────────────────────────────────────

def test_disabled_without_config(monkeypatch, mock_http):
    monkeypatch.delenv("RAG_SERVER_URL")
    calls = mock_http(_search_handler)
    assert rsc.is_enabled() is False
    assert _run(rsc.search("newton")) == []
    assert rsc.search_sync("newton") == []
    assert rsc.search_many_sync(["a", "b"]) == []
    assert _run(_collect(rsc.ask_stream("newton")))[0]["event"] == "error"
    assert _run(rsc.upload_document(b"x", "a.pdf"))["status"] == "failed"
    assert _run(rsc.send_feedback("q1", 5)) is False
    assert _run(rsc.tenant_usage()) is None
    assert _run(rsc.health()) is False
    assert calls == []  # nothing was sent anywhere


def test_disabled_without_key(monkeypatch, mock_http):
    monkeypatch.delenv("RAG_SERVER_API_KEY")
    calls = mock_http(_search_handler)
    assert rsc.is_enabled() is False
    assert rsc.search_sync("newton") == []
    assert rsc.is_enabled("sk-institute") is True  # an institute key enables it
    assert calls == []


def test_blank_query_is_not_sent(mock_http):
    calls = mock_http(_search_handler)
    assert _run(rsc.search("   ")) == []
    assert calls == []


# ── Search ────────────────────────────────────────────────────────────────────

def test_search_maps_hits_and_sends_tenant_and_key(mock_http):
    calls = mock_http(_search_handler)
    chunks = _run(rsc.search("newton", top_k=4, tenant="inst-a", api_key="sk-a"))

    assert chunks == [
        {"id": "c1", "text": "F = ma", "source": "Physics_Notes.pdf", "page": 12, "score": 0.9},
        {"id": "c2", "text": "Newton's third law", "source": "NCERT Ch 5", "page": None, "score": 0.5},
    ]
    req = calls[0]
    assert req.headers["X-API-Key"] == "sk-a"
    assert json.loads(req.content) == {"query": "newton", "store": "kb", "namespace": "inst-a",
                                       "top_k": 4, "auto_weight": True}


def test_search_uses_env_defaults(mock_http):
    calls = mock_http(_search_handler)
    assert len(rsc.search_sync("newton")) == 2
    assert calls[0].headers["X-API-Key"] == "sk-env"
    assert json.loads(calls[0].content)["namespace"] == "inst-env"


def test_search_403_returns_empty(mock_http):
    mock_http(lambda r: httpx.Response(403, json={"detail": "tenant mismatch"}))
    assert _run(rsc.search("newton", tenant="inst-b")) == []
    assert rsc.search_sync("newton", tenant="inst-b") == []


def test_search_connection_error_returns_empty(mock_http):
    def down(request):
        raise httpx.ConnectError("connection refused", request=request)
    mock_http(down)
    assert _run(rsc.search("newton")) == []
    assert rsc.search_sync("newton") == []
    assert rsc.search_many_sync(["a", "b"]) == []


def test_search_many_dedupes(mock_http):
    calls = mock_http(_search_handler)
    merged = _run(rsc.search_many(["newton", "force", "mass"]))
    assert [c["id"] for c in merged] == ["c1", "c2"]
    assert len(calls) == 3


def test_search_many_sync_dedupes_and_keeps_query_order(mock_http):
    def per_query(request):
        q = json.loads(request.content)["query"]
        return httpx.Response(200, json={"hits": [
            {"id": q, "metadata": {"text": q, "source": "s"}},
            {"id": "shared", "metadata": {"text": "shared", "source": "s"}},
        ]})
    calls = mock_http(per_query)
    merged = rsc.search_many_sync(["a", "b", "c"], top_k=2, tenant="inst-a", api_key="sk-a")
    assert [c["id"] for c in merged] == ["a", "shared", "b", "c"]
    assert len(calls) == 3
    assert all(json.loads(r.content)["top_k"] == 2 for r in calls)
    assert rsc.search_many_sync([]) == []


# ── Prompt helpers ────────────────────────────────────────────────────────────

def test_format_context_and_citations():
    chunks = [{"id": 1, "text": " F = ma ", "source": "Physics.pdf", "page": 4},
              {"id": 2, "text": "x" * 100, "source": "Notes.md", "page": None}]
    assert rsc.format_context(chunks) == f"[1] (Physics.pdf, p. 4)\nF = ma\n\n[2] (Notes.md)\n{'x' * 100}"
    assert rsc.format_context(chunks, max_chars=40) == "[1] (Physics.pdf, p. 4)\nF = ma"
    assert rsc.citations_of(chunks) == [{"source": "Physics.pdf", "page": 4},
                                        {"source": "Notes.md", "page": None}]


# ── Streamed answers ──────────────────────────────────────────────────────────

SSE_BODY = "\n".join([
    "event: memory", 'data: {"event": "memory", "conversation_id": "conv-1"}', "",
    "event: step", 'data: {"event": "step", "step": "retrieve"}', "",
    ": keep-alive comment", "",
    "data: not json", "",
    'data: {"event": "token", "token": "F = "}', "",
    'data:{"event": "token", "token": "ma"}', "",
    'data: {"event": "complete", "answer": "F = ma", "confidence": "high", "answerable": true,'
    ' "citations": [{"marker": 1, "source": "Physics_Notes.pdf", "page": 12}]}', "",
])


def test_ask_stream_parses_data_lines(mock_http):
    calls = mock_http(lambda r: httpx.Response(200, text=SSE_BODY,
                                               headers={"content-type": "text/event-stream"}))
    events = _run(_collect(rsc.ask_stream("what is F?", tenant="inst-a", api_key="sk-a",
                                          conversation_id="conv-1")))

    assert [e["event"] for e in events] == ["memory", "step", "token", "token", "complete"]
    assert "".join(e["token"] for e in events if e["event"] == "token") == "F = ma"
    assert events[-1]["citations"][0]["page"] == 12
    body = json.loads(calls[0].content)
    assert calls[0].url.path == "/api/v1/rag/stream/ask"
    assert body == {"question": "what is F?", "tenant": "inst-a", "mode": "fast",
                    "new_conversation": False, "conversation_id": "conv-1"}


def test_ask_stream_http_error_yields_error_event(mock_http):
    mock_http(lambda r: httpx.Response(403, json={"detail": "forbidden"}))
    events = _run(_collect(rsc.ask_stream("q")))
    assert len(events) == 1 and events[0]["event"] == "error"


def test_ask_returns_complete_or_none(mock_http):
    mock_http(lambda r: httpx.Response(200, text=SSE_BODY))
    assert _run(rsc.ask("q"))["answer"] == "F = ma"

    def down(request):
        raise httpx.ConnectError("down", request=request)
    mock_http(down)
    assert _run(rsc.ask("q")) is None


# ── Ingestion ─────────────────────────────────────────────────────────────────

def test_upload_document_4xx_returns_failed(mock_http):
    mock_http(lambda r: httpx.Response(413, json={"detail": "File too large"}))
    out = _run(rsc.upload_document(b"%PDF", "notes.pdf"))
    assert out == {"status": "failed", "message": "File too large"}


def test_upload_document_4xx_non_json_body(mock_http):
    mock_http(lambda r: httpx.Response(400, text="bad request"))
    assert _run(rsc.upload_document(b"%PDF", "notes.pdf"))["message"] == "bad request"


def test_upload_document_unreachable_returns_failed(mock_http):
    def down(request):
        raise httpx.ConnectError("connection refused", request=request)
    mock_http(down)
    out = _run(rsc.upload_document(b"%PDF", "notes.pdf"))
    assert out["status"] == "failed"
    assert out["message"].startswith("RAG server unreachable")


def test_upload_document_no_wait(mock_http):
    calls = mock_http(lambda r: httpx.Response(200, json={"execution_id": "ex-1"}))
    out = _run(rsc.upload_document(b"%PDF", "notes.pdf", tenant="inst-a", api_key="sk-a", wait=False))
    assert out == {"execution_id": "ex-1", "status": "running"}
    req = calls[0]
    assert req.url.path == "/api/v1/documents/upload"
    assert req.headers["X-API-Key"] == "sk-a"
    assert b'name="tenant"' in req.content and b"inst-a" in req.content
    assert b'filename="notes.pdf"' in req.content


def test_upload_document_waits_until_completed(mock_http):
    states = iter([{"status": "running", "progress": 40},
                   {"status": "completed", "message": "ok", "chunks_indexed": 17}])

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json={"execution_id": "ex-1"})
        assert request.url.path == "/api/v1/documents/executions/ex-1"
        return httpx.Response(200, json=next(states))

    mock_http(handler)
    out = _run(rsc.upload_document(b"%PDF", "notes.pdf", poll_seconds=0))
    assert out == {"execution_id": "ex-1", "status": "completed", "message": "ok",
                   "chunks_indexed": 17}


# ── Feedback, usage, health ───────────────────────────────────────────────────

def test_send_feedback_clamps_rating(mock_http):
    calls = mock_http(lambda r: httpx.Response(200, json={"ok": True}))
    assert _run(rsc.send_feedback("q1", 9, query="q", answer="a", sources=["s"])) is True
    assert json.loads(calls[0].content)["rating"] == 5


def test_tenant_usage(mock_http):
    calls = mock_http(lambda r: httpx.Response(200, json={"total_queries": 3, "cache_hit_rate": 0.5}))
    assert _run(rsc.tenant_usage(tenant="inst-a"))["total_queries"] == 3
    assert calls[0].url.path == "/api/v1/tenants/inst-a/usage"

    mock_http(lambda r: httpx.Response(403))
    assert _run(rsc.tenant_usage(tenant="inst-b")) is None


def test_health(mock_http):
    calls = mock_http(lambda r: httpx.Response(200, json={"status": "ok"}))
    assert _run(rsc.health()) is True
    assert calls[0].url.path == "/health"

    def down(request):
        raise httpx.ConnectError("down", request=request)
    mock_http(down)
    assert _run(rsc.health()) is False
