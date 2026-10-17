# SmartCoaching — Backend

AI coaching engine for JEE / NEET institutes. A **FastAPI** server orchestrating
**8+ LangGraph agents** over **Supabase (Postgres + Auth)**, with **APScheduler** running
the nightly/weekly automation. All retrieval of study material (notes, NCERT, PYQs) goes
to **[RAG_SERVER](https://github.com/SanjayRawat0570/RAG_SERVER)** — a separate, hosted,
multi-tenant RAG service used as-is over HTTP. It is the **only** RAG; this backend has
no vector store or retriever of its own.

>  **Frontend (UI) repository:** https://github.com/SanjayRawat0570/coaching_inst_ui
> The Next.js client lives in that repo and talks to this backend over REST + SSE.

---

## Stack

| Layer | Choice |
|-------|--------|
| API | FastAPI + Uvicorn (SSE streaming for doubts) |
| Orchestration | LangGraph (supervisor + worker, parallel fan-out, HITL, checkpointer) |
| LLMs | Groq `llama-3.3-70b` → Gemini `2.5-flash` → OpenRouter (fallback chain) |
| Vision | Gemini `2.5-flash` (handwriting + question photos) |
| Auth + DB + files | Supabase (Postgres + Auth + RLS + Storage for uploaded study material) |
| RAG | **RAG_SERVER** (hybrid dense + BM25 search, grounded answers with citations, semantic cache, conversation memory) via [rag/rag_server_client.py](rag/rag_server_client.py) |
| Local embeddings | `all-MiniLM-L6-v2` for **non-RAG** features only: long-term memory, copy detection, doubt clustering, concept graph |
| Memory | Working (last N turns) · Long-term (pgvector `student_memories`) · Episodic (Postgres) · chat memory (RAG_SERVER `conversation_id`) |
| Jobs | APScheduler (timezone `Asia/Kolkata`) |
| Notifications | Resend (email) + Twilio (WhatsApp) |
| Voice | Browser Web Speech API (arrives pre-transcribed); Whisper optional (offline lecture transcription only) |

---

## Quick start

```bash
# 1. Python 3.11 + deps
pip install -r requirements.txt

# 2. Secrets — copy the template and fill in your free keys
cp .env.example .env              # Supabase, RAG_SERVER, Groq/Gemini/OpenRouter, Resend, Twilio

# 3. Database — run schema.sql ONCE in the Supabase SQL editor (NOT auto-applied).
#    On an existing database, run the files in migrations/ instead (see "Database").

# 4. Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5. Tests (no network needed — RAG_SERVER, LLMs and Supabase are faked)
pip install -r requirements-dev.txt && python -m pytest
```

`GET /health` → `{"status": "ok"}` confirms it's up. Interactive docs at `/docs`.
If `RAG_SERVER_URL` is not set the app still starts, logs a warning, and every
retrieval fails soft (doubts show a friendly "busy" message; agents run without context).

> **Note:** `openai-whisper` is **not** in `requirements.txt` (it needs ffmpeg + special
> build flags and is only used by the offline lecture-transcription CLI). Install it
> manually if you need [`rag/transcribe.py`](rag/transcribe.py):
> `pip install "setuptools<81" wheel && pip install --no-build-isolation openai-whisper==20231117`

---

## High-level architecture

```
                         ┌──────────────────────────────┐
   Next.js UI  ──REST──▶ │           FastAPI            │ ──▶ Supabase (Postgres+Auth+Storage)
   (separate repo) ◀SSE─ │           main.py            │ ──▶ RAG_SERVER (X-API-Key, per institute)
                         │  Supabase-JWT auth + roles   │ ──▶ Groq/Gemini/OpenRouter
                         └───────────────┬──────────────┘ ──▶ Resend / Twilio
                                         │
                          ┌──────────────▼───────────────┐
                          │   LangGraph supervisor graph  │
                          │      (graph/coaching_graph)   │
                          └──────────────┬───────────────┘
        route on state["action_type"]    │
        ┌──────────────┬─────────────────┼────────────────────┐
        ▼              ▼                  ▼                    ▼
     doubt           test             evaluate              rank
        │              │                  │                    │
   doubt_node    generator→reviewer   evaluator          rank_predictor
        │         (loop ≤3) → HITL    fan-out ∥ 3:               │
       END         interrupt → END   progress·rank·flashcard    END
                                         → aggregator → END

   APScheduler (background): at-risk · inactivity · doubt-clusters ·
   parent-reports · study-plans · flashcard-reminders
```

---

## The LangGraph supervisor ([graph/coaching_graph.py](graph/coaching_graph.py))

A single master graph routes on `state["action_type"]` via a conditional entry point.
Shared state is [`CoachingState`](graph/state.py) (a `TypedDict` passed between every node).

| `action_type` | Flow |
|---------------|------|
| `doubt` | `doubt_node` → END |
| `test` | `test_generator` → `reviewer` (regenerate loop, max 3) → **HITL** interrupt → END |
| `evaluate` | `evaluator` → **parallel** `progress ∥ rank ∥ flashcard` → `aggregator` → END |
| `rank` | `rank_predictor` → END |

**Parallel fan-out detail:** after evaluation, three agents run concurrently. LangGraph
forbids two branches writing the same state key, so each branch returns only **disjoint**
keys (`progress→weakness_update`, `rank→air_rank/score`, `flashcard→flashcards_generated`);
`aggregator` is the join point.

**HITL (human-in-the-loop):** the graph is compiled with `interrupt_before=["hitl"]` and a
checkpointer, so a test run **pauses** for teacher approval, then resumes to END once the
teacher's decision is supplied via `update_state`. See [graph/test_subgraph.py](graph/test_subgraph.py).

Isolated subgraphs for independent testing/streaming:
- [graph/doubt_subgraph.py](graph/doubt_subgraph.py) — doubt only
- [graph/test_subgraph.py](graph/test_subgraph.py) — generate → review → HITL
- [graph/monitoring_subgraph.py](graph/monitoring_subgraph.py) — `at_risk → parent_report`

---

## The agents ([agents/](agents/))

| Agent | Role |
|-------|------|
| `doubt_agent` | Answers doubts 24/7 (text/voice/photo) through RAG_SERVER, with citations; Socratic mode = RAG_SERVER search + coaching LLM |
| `test_generator` | Drafts a personalised test from RAG_SERVER material per weak concept; each question carries a `source` |
| `reviewer_agent` | Self-reviews questions (incl. consistency with the cited source); loops back to regenerate (bounded, `MAX_ITERATIONS`) |
| `answer_evaluator` | Grades submissions — MCQ (negative marking) + theory (AI vs model answer **and** the institute's material → `grounding_sources`) |
| `progress_tracker` | Updates the per-concept `weakness_map` |
| `rank_predictor` | Predicts All-India Rank from the `nta_cutoffs` table (CSV-imported reference data, not RAG) |
| `flashcard_agent` | Builds spaced-revision flashcards from RAG_SERVER material (each card has a `source`) + surfaces due cards |
| `at_risk_agent` | Nightly engagement scoring → flags likely dropouts ~7 days early |
| `inactivity_alert_agent` | Emails teacher+parent on 3-day no-login / skipped test |
| `doubt_cluster_agent` | Clusters similar class doubts into "hot topics", each linked to its top RAG_SERVER source |
| `parent_report_agent` | Weekly plain-language progress report (email + WhatsApp) |
| `study_plan_agent` | Rebuilds each student's weekly timetable |

Supporting: [graph/knowledge_graph.py](graph/knowledge_graph.py) (concept prerequisite graph).

---

## RAG: RAG_SERVER is the only retrieval ([rag/](rag/))

RAG_SERVER is a separate hosted service and is **never modified** from here — this
backend is a client of its HTTP API. Each institute is one RAG_SERVER **tenant** with a
tenant-scoped `member` API key (a key for tenant A gets 403 on tenant B).

| Module | What it does |
|--------|--------------|
| [rag/rag_server_client.py](rag/rag_server_client.py) | HTTP connector: hybrid search (`search`, `search_sync`, `search_many[_sync]`), streamed grounded answers (`ask_stream`), upload + status, feedback, usage, health. **Every call fails soft.** |
| [rag/rag_config.py](rag/rag_config.py) | `get_rag_config(institute_id) → (tenant, api_key)` from `institutes.rag_tenant` + `institute_secrets.rag_api_key`, else the env defaults; cached 5 min |
| [rag/grounding.py](rag/grounding.py) | Helpers for the sync agents: parallel retrieval, `[n]` → `{source, page}` |
| [rag/study_materials.py](rag/study_materials.py) | Teacher uploads: original → Storage bucket `study-materials`, copy → RAG_SERVER; list/refresh, re-index, delete |
| [rag/ingest.py](rag/ingest.py), [rag/transcribe.py](rag/transcribe.py) | CLIs that upload a file / a timestamped lecture transcript through the same path |
| [rag/embedder.py](rag/embedder.py), [rag/image_utils.py](rag/image_utils.py) | Not RAG: local MiniLM embeddings (memory, clustering, copy check, concept graph) and photo clean-up for Gemini vision |

**Where retrieval is used**

| Flow | How |
|------|-----|
| Doubt (normal) | `ask_stream` → tokens, `[META]` with citations / answerable / confidence / conversation_id |
| Doubt (Socratic) | `search(top_k=5)` → context in the Socratic prompt → coaching LLM streams hints |
| Doubt (photo) | Gemini vision → question text → as above |
| Test generation | one `search` per weak concept (`"<concept> <subject> previous year question"`, top 3) |
| Theory grading | `search(question, top_k=3)` per answered theory question |
| Flashcards | `search` per wrong concept; concepts with no material are skipped |
| Doubt clusters | top source per cluster (`top_k=1`) |

**When RAG_SERVER is down / not configured:** doubts send `[ERROR]The doubt service is busy
right now, please try again in a minute.` (the real reason is only logged); Socratic doubts
still answer with `answerable:false`; tests, grading and flashcards complete without sources.
The API key is never sent to the browser or logged.

**Content gaps:** when RAG_SERVER says a doubt is not answerable (or confidence is low) the
student still gets the answer, an amber note, and the teacher gets one `content_gap` alert
per question per day.

**Removed** (old in-process RAG): Qdrant (`rag/qdrant_client.py`), the 6-pattern
`rag/retriever.py` (agentic multi-query, HyDE, RAPTOR, CRAG, Tavily web fallback,
CrossEncoder rerank, `lru_cache`), and the `qdrant-client`, `langchain-community`,
`pymupdf` and `mem0ai` dependencies. Long-term memory moved from Qdrant to pgvector.

---

## Auth & roles ([auth/supabase_auth.py](auth/supabase_auth.py))

- Every request carries a **Supabase-issued JWT** (`Authorization: Bearer …`).
- `get_current_user` validates the token and returns `{id, email, role, name, institute_id, …}`.
- `require_role("teacher", "admin")` is a dependency factory enforcing role access.
- The backend uses the **service-role key** so server-side reads/writes bypass RLS
  (RLS checks `auth.uid()`, which is null for a keyed backend call).
- Four roles: **student · teacher · parent · admin** — each only sees its own data.

---

## End-to-end: the test lifecycle

```
1. Teacher  POST /test/generate        → generator+reviewer loop → saved status="pending"
2. Teacher  POST /test/approve         → edits/sets per-question marks → status="ready"
                                          (+ due_date, default 3 days out)
3. Student  POST /test/submit          → answers captured
4. Backend  answer_evaluator           → MCQ negative marking + AI-graded theory
5. Post-test  evaluator → (progress ∥ rank ∥ flashcard)  [parallel]
6. status="evaluated" → result shows on student, teacher, parent & admin dashboards
```

---

## API surface (selected, see [main.py](main.py))

| Area | Endpoints |
|------|-----------|
| Auth/health | `GET /health` · `POST /auth/signup` |
| Doubts | `POST /doubt` · `POST /doubt/stream` (SSE) · `POST /doubt/feedback` |
| Tests | `POST /test/generate` · `POST /test/approve` · `POST /test/submit` · `POST /answer/evaluate` |
| Student | `GET /progress` · `POST /activity/ping` · `GET /flashcards/due` · `POST /flashcards/review` · `GET/POST /student/plan…` · `GET/POST /student/concept-map…` · `GET /leaderboard` · `GET /badges` · challenges |
| Teacher | `GET /teacher/overview` · `/teacher/alerts` · `/teacher/students` · `/teacher/submissions` · `/teacher/tests/pending` · `POST /teacher/tests/generate-class` · `/teacher/doubt-clusters` · `/teacher/activity-heatmap` · `GET /teacher/rag-insights` |
| Study material | `POST /teacher/materials/upload` · `GET /teacher/materials` · `POST /teacher/materials/{id}/reindex` · `DELETE /teacher/materials/{id}` · `POST /admin/materials/reindex-all` |
| Parent | `GET /parent/report` · `POST /parent/goal` · `POST /parent/report/send` · `/parent/activity-heatmap` |
| Admin | `GET /admin/analytics` · `GET /admin/audit-logs` · `GET /admin/rag/health` · `GET /admin/rag/usage` |

**Doubt stream format** (`POST /doubt/stream`, body adds optional `conversation_id`,
`new_conversation`): `data: <token>` · `data: [STATUS]<text>` · `data: [ERROR]<friendly
message>` · `data: [META]{doubt_id, citations:[{source,page}], answerable, confidence,
conversation_id, provider}` · `data: [DONE]`. A token containing newlines is sent as several
`data:` lines in one event; the client joins them with `\n`.

The institute (and so the RAG_SERVER tenant) is always resolved **server-side** from the
caller — a request-body `institute_id` is ignored for RAG.

---

## Scheduled automation ([scheduler/jobs.py](scheduler/jobs.py))

Started on app boot via the FastAPI `lifespan` handler (timezone `Asia/Kolkata`):

| When | Job |
|------|-----|
| Nightly 23:00 | `at_risk_agent.run_nightly` — flag dropouts 7 days early |
| Nightly 21:00 | `inactivity_alert_agent.run_nightly` — 3-day no-login / skipped test |
| Nightly 02:00 | `doubt_cluster_agent.run_nightly` — cluster similar doubts |
| Sunday 20:00 | `parent_report_agent.run_weekly` — WhatsApp/email reports |
| Monday 07:00 | `study_plan_agent.run_weekly` — rebuild timetables |
| Every 5 min | flashcard due-reminder checker |

---

## Database ([schema.sql](schema.sql))

Run once in the Supabase SQL editor (not auto-applied). Tables:

`institutes` · `institute_secrets` · `students` · `concepts` · `concept_relationships` ·
`weakness_map` · `doubt_logs` · `tests` · `alerts` · `parent_reports` · `episodic_memories` ·
`student_memories` · `flashcards` · `study_plans` · `study_materials` · `doubt_clusters` ·
`nta_cutoffs` · `activity_log` · `badges` · `challenges` · `audit_logs`

**Existing database?** Run these in order in the SQL editor (all idempotent; the same SQL
is already in `schema.sql`):

| File | Adds |
|------|------|
| [migrations/2026-10-17_rag_server.sql](migrations/2026-10-17_rag_server.sql) | `institutes.rag_tenant`, `institute_secrets` (RLS on, no policies — service role only) |
| [migrations/2026-10-18_doubt_rag_server.sql](migrations/2026-10-18_doubt_rag_server.sql) | `doubt_logs.citations / answerable / rag_confidence / conversation_id / rating` |
| [migrations/2026-10-18_study_materials.sql](migrations/2026-10-18_study_materials.sql) | `study_materials` + the private Storage bucket `study-materials` |
| [migrations/2026-10-18_grounded_agents.sql](migrations/2026-10-18_grounded_agents.sql) | `flashcards.source`, `nta_cutoffs` |
| [migrations/2026-10-18_remove_old_rag.sql](migrations/2026-10-18_remove_old_rag.sql) | `student_memories` + `match_student_memories` RPC (long-term memory) |
| [migrations/2026-10-18_insights.sql](migrations/2026-10-18_insights.sql) | `doubt_clusters.source` |

Until a migration is run, the features that need it degrade (e.g. doubts are logged
without citations, cards are saved without a source) rather than fail.

**Per-institute RAG_SERVER access** (after creating the tenant + `member` key on
RAG_SERVER with your own login):

```sql
UPDATE institutes SET rag_tenant = 'inst-3f2a9c' WHERE id = '<institute uuid>';
INSERT INTO institute_secrets (institute_id, rag_api_key) VALUES ('<institute uuid>', 'sk-...')
ON CONFLICT (institute_id) DO UPDATE SET rag_api_key = EXCLUDED.rag_api_key, updated_at = NOW();
```

An institute uses its own tenant + key only when both are set; otherwise (and for
accounts with no institute) the `RAG_SERVER_TENANT` / `RAG_SERVER_API_KEY` env defaults apply.

## Scripts

| Command (from `backend/`) | What |
|---------------------------|------|
| `python -m scripts.migrate_to_rag_server --from-qdrant --memories --dry-run` | One-off: export the old Qdrant chunks (re-joined in reading order, one `.md` per source/subject with chapter headings) into RAG_SERVER, and copy long-term memories into pgvector. Also `--files DIR` for original PDFs. Needs `pip install qdrant-client==1.9.1` and `QDRANT_URL/KEY` just for this run. Always dry-run first. |
| `python -m scripts.import_nta_cutoffs <file.csv> [--dry-run]` | Load marks/percentile → AIR rows for the rank predictor (columns: [scripts/nta_cutoffs_template.csv](scripts/nta_cutoffs_template.csv)) |
| `python -m rag.ingest --file notes.pdf --material-type notes --subject Physics` | Upload one file as study material |
| `python -m rag.transcribe --media lecture.mp4 --subject Physics --chapter "Rotation"` | Whisper transcript (timestamped) → study material `lecture` |

---

## Environment variables

See [`.env.example`](.env.example) for the full, annotated list. Essentials:

```
GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY   # LLM fallback chain
SUPABASE_URL / SUPABASE_KEY / SUPABASE_SERVICE_KEY    # Auth + DB (service key = backend)
RAG_SERVER_URL                                        # hosted RAG_SERVER, without /api/v1
RAG_SERVER_API_KEY / RAG_SERVER_TENANT                # default tenant + member key
RAG_SERVER_TIMEOUT                                    # seconds per request (default 30)
RESEND_API_KEY / TWILIO_*                             # Email + WhatsApp
```

Removed: `QDRANT_URL`, `QDRANT_API_KEY`, `TAVILY_API_KEY` (delete them from Railway and
your `.env`; `QDRANT_*` is only needed once, locally, if you run the Qdrant migration script).

---

## Deployment — Railway (native Python build, no Docker)

Deployed on **Railway** using its native **Railpack** builder — no Dockerfile:

| Setting | Value |
|---------|-------|
| Builder | Railpack (auto-detects Python via `requirements.txt`) |
| Root Directory | the folder containing the backend (leave empty if the repo root *is* the backend) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Python | pinned to **3.11** via [`.python-version`](.python-version) |
| Health check | `/health` |

- **Do not set a `PORT` variable** — Railway injects it; the start command binds `$PORT`.
- Set the env vars from [`.env.example`](.env.example) in the Railway dashboard: add
  `RAG_SERVER_URL`, `RAG_SERVER_TIMEOUT`, and either `RAG_SERVER_API_KEY` +
  `RAG_SERVER_TENANT` (single institute) or per-institute rows (see "Database");
  remove `QDRANT_URL`, `QDRANT_API_KEY`, `TAVILY_API_KEY`.
- Run the SQL in `migrations/` in the Supabase SQL editor (creates the private
  Storage bucket `study-materials` too).
- The hosted RAG_SERVER itself needs **no changes**. If it answers in extractive mode
  (no LLM configured there) answers are quotes from the notes — expected. If it loses
  its data after one of its own redeploys, use **Re-index** per file or **Re-index all**
  (admin) on the Study Material page: originals are re-sent from Supabase Storage.
- The build is smaller now: no Qdrant client, CrossEncoder or Tavily stack.
- Live: `https://coachinginstserver-production.up.railway.app` (`/health`, `/docs`).

Full step-by-step (Railway + Vercel) is in [`../DEPLOYMENT.md`](../DEPLOYMENT.md).
The frontend deploys separately to **Vercel** from the
[UI repo](https://github.com/SanjayRawat0570/coaching_inst_ui), with
`NEXT_PUBLIC_API_URL` pointing at the Railway domain.

> A root [`Dockerfile`](../Dockerfile) + [`../railway.json`](../railway.json) also exist
> (for a Docker-based deploy / HuggingFace Spaces). They are unused by the native Railway
> setup above — delete them if you only deploy via Railpack.
