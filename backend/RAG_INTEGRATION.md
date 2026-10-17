# SmartCoaching × RAG_SERVER — Full Integration Prompt

> **How to use:** open Claude Code inside your coaching_inst_server folder (the backend). Save this file there as `RAG_INTEGRATION.md` and say: *"Read RAG_INTEGRATION.md and do Phase 0."* Then go one phase at a time ("Do Phase 1", "Do Phase 2", …) and check each one before moving on. Phases 2–5 also touch the frontend (coaching_inst_ui); open that repo too when Claude reaches those steps.
>
> **Note (repo reality):** both live in one monorepo here — `backend/` and `frontend/`. See [Decisions after Phase 0](#decisions-after-phase-0) at the end; they override the text below where they differ.

## 0. Context — read this first

You are working on **SmartCoaching**, an AI coaching platform for JEE/NEET institutes. There are three repositories:

| Repo | What it is | Can you change it? |
|---|---|---|
| `SanjayRawat0570/coaching_inst_server` | FastAPI backend: LangGraph agents (doubt, test_generator, reviewer, answer_evaluator, progress, rank, flashcard, at_risk, …), Supabase (Postgres + Auth), its own old RAG (Qdrant, `rag/retriever.py`, `rag/ingest.py`, MiniLM embeddings, CrossEncoder, HyDE/CRAG/RAPTOR, Tavily web fallback), APScheduler. Deployed on Railway. | **Yes** — main work happens here |
| `SanjayRawat0570/coaching_inst_ui` | Next.js 14 + TypeScript frontend (Pages Router, Tailwind). `lib/api.ts` has `api()` and `streamDoubt()`. Pages: `student/doubt.tsx`, `teacher/dashboard.tsx`, `teacher/review.tsx`, `admin/analytics.tsx`, … | **Yes** — UI changes in Phases 2–5 |
| `SanjayRawat0570/RAG_SERVER` | My separate, already-hosted RAG service: multi-tenant, hybrid search (dense + BM25, RRF), semantic answer cache, citations with page numbers, "answerable"/confidence, conversation memory, agentic mode, ingestion of PDF/DOCX/PPTX/images, tenant-scoped API keys, feedback, usage/cost tracking. | **NO. Never modify it** — no code, no Railway settings, no env vars, no redeploys. It is live and used as-is, only over HTTP. |

### The goal

**RAG_SERVER becomes the one and only RAG of SmartCoaching.** Every place the coaching backend retrieves study content (doubts, tests, grading, flashcards, lecture transcripts, hot-topic clustering links) must call RAG_SERVER. The coaching backend's own RAG — Qdrant, `rag/retriever.py`, its ingestion, embeddings, rerankers, HyDE/CRAG/RAPTOR, Tavily web search — is **removed**, not kept as a fallback.

The coaching backend keeps owning everything that is not RAG: students, tests, weakness maps, memory, agents, LLM calls for generation/grading, photo-to-text (Gemini vision), scheduler, notifications.

```
Next.js UI ──REST/SSE──▶ coaching_inst_server ──HTTP (X-API-Key)──▶ RAG_SERVER (only RAG)
                          agents · Supabase · LLMs                    notes · NCERT · PYQs
```

### Hard rules (apply to every phase)

1. **Never change the hosted RAG_SERVER in any way**: no code, no commits, no Railway settings, env vars, volumes or redeploys. Treat it like a third-party API. If something seems to need a RAG_SERVER change, solve it inside the coaching backend, or stop and tell me. Everything must work with RAG_SERVER exactly as it is deployed today.
2. **RAG_SERVER is the only retrieval.** Do not keep Qdrant or any other retriever as a fallback. When RAG_SERVER is down or returns nothing, degrade gracefully as described in each phase (friendly message for doubts; agents continue without retrieved context). Never crash a request because RAG_SERVER failed.
3. **Never send a RAG_SERVER API key to the frontend or log it.** Keys live only in env vars or in Supabase rows readable by the service role.
4. **Keep the existing auth**: every new endpoint uses `get_current_user` / `require_role(...)` from `auth/supabase_auth.py`, and every query is scoped to the caller's `institute_id`.
5. **Follow the repo's existing style**, naming, and patterns. Read before you write. Don't break any existing API contract the frontend uses unless this prompt says to change both sides.
6. **Small, reviewable changes.** At the end of each phase: run the app, run tests, and give me a short summary of files changed + how to try it. Commit once per phase with a clear message.
7. If my description doesn't match the real code (a file or function has a different name), **trust the code**, adapt, and tell me what you changed.

### RAG_SERVER API reference (verified against its code)

Base path: `{RAG_SERVER_URL}/api/v1`. Server-to-server auth: header `X-API-Key: sk-…` (a key scoped to one tenant). A key for tenant A gets **403** on tenant B. Every institute = one tenant (slug, e.g. `inst-<short-id>`).

| Purpose | Call | Notes |
|---|---|---|
| Hybrid search | `POST /search/hybrid` body `{query, store:"kb", namespace:<tenant>, top_k, auto_weight:true}` | Returns `{hits:[{id, score/rrf_score, metadata:{text, source, title, page?…}, highlight}]}` |
| Grounded answer (SSE) | `POST /rag/stream/ask` body `{question, tenant, mode:"fast"\|"agentic", conversation_id?, new_conversation?}` | Lines `event: X` / `data: {json}`. Events: `memory` (has `conversation_id`), `step`, `progress`, `token` (`token` field), `sources`, `complete` (`answer`, `citations[{marker, source, page?, heading}]`, `confidence`, `answerable`), `error`. Semantic cache is automatic in fast mode. |
| Upload file | `POST /documents/upload` multipart `file`, form `tenant` | Returns `{execution_id}`. Allowed: pdf docx pptx xlsx txt md html json xml jpg jpeg png bmp tif tiff. Max 50 MB. Needs role member+. |
| Upload status | `GET /documents/executions/{id}` | `{status: running\|completed\|failed, progress, message, chunks_indexed}` |
| Feedback | `POST /feedback` body `{query_id, rating 1-5, query, answer, sources[], comment}` | |
| Usage | `GET /tenants/{slug}/usage` | `{total_queries, total_tokens, total_cost_usd, cache_hits, cache_hit_rate}` |
| Health | `GET /health` (no `/api/v1`) | |

**Getting access is normal API usage, not a change to RAG_SERVER.** I do this myself, once per institute, with my RAG_SERVER login — Claude must not do it on the live server: `POST /api/v1/tenants {slug, name}` → `POST /api/v1/security/api-keys {name, tenant, role:"member"}` (the key is shown only once).

---

## Phase 0 — Explore and report (no code changes)

1. Map the backend: `main.py` (all routes, esp. `/doubt`, `/doubt/stream`, `/test/generate`, `/answer/evaluate`, teacher/admin routes), `graph/` (state, coaching graph, subgraphs), every file in `agents/` and `rag/`, `auth/supabase_auth.py`, `scheduler/jobs.py`, `schema.sql`, `requirements.txt`, `.env.example`, Dockerfile/railway files, tests.
2. Build a complete inventory of the old RAG: every import/call of `rag/retriever.py`, `rag/qdrant_client.py`, `rag/ingest.py`, `rag/transcribe.py`, `rag/image_utils.py`, `qdrant_client`, `sentence_transformers` / embedding models, `CrossEncoder`, Tavily, HyDE/CRAG/RAPTOR helpers, `lru_cache` retrieval caches. For each: file, function, what it is used for. Separately list uses of Qdrant or embeddings that are **not** RAG (e.g. Mem0 long-term memory stored in Qdrant, doubt clustering embeddings) — those are decided in Phase 5, not removed blindly.
3. Find out exactly:
   - how `/doubt/stream` emits SSE today (the frontend expects plain `data: <text>` tokens, `data: [STATUS]<node>`, `data: [ERROR]<msg>`, `data: [DONE]`) and how it handles newlines inside tokens;
   - how photo doubts are handled (Gemini vision → text?) and how socratic mode works;
   - whether each agent is sync or async;
   - how `institute_id` reaches the doubt/test flows and what the `institutes` table holds;
   - what content is in Qdrant now (collections, payload fields like source/subject) and whether the original files that `rag/ingest.py` ingested exist in the repo or elsewhere;
   - whether `httpx` is already a dependency.
4. Reply with the file map, the inventory, the answers above, and any mismatch with this prompt. **Do not change any code in Phase 0.**

## Phase 1 — Connector, per-institute config, health

### 1.1 Add the connector

Create `rag/rag_server_client.py` with exactly this code (it was tested against RAG_SERVER: upload, hybrid search, streamed answer with citations, tenant isolation, fail-soft when the server is down). Add `httpx` to `requirements.txt` if it's missing.

```python
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
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{_url()}/api/v1/search/hybrid",
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
        with httpx.Client(timeout=_timeout()) as client:
            r = client.post(f"{_url()}/api/v1/search/hybrid",
                            json=_search_body(query, top_k, tenant), headers=_headers(api_key))
            r.raise_for_status()
            return [_to_chunk(h) for h in r.json().get("hits", []) if h.get("metadata")]
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER search failed (%s)", exc)
        return []


async def search_many(queries: list[str], *, top_k: int = 3,
                      tenant: str | None = None, api_key: str | None = None) -> list[dict[str, Any]]:
    """Search several queries in parallel (e.g. one per weak concept), de-duplicated."""
    results = await asyncio.gather(*(search(q, top_k=top_k, tenant=tenant, api_key=api_key) for q in queries))
    seen: set[Any] = set()
    merged: list[dict[str, Any]] = []
    for chunks in results:
        for c in chunks:
            if c["id"] not in seen:
                seen.add(c["id"])
                merged.append(c)
    return merged


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
        async with httpx.AsyncClient(timeout=httpx.Timeout(_timeout(), read=120)) as client:
            async with client.stream("POST", f"{_url()}/api/v1/rag/stream/ask",
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
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{_url()}/api/v1/documents/upload",
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
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        r = await client.get(f"{_url()}/api/v1/documents/executions/{execution_id}",
                             headers=_headers(api_key))
        r.raise_for_status()
        return r.json()


async def _wait_for(client: httpx.AsyncClient, exec_id: str, poll_seconds: float,
                    max_wait: float, api_key: str | None = None) -> dict[str, Any]:
    waited = 0.0
    while waited < max_wait:
        r = await client.get(f"{_url()}/api/v1/documents/executions/{exec_id}",
                             headers=_headers(api_key))
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
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{_url()}/api/v1/feedback", json=body, headers=_headers(api_key))
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
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.get(f"{_url()}/api/v1/tenants/{_tenant(tenant)}/usage",
                                 headers=_headers(api_key))
            return r.json() if r.status_code < 400 else None
    except Exception as exc:  # noqa: BLE001
        log.warning("RAG_SERVER usage failed (%s)", exc)
        return None


async def health() -> bool:
    if not _url():
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            return (await client.get(f"{_url()}/health")).status_code == 200
    except Exception:  # noqa: BLE001
        return False
```

### 1.2 Per-institute tenant + key

Add `migrations/<date>_rag_server.sql` (and append the same SQL to `schema.sql`):

```sql
alter table institutes add column if not exists rag_tenant text;
alter table institutes add column if not exists rag_api_key text;   -- service role only
```

- Make sure RLS/policies do not expose `rag_api_key` to anon/authenticated clients (if `institutes` is readable by clients, put the key in a separate table `institute_secrets(institute_id pk, rag_api_key)` with RLS enabled and no policies).
- Create `rag/rag_config.py` with `get_rag_config(institute_id) -> (tenant, api_key)`: read the institute row via the service-role client, fall back to the `RAG_SERVER_TENANT` / `RAG_SERVER_API_KEY` env vars, cache for ~5 minutes.

### 1.3 Env + health

- Add to `.env.example`: `RAG_SERVER_URL=`, `RAG_SERVER_API_KEY=`, `RAG_SERVER_TENANT=`, `RAG_SERVER_TIMEOUT=30`.
- Add `GET /admin/rag/health` (admin only) → `{configured, reachable, tenant}`.
- Log a clear warning at startup if `RAG_SERVER_URL` is not set.

### 1.4 Tests

Add `tests/test_rag_server_client.py` using `httpx.MockTransport` / respx / monkeypatch: disabled without config returns `[]`; `search` maps hits to `{id,text,source,page,score}`; 403 and connection errors return `[]`; `ask_stream` parses `data:` lines; `upload_document` returns `status:"failed"` on 4xx and when unreachable.

**Done when:** app starts with and without `RAG_SERVER_URL`; tests pass. (The old RAG is still present after this phase; it's removed in Phase 5.)

## Phase 2 — Doubt solving through RAG_SERVER only

### 2.1 Backend: `/doubt/stream` (and `POST /doubt`)

- **Photo doubt:** keep the existing Gemini-vision step that turns the image into question text (this is not RAG). The extracted text becomes the question.
- **Normal doubts:** call `rag_server_client.ask_stream(question, tenant, api_key, conversation_id=…, new_conversation=…)` and translate events into the **existing** SSE format so the current frontend keeps working:
  - `step` → `data: [STATUS]<step name>`
  - `token` → `data: <token>` (handle newlines the same way the current code does)
  - `memory` → remember `conversation_id`
  - `complete` → one new line `data: [META]{json}` with `{doubt_id, citations:[{source, page}], answerable, confidence, conversation_id, provider}`, then `data: [DONE]`
  - `error` (RAG_SERVER down, not configured, 403, …) → `data: [ERROR]The doubt service is busy right now, please try again in a minute.` then `data: [DONE]`. Log the real reason.
- **Socratic mode:** RAG_SERVER can't do Socratic prompting, so: retrieve with `rag_server_client.search(question, top_k=5, tenant, api_key)`, put `format_context(chunks)` into the existing Socratic doubt-agent prompt, and stream the coaching LLM's reply as today. Send the same `[META]` line with `citations_of(chunks)`. If search returns `[]`, still answer Socratically but set `answerable:false` in `[META]`.
- Accept two new optional request fields: `conversation_id` (string) and `new_conversation` (bool, default true for the first message of a chat).
- If `answerable` is false or `confidence == "low"`: still show the answer, and create an `alerts` row for the student's teacher (type `content_gap`, message `"Doubt not covered by institute material: <question>"`), de-duplicated per question per day.
- Log every doubt to `doubt_logs` as today, plus new columns (`alter table doubt_logs add column if not exists …`): `citations jsonb`, `answerable boolean`, `confidence text`, `conversation_id text`, `rating smallint`. The `doubt_id` in `[META]` is this row's id.
- Keep episodic memory / Mem0 / weakness-signal updates exactly as the current doubt flow does, using the final answer text.
- Remove the old retrieval calls from the doubt agent / doubt subgraph (the old RAG modules themselves are deleted in Phase 5).

### 2.2 Backend: feedback

`POST /doubt/feedback {doubt_id, helpful: bool, comment?}` (student only, must own the doubt) → store `rating` (5 or 1) on `doubt_logs`, then fire-and-forget `rag_server_client.send_feedback(doubt_id, rating, query, answer, sources)`.

### 2.3 Frontend (coaching_inst_ui)

- `lib/api.ts` → `streamDoubt`: handle `data: [META]{json}` (`JSON.parse` → new optional `onMeta(meta)` callback). Everything else unchanged.
- `pages/student/doubt.tsx`:
  - keep a `conversationId` in state; send `conversation_id` and `new_conversation` (true on the first message / after "New chat"); add a **"New chat"** button;
  - store `meta` on the assistant message and show **source chips** under each answer ("Physics_Notes.pdf · p. 12"), de-duplicated;
  - if `answerable === false` or `confidence === "low"`, show a small amber note: "Not clearly covered in your institute's notes — your teacher has been informed.";
  - 👍 / 👎 buttons → `POST /doubt/feedback`, once per answer;
  - match existing Tailwind tokens (`card`, `badge-brand`, …) and dark mode.

**Done when:** doubts stream with source chips; an off-syllabus doubt shows the amber note and creates a teacher alert; follow-ups in one chat use memory; photo and Socratic doubts work; with RAG_SERVER unreachable the student sees the friendly message, nothing crashes.

## Phase 3 — Teacher uploads study material (the only way content enters the RAG)

### 3.1 Backend

New table:

```sql
create table if not exists study_materials (
  id uuid primary key default gen_random_uuid(),
  institute_id uuid not null references institutes(id),
  uploaded_by uuid not null,
  filename text not null,
  subject text, chapter text, class_level text,
  exam text,                         -- JEE / NEET / Boards / Other
  material_type text,                -- notes / ncert / pyq / dpp / lecture / other
  storage_path text,                 -- original file in Supabase Storage
  execution_id text,
  status text not null default 'running',   -- running / completed / failed
  message text,
  chunks_indexed int,
  created_at timestamptz default now()
);
```

with RLS consistent with the other tables.

- `POST /teacher/materials/upload` (teacher/admin; multipart `file`, `subject`, `chapter`, `class_level`, `exam`, `material_type`): validate extension + 50 MB; rename to `"{subject}_{chapter}_{material_type}_{original}"` (sanitised) so citations read well; save the original to **Supabase Storage** (private bucket `study-materials`, path `{institute_id}/{id}/{filename}`); call `upload_document(..., wait=False)`; save the row.
- `GET /teacher/materials` (own institute): list rows; refresh `running` rows via `upload_status` and update them.
- `POST /teacher/materials/{id}/reindex`: download from Storage, send to RAG_SERVER again (for when the hosted RAG_SERVER lost data after its own redeploy).
- `DELETE /teacher/materials/{id}`: remove the row and the Storage file. (RAG_SERVER chunks stay — note this in the UI; don't call any RAG_SERVER delete endpoint.)
- If RAG is not configured, return 503 with a clear message.

### 3.2 Lecture transcripts

If `rag/transcribe.py` is kept, change its output step: instead of writing to Qdrant, save the transcript as a `.txt` (with timestamps in the text) and send it through the same upload path with `material_type="lecture"`. If it's only a CLI, make it call the new endpoint or `upload_document` directly.

### 3.3 Frontend

New page `pages/teacher/materials.tsx`: upload form, list with status badges (running → spinner, completed → "N chunks", failed → message + **Re-index** button), polling every 3 s while anything is running. Add a "Study Material" link in `components/Shell.tsx` for teacher/admin.

**Done when:** a teacher uploads a PDF, sees "completed", and a student doubt about it cites it.

## Phase 4 — Agents grounded in RAG_SERVER (tests, grading, flashcards)

For each agent: retrieve with `search` / `search_many` / `search_sync` (match the agent's sync/async style) using the institute's tenant/key, put `format_context(chunks)` into the prompt, tell the LLM to rely on it, and store `citations_of(chunks)` with the output. Remove the agent's old retriever calls. If retrieval returns `[]`, the agent continues without context (as a plain LLM call) and marks `source: null` — never fail the run.

- **test_generator** — one query per weak concept (from `weakness_map`), e.g. `"<concept> <subject> previous year question"`, `top_k=3`, via `search_many`. Base questions on the retrieved material/PYQs, keep exam pattern, add a `source` field (`{source, page}` or `null`) per question. Keep the rest of the schema.
- **reviewer_agent** — a question with a `source` must be consistent with that chunk; flag otherwise (existing regenerate loop, max iterations unchanged).
- **answer_evaluator** (theory only) — retrieve for the question, `top_k=3`; grade against the model answer **and** the material; add `grounding_sources`. MCQ grading unchanged.
- **flashcard_agent** — build cards from retrieved chunks for weak concepts; each card gets `source`. Skip a concept when nothing is retrieved.
- **study_plan_agent / others** — if Phase 0 found any other retriever use, convert it the same way.
- **Frontend `/teacher/review`** — show each question's source under it (small muted text).

Keep the parallel fan-out rule intact (each branch writes only its own state keys). Add any new state keys to `graph/state.py`.

**Done when:** generated tests show sources on the review page; grading and flashcards work; with RAG_SERVER down, tests/grading/flashcards still complete (without sources).

## Phase 5 — Remove the old RAG completely

1. **Move existing content first.** Content that is in Qdrant today must end up in RAG_SERVER before Qdrant is removed:
   - If the original files (NCERT/PYQ PDFs, notes) exist, write `scripts/migrate_to_rag_server.py` that uploads them per institute via `upload_document` and creates `study_materials` rows (+ Storage copies).
   - If only Qdrant has the text, the script exports the payload text grouped by source/document into `.md` files (one per source, with chapter headings) and uploads those.
   - Run it with `--dry-run` first and show me the plan; run for real only after I say yes.
2. **Delete the old RAG** after I confirm the migration worked: `rag/retriever.py`, `rag/qdrant_client.py`, `rag/ingest.py` (or reduce it to a thin wrapper around `upload_document`), `rag/image_utils.py` if it only fed the RAG, HyDE/CRAG/RAPTOR/CrossEncoder/Tavily code, retrieval `lru_cache`s, and their tests.
3. **Dependencies & env:** remove `qdrant-client`, `sentence-transformers`, CrossEncoder / embedding model downloads, `tavily-python` from `requirements.txt` only if nothing else uses them; remove `QDRANT_URL`, `QDRANT_API_KEY`, `TAVILY_API_KEY` from `.env.example` and the README. The Railway build gets much smaller and faster.
4. **Non-RAG uses** found in Phase 0 (e.g. Mem0 memory stored in Qdrant, doubt-cluster embeddings): don't delete these silently. Tell me what each one needs and propose the option to keep them working (e.g. Mem0 on its own storage, clustering via the LLM or a tiny local embedding). Implement only what I approve.
5. `grep` the repo to prove nothing imports the removed modules; run all tests.

**Done when:** no code references Qdrant/old retriever for RAG, the app starts and all features work through RAG_SERVER, and the dependency list is smaller.

## Phase 6 — Insights for teachers and admins

- **Teacher dashboard → "Content gaps" card:** top questions from `alerts` of type `content_gap` (last 14 days, grouped), with a link to Study Material upload.
- **Teacher dashboard → "Answer quality":** % helpful (`doubt_logs.rating`) and % answerable over the last 7 days.
- **Admin analytics → "AI usage":** `GET /admin/rag/usage` → `tenant_usage(...)`: total queries, tokens, estimated cost, cache hit rate; "RAG server not connected" when `None`.
- **Doubt clusters:** the nightly `doubt_cluster_agent` attaches the top RAG_SERVER source per cluster (via `search`) so "hot topics" link to the right notes.

## Phase 7 — End-to-end test with a local copy of RAG_SERVER

1. In a separate throwaway folder, run a **local copy** just for testing (never push anything from it; never point tests at the live server):
   ```bash
   git clone https://github.com/SanjayRawat0570/RAG_SERVER rag_server_local && cd rag_server_local
   python -m venv .venv && .venv/bin/pip install -r requirements.txt
   APP_ENV=development DATA_DIR=./data uvicorn app.main:app --port 8765
   ```
2. Create a tenant + key on the local copy:
   ```bash
   curl -X POST localhost:8765/api/v1/tenants -H 'Authorization: Bearer dev' \
     -H 'content-type: application/json' -d '{"slug":"inst-demo","name":"Demo Institute"}'
   curl -X POST localhost:8765/api/v1/security/api-keys -H 'Authorization: Bearer dev' \
     -H 'content-type: application/json' -d '{"name":"coaching","tenant":"inst-demo","role":"member"}'
   ```
3. Coaching backend env: `RAG_SERVER_URL=http://localhost:8765`, `RAG_SERVER_API_KEY=<key>`, `RAG_SERVER_TENANT=inst-demo`. (Without an LLM key on the local copy, its answers are extractive quotes from the notes — fine for testing.)
4. Walk through and report pass/fail:
   - [ ] teacher uploads a notes PDF → completed with chunk count
   - [ ] student doubt about it → streamed answer + source chip
   - [ ] same doubt reworded → fast (semantic cache)
   - [ ] follow-up "explain simpler" in the same chat → uses conversation memory
   - [ ] off-syllabus doubt → amber note + teacher `content_gap` alert
   - [ ] 👍/👎 saved
   - [ ] photo doubt and Socratic doubt work, with sources
   - [ ] generate test → questions carry sources on `/teacher/review`
   - [ ] evaluate a theory answer → `grounding_sources` present
   - [ ] flashcards generated with sources
   - [ ] stop the local RAG_SERVER → doubt shows the friendly message; tests, grading and flashcards still complete; nothing crashes
   - [ ] a key for tenant A cannot read tenant B
   - [ ] no API key in any frontend response or log
   - [ ] no Qdrant / old-retriever import left (grep)
5. Run the full test suite + new tests; `npm run build` in the UI repo.

## Phase 8 — Deployment and docs

**RAG_SERVER (hosted): no changes at all.** Use the live URL as-is. My only steps there are normal API usage that I do myself: create a tenant per institute and a `member` API key for it (same calls as Phase 7 step 2, with my login instead of `Bearer dev`).

Things the coaching backend must cope with, since RAG_SERVER won't be changed:

- If the live RAG_SERVER answers in extractive mode (no LLM configured there), answers are quotes from the notes. Acceptable; don't try to fix it on the RAG side.
- If RAG_SERVER loses data after one of its own redeploys, searches return nothing. The **Re-index** button (Phase 3) and an admin **"Re-index all"** action (add it: loops over `study_materials` for the institute) restore it from Supabase Storage.

**coaching_inst_server on Railway:** add `RAG_SERVER_URL`, `RAG_SERVER_TIMEOUT`, and either the env key/tenant (single institute) or fill `rag_tenant` / `rag_api_key` per institute; remove the Qdrant/Tavily variables. Run the new SQL in the Supabase SQL editor (not auto-applied) and create the private Storage bucket `study-materials`.

**Docs:** update the backend README (architecture with RAG_SERVER as the only RAG, removed components, new env vars, new endpoints, SQL to run, migration script) and the UI README (Study Material page, citations, feedback, insights).

---

## Decisions after Phase 0

Agreed with the owner on 2026-10-17. Where these differ from the text above, **these win**.

**Repo facts**
- One monorepo: `backend/` (FastAPI) and `frontend/` (Next.js). Root `Dockerfile` + `railway.json`.
- `institutes` has **no RLS**, so the per-institute key lives in `institute_secrets` (RLS on, no policies). `institutes.rag_tenant` holds the slug.
- `alerts` uses the column `alert_type` (not `type`); teacher views sort by `risk_score desc`.
- All agents are synchronous; `/doubt/stream` is the only async endpoint.

**Decisions**
1. **Tenant resolution** is always server-side, from the caller's `students.institute_id` (or the teacher/admin's institute) — never from the request body. Accounts with no institute use the env default tenant/key.
2. **Doubt confidence:** new column `doubt_logs.rag_confidence text`; keep the existing numeric `confidence` column.
3. **Rank predictor does not use RAG.** Phase 4 adds a Supabase table `nta_cutoffs` (exam, year, category, score/percentile, rank, …), makes `rank_predictor` read from it, and adds a small CSV import script.
4. **Content migration:** the owner re-runs the read-only Qdrant inventory from another network. If Qdrant has the data, Phase 5 exports it; otherwise Phase 5 skips export and fresh NCERT/PYQ PDFs are uploaded through the Study Material page.
5. The connector gets an extra **`search_many_sync`** (parallel threads) for the sync agents.
6. **`content_gap` alerts** use `alert_type='content_gap'` and `risk_score=0`, so they never rank above real at-risk alerts.
7. **Theory-grading grounding** (Phase 4) goes into `grade_text_answer` (inside `/test/submit`), not `/answer/evaluate` (that is the handwritten-photo grader).
8. **Phase 2 errors:** `[ERROR]` always sends a friendly message, never raw exception text. The doubt page uses `[META]` confidence instead of `splitConfidence` when `[META]` is present.
9. **Phase 5:** keep `sentence-transformers` for the non-RAG uses (copy detection, doubt clustering, knowledge graph). Move long-term memory from the Qdrant collection `longterm_memories` to Supabase pgvector so Qdrant can be removed completely. Add `scikit-learn` to requirements explicitly. Remove the unused `mem0ai` dependency.
10. Create `backend/tests`, `backend/.env.example` and `backend/migrations`.
