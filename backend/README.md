# SmartCoaching — Backend

AI coaching engine for JEE / NEET institutes. A **FastAPI** server orchestrating
**8+ LangGraph agents** over **Supabase (Postgres + Auth)** and **Qdrant (vector RAG)**,
with **APScheduler** running the nightly/weekly automation. 100% free-tier stack.

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
| Auth + DB | Supabase (Postgres + Auth + RLS) |
| Vector DB | Qdrant Cloud (NCERT, PYQs, institute notes) |
| Embeddings | `all-MiniLM-L6-v2`; rerank `ms-marco-MiniLM-L-6-v2` |
| Memory | Working (last N turns) · Long-term (Mem0) · Episodic (Postgres) |
| Jobs | APScheduler (timezone `Asia/Kolkata`) |
| Notifications | Resend (email) + Twilio (WhatsApp) |
| Voice | Browser Web Speech API (arrives pre-transcribed) / Whisper |

---

## Quick start

```bash
# 1. Python 3.11 + deps
pip install -r requirements.txt

# 2. Secrets — copy the root template and fill in your free keys
cp ../.env.example ../.env        # Supabase, Qdrant, Groq/Gemini/OpenRouter, Resend, Twilio

# 3. Database — run schema.sql ONCE in the Supabase SQL editor
#    (it is NOT auto-applied)

# 4. Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

`GET /health` → `{"status": "ok"}` confirms it's up. Interactive docs at `/docs`.

---

## High-level architecture

```
                         ┌──────────────────────────────┐
   Next.js UI  ──REST──▶ │           FastAPI            │ ──▶ Supabase (Postgres+Auth)
   (separate repo) ◀SSE─ │           main.py            │ ──▶ Qdrant (vectors)
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
| `doubt_agent` | Answers doubts 24/7 (text/voice/photo) grounded in RAG + memory |
| `test_generator` | Drafts a personalised test aimed at the student's weak concepts |
| `reviewer_agent` | Self-reviews questions; loops back to regenerate (bounded, `MAX_ITERATIONS`) |
| `answer_evaluator` | Grades submissions — MCQ (negative marking) + theory (AI vs model answer) |
| `progress_tracker` | Updates the per-concept `weakness_map` |
| `rank_predictor` | Predicts All-India Rank from score history |
| `flashcard_agent` | Generates spaced-revision flashcards + surfaces due cards |
| `at_risk_agent` | Nightly engagement scoring → flags likely dropouts ~7 days early |
| `inactivity_alert_agent` | Emails teacher+parent on 3-day no-login / skipped test |
| `doubt_cluster_agent` | Clusters similar class doubts into "hot topics" |
| `parent_report_agent` | Weekly plain-language progress report (email + WhatsApp) |
| `study_plan_agent` | Rebuilds each student's weekly timetable |

Supporting: [graph/knowledge_graph.py](graph/knowledge_graph.py) (concept prerequisite graph).

---

## RAG pipeline ([rag/retriever.py](rag/retriever.py)) — 6 patterns

```
question
  │
  ├─ 1. Agentic multi-query   (LLM plans 2–4 sub-queries → Qdrant search)
  │
  ├─ 2. CRAG quality gate     (LLM rates chunk relevance 0–10; pass if avg ≥ 5)
  │        │ fail
  │        ▼
  ├─ 3. HyDE fallback         (LLM writes a hypothetical NCERT answer → embed → search)
  │        │ still fail
  │        ▼
  ├─ 4. Web fallback          (Tavily, restricted to edu domains)
  │
  └─ 5. CrossEncoder re-rank   (re-rank by student level, keep top 5)

(RAPTOR multi-level retrieval also available for complexity-scaled depth.)
Results are cached with lru_cache. Vectors live in Qdrant ([rag/qdrant_client.py]).
Ingestion: [rag/ingest.py]; image OCR/preprocess: [rag/image_utils.py]; audio: [rag/transcribe.py].
```

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
| Doubts | `POST /doubt` · `POST /doubt/stream` (SSE) |
| Tests | `POST /test/generate` · `POST /test/approve` · `POST /test/submit` · `POST /answer/evaluate` |
| Student | `GET /progress` · `POST /activity/ping` · `GET /flashcards/due` · `POST /flashcards/review` · `GET/POST /student/plan…` · `GET/POST /student/concept-map…` · `GET /leaderboard` · `GET /badges` · challenges |
| Teacher | `GET /teacher/overview` · `/teacher/alerts` · `/teacher/students` · `/teacher/submissions` · `/teacher/tests/pending` · `POST /teacher/tests/generate-class` · `/teacher/doubt-clusters` · `/teacher/activity-heatmap` |
| Parent | `GET /parent/report` · `POST /parent/goal` · `POST /parent/report/send` · `/parent/activity-heatmap` |
| Admin | `GET /admin/analytics` · `GET /admin/audit-logs` |

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

`institutes` · `students` · `concepts` · `concept_relationships` · `weakness_map` ·
`doubt_logs` · `tests` · `alerts` · `parent_reports` · `episodic_memories` ·
`flashcards` · `study_plans` · `doubt_clusters` · `activity_log` · `badges` ·
`challenges` · `audit_logs`

---

## Environment variables

See [`../.env.example`](../.env.example) for the full list. Essentials:

```
GROQ_API_KEY / GEMINI_API_KEY / OPENROUTER_API_KEY   # LLM fallback chain
SUPABASE_URL / SUPABASE_KEY / SUPABASE_SERVICE_KEY    # Auth + DB (service key = backend)
QDRANT_URL / QDRANT_API_KEY                           # Vector store
RESEND_API_KEY / TWILIO_*                             # Email + WhatsApp
TAVILY_API_KEY                                        # Web-search RAG fallback
```

---

## Deployment

Containerised for **HuggingFace Spaces** (Docker) — see [`../Dockerfile`](../Dockerfile),
which listens on port **7860** and sets the `/tmp` model-cache env vars Spaces requires.
The frontend deploys separately to Vercel from the
[UI repo](https://github.com/SanjayRawat0570/coaching_inst_ui).
