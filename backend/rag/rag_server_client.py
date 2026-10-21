"""Connector from the SmartCoaching backend to the standalone RAG_SERVER.

RAG_SERVER (https://github.com/SanjayRawat0570/RAG_SERVER) is used as-is, over
HTTP. Nothing in it is changed. Each coaching institute is one RAG_SERVER
tenant, authenticated with a tenant-scoped API key.

Endpoints used (all under /api/v1 on RAG_SERVER):
    POST /search/hybrid                  dense + BM25 retrieval, RRF fused
    POST /rag/stream/ask                 full grounded answer as SSE (with citations)
    POST /documents/upload               ingest a PDF / DOCX / image / ...
    GET  /documents/executions/{id}      ingestion progress

RAG_SERVER is the ONLY retrieval system of SmartCoaching. Every function fails
soft: if RAG_SERVER is not configured or not reachable, it logs a warning and
returns an empty result (or an "error" event), and the caller decides how to
degrade (friendly error for doubts, no-context generation for agents).

Environment:
    RAG_SERVER_URL       e.g. https://your-rag-server.up.railway.app
    RAG_SERVER_API_KEY   sk-... key scoped to the tenant (role "member" to upload)
    RAG_SERVER_TENANT    tenant slug for this institute (default "smartcoaching")
    RAG_SERVER_TIMEOUT   seconds per request (default 30)

Every public function also takes ``tenant=`` and ``api_key=`` so each
institute can use its own tenant and key (looked up from the database);
the env values are the default for a single-institute setup.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator

import httpx

log = logging.getLogger(__name__)

STORE = "kb"  # the store RAG_SERVER's upload pipeline indexes into


# ── Config ─────────────────────────────────────────────────────────────────────

def _url() -> str:
    return os.getenv("RAG_SERVER_URL", "").rstrip("/")


def _headers(api_key: str | None = None) -> dict[str, str]:
    return {"X-API-Key": api_key or os.getenv("RAG_SERVER_API_KEY", "")}


def _tenant(tenant: str | None) -> str:
    return tenant or os.getenv("RAG_SERVER_TENANT", "smartcoaching")


def _timeout() -> float:
    return float(os.getenv("RAG_SERVER_TIMEOUT", "30"))


# ── Shared HTTP clients (keep-alive) ───────────────────────────────────────────
# One sync client per process and one async client per event loop, created on
# first use, so repeated calls reuse open connections instead of paying a new
# TLS handshake each time. Timeouts are passed per request. aclose() runs in the
# FastAPI lifespan shutdown.

_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_sync_client: httpx.Client | None = None
_async_client: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None
_client_lock = threading.Lock()


def _client() -> httpx.Client:
    global _sync_client
    with _client_lock:
        if _sync_client is None or _sync_client.is_closed:
            _sync_client = httpx.Client(limits=_LIMITS)
        return _sync_client


def _aclient() -> httpx.AsyncClient:
    """The async client of the running event loop (one client can't span loops)."""
    global _async_client
    loop = asyncio.get_running_loop()
    if _async_client is None or _async_client[0] is not loop or _async_client[1].is_closed:
        _async_client = (loop, httpx.AsyncClient(limits=_LIMITS))
    return _async_client[1]


async def aclose() -> None:
    """Close the shared clients (FastAPI lifespan shutdown)."""
    global _sync_client, _async_client
    if _async_client is not None:
        try:
            await _async_client[1].aclose()
        except Exception:  # noqa: BLE001 - belongs to an already closed loop
            pass
    if _sync_client is not None:
        _sync_client.close()
    _sync_client = _async_client = None


def reset_clients() -> None:
    """Forget the shared clients without closing them (tests swap httpx out)."""
    global _sync_client, _async_client
    _sync_client = _async_client = None


def is_enabled(api_key: str | None = None) -> bool:
    """True when RAG_SERVER_URL and an API key (argument or env) are both set."""
    return bool(_url() and (api_key or os.getenv("RAG_SERVER_API_KEY")))


# ── Result shaping ─────────────────────────────────────────────────────────────

def _to_chunk(hit: dict[str, Any]) -> dict[str, Any]:
    meta = hit.get("metadata") or {}
    return {
        "id":     hit.get("id"),
        "text":   str(meta.get("text", "")),
        "source": meta.get("source") or meta.get("title") or "document",
        "page":   meta.get("page"),
        "score":  hit.get("rrf_score", hit.get("score")),
    }


def format_context(chunks: list[dict[str, Any]], max_chars: int = 6000) -> str:
    """Numbered context block for an LLM prompt: ``[1] (source, p. 4) text``."""
    parts: list[str] = []
    used = 0
    for i, c in enumerate(chunks, 1):
        where = c["source"] + (f", p. {c['page']}" if c.get("page") else "")
        block = f"[{i}] ({where})\n{c['text'].strip()}"
        if used + len(block) > max_chars and parts:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def citations_of(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact source list to store with a test question, flashcard or grade."""
    return [{"source": c["source"], "page": c.get("page")} for c in chunks]


def _search_body(query: str, top_k: int, tenant: str | None) -> dict[str, Any]:
    return {
        "query":       query,
        "store":       STORE,
        "namespace":   _tenant(tenant),
        "top_k":       top_k,
        "auto_weight": True,   # RAG_SERVER picks keyword/semantic weighting per query
    }


# ── Retrieval ──────────────────────────────────────────────────────────────────

async def search(query: str, *, top_k: int = 5, tenant: str | None = None,
           api_key: str | None = None) -> list[dict[str, Any]]:
    """Hybrid retrieval. Returns ``[{id, text, source, page, score}]`` or ``[]``."""
    if not is_enabled(api_key) or not query.strip():
        return []
    try:
        r = await _aclient().post(f"{_url()}/api/v1/search/hybrid", timeout=_timeout(),
                                  json=_search_body(query, top_k, tenant), headers=_headers(api_key))
        r.raise_for_status()
        return [_to_chunk(h) for h in r.json().get("hits", []) if h.get("metadata")]
    except Exception as exc:  # noqa: BLE001 - fail soft
        log.warning("RAG_SERVER search failed (%s)", exc)
        return []


def search_sync(query: str, *, top_k: int = 5, tenant: str | None = None,
           api_key: str | None = None) -> list[dict[str, Any]]:
    """Same as :func:`search`, for synchronous LangGraph nodes."""
    if not is_enabled(api_key) or not query.strip():
        return []
    try:
        r = _client().post(f"{_url()}/api/v1/search/hybrid", timeout=_timeout(),
                           json=_search_body(query, top_k, tenant), headers=_headers(api_key))
        r.raise_for_status()
        return [_to_chunk(h) for h in r.json().get("hits", []) if h.get("metadata")]
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER search failed (%s)", exc)
        return []


def _merge_unique(results: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    seen: set[Any] = set()
    merged: list[dict[str, Any]] = []
    for chunks in results:
        for c in chunks:
            if c["id"] not in seen:
                seen.add(c["id"])
                merged.append(c)
    return merged


async def search_many(queries: list[str], *, top_k: int = 3,
                      tenant: str | None = None, api_key: str | None = None) -> list[dict[str, Any]]:
    """Search several queries in parallel (e.g. one per weak concept), de-duplicated."""
    results = await asyncio.gather(*(search(q, top_k=top_k, tenant=tenant, api_key=api_key) for q in queries))
    return _merge_unique(list(results))


def search_many_sync(queries: list[str], *, top_k: int = 3, tenant: str | None = None,
                     api_key: str | None = None, max_workers: int = 6) -> list[dict[str, Any]]:
    """Same as :func:`search_many`, for synchronous agents: one thread per query."""
    if not queries:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(queries))) as pool:
        results = list(pool.map(
            lambda q: search_sync(q, top_k=top_k, tenant=tenant, api_key=api_key), queries))
    return _merge_unique(results)


# ── Grounded answers (streamed) ────────────────────────────────────────────────

async def ask_stream(question: str, *, tenant: str | None = None,
                     api_key: str | None = None, conversation_id: str | None = None,
                     new_conversation: bool = False, mode: str = "fast") -> AsyncIterator[dict[str, Any]]:
    """Yield RAG_SERVER's SSE events as dicts.

    Event types: memory · step · progress · token · sources · complete · error.
    ``token`` events carry ``token``; ``complete`` carries ``answer``,
    ``citations`` (with source/page), ``confidence`` and ``answerable``.
    """
    if not is_enabled(api_key):
        yield {"event": "error", "detail": "RAG_SERVER is not configured"}
        return
    body: dict[str, Any] = {"question": question, "tenant": _tenant(tenant), "mode": mode,
                            "new_conversation": new_conversation}
    if conversation_id:
        body["conversation_id"] = conversation_id
    try:
        async with _aclient().stream("POST", f"{_url()}/api/v1/rag/stream/ask",
                                     timeout=httpx.Timeout(_timeout(), read=120),
                                     json=body, headers=_headers(api_key)) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    try:
                        yield json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER ask failed (%s)", exc)
        yield {"event": "error", "detail": str(exc)}


async def ask(question: str, *, tenant: str | None = None,
              api_key: str | None = None) -> dict[str, Any] | None:
    """Grounded answer in one call: the ``complete`` event, or ``None`` on failure."""
    async for ev in ask_stream(question, tenant=tenant, api_key=api_key):
        if ev.get("event") == "complete":
            return ev
        if ev.get("event") == "error":
            return None
    return None


# ── Ingestion ──────────────────────────────────────────────────────────────────

async def upload_document(content: bytes, filename: str, *, tenant: str | None = None,
                          api_key: str | None = None, wait: bool = True, poll_seconds: float = 2.0,
                          max_wait: float = 300.0) -> dict[str, Any]:
    """Send a file to RAG_SERVER for chunking + indexing.

    Returns ``{"execution_id", "status", "message", "chunks_indexed"}``.
    With ``wait=False`` it returns right after the upload is accepted.
    """
    if not is_enabled(api_key):
        return {"status": "failed", "message": "RAG_SERVER is not configured"}
    try:
        client = _aclient()
        r = await client.post(f"{_url()}/api/v1/documents/upload", timeout=_timeout(),
                              files={"file": (filename, content)},
                              data={"tenant": _tenant(tenant)}, headers=_headers(api_key))
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            return {"status": "failed", "message": str(detail)}
        exec_id = r.json()["execution_id"]
        if not wait:
            return {"execution_id": exec_id, "status": "running"}
        return await _wait_for(client, exec_id, poll_seconds, max_wait, api_key)
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER upload failed (%s)", exc)
        return {"status": "failed", "message": f"RAG server unreachable: {exc}"}


async def upload_status(execution_id: str, *, api_key: str | None = None) -> dict[str, Any]:
    r = await _aclient().get(f"{_url()}/api/v1/documents/executions/{execution_id}",
                             timeout=_timeout(), headers=_headers(api_key))
    r.raise_for_status()
    return r.json()


async def _wait_for(client: httpx.AsyncClient, exec_id: str, poll_seconds: float,
                    max_wait: float, api_key: str | None = None) -> dict[str, Any]:
    waited = 0.0
    while waited < max_wait:
        r = await client.get(f"{_url()}/api/v1/documents/executions/{exec_id}",
                             timeout=_timeout(), headers=_headers(api_key))
        r.raise_for_status()
        state = r.json()
        if state.get("status") in ("completed", "failed"):
            return {"execution_id": exec_id, "status": state["status"],
                    "message": state.get("message"), "chunks_indexed": state.get("chunks_indexed")}
        await asyncio.sleep(poll_seconds)
        waited += poll_seconds
    return {"execution_id": exec_id, "status": "running",
            "message": "Still indexing; check upload_status later."}


# ── Feedback & usage ───────────────────────────────────────────────────────────

async def send_feedback(query_id: str, rating: int, *, query: str = "", answer: str = "",
                        sources: list[str] | None = None, comment: str = "",
                        api_key: str | None = None) -> bool:
    """Forward a student's rating (1-5; thumbs up = 5, down = 1) to RAG_SERVER."""
    if not is_enabled(api_key):
        return False
    body = {"query_id": query_id, "rating": max(1, min(5, int(rating))), "comment": comment,
            "query": query, "answer": answer, "sources": sources or []}
    try:
        r = await _aclient().post(f"{_url()}/api/v1/feedback", timeout=_timeout(),
                                  json=body, headers=_headers(api_key))
        return r.status_code < 400
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER feedback failed (%s)", exc)
        return False


async def tenant_usage(*, tenant: str | None = None,
                       api_key: str | None = None) -> dict[str, Any] | None:
    """Tokens, cost and cache hits for an institute's tenant, or ``None``."""
    if not is_enabled(api_key):
        return None
    try:
        r = await _aclient().get(f"{_url()}/api/v1/tenants/{_tenant(tenant)}/usage",
                                 timeout=_timeout(), headers=_headers(api_key))
        return r.json() if r.status_code < 400 else None
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER usage failed (%s)", exc)
        return None


async def health() -> bool:
    if not _url():
        return False
    try:
        return (await _aclient().get(f"{_url()}/health", timeout=5)).status_code == 200
    except Exception:  # noqa: BLE001
        return False
