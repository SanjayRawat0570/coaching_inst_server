# smrt_chng_platform

AI-powered coaching institute management platform for India (JEE / NEET / competitive exams).
8 LangGraph agents handle each student individually — doubts, personalized tests, progress
tracking, at-risk detection, parent reports, answer evaluation, and AIR rank prediction.

## Stack (free tiers; backend on Railway)

- **LLMs:** Groq → Gemini 2.5 Flash → OpenRouter, failing over per call with a timeout and
  a circuit breaker (`backend/graph/llm.py`); models set by `GROQ_MODEL` / `GEMINI_MODEL` /
  `OPENROUTER_MODEL`
- **Auth + DB + files:** Supabase (PostgreSQL + pgvector + Auth + RLS + Storage)
- **RAG:** [RAG_SERVER](https://github.com/SanjayRawat0570/RAG_SERVER) — the only RAG: a
  separate hosted, multi-tenant service (hybrid search, citations, semantic cache,
  conversation memory) used over HTTP; teachers upload notes / NCERT / PYQs on the
  Study Material page. See [backend/README.md](backend/README.md#rag-rag_server-is-the-only-retrieval-rag).
- **Orchestration:** LangGraph (Supervisor+Worker, Parallel, HITL, Streaming)
- **Backend:** FastAPI + APScheduler on Railway (Docker)
- **Frontend:** Next.js 14 (Pages Router, TypeScript, Tailwind, SWR) on Vercel

## Repositories

| Repo | What | Deploys to |
|------|------|------------|
| [coaching_inst_server](https://github.com/SanjayRawat0570/coaching_inst_server) (this repo, git remote `origin`) | Backend (`backend/`) + a copy of the frontend (`frontend/`) | Railway |
| [coaching_inst_ui](https://github.com/SanjayRawat0570/coaching_inst_ui) (git remote `ui`) | The frontend only, at the repo root | Vercel |

`frontend/` here is the source of truth. To publish it to the UI repo as a new commit on
top of a UI branch (keeps that repo's history). Push to a branch first — Vercel builds a
preview — and merge it into the UI repo's `main` only after the backend it needs is live:

```bash
git fetch ui
BR=rag-server-integration   # or main, once the backend is deployed
git push ui "$(git commit-tree HEAD:frontend -p ui/$BR -m 'Sync frontend from coaching_inst_server')":refs/heads/$BR
```

## Setup

```bash
cp backend/.env.example backend/.env   # fill in your free API keys + RAG_SERVER_URL / key
pip install -r backend/requirements.txt
# Run backend/schema.sql once in the Supabase SQL editor (existing DB: backend/migrations/*.sql)
# SCHEDULER_ENABLED=0 for a local run against the real database (the jobs send emails)
uvicorn main:app --reload --port 8000   # from inside backend/

cd frontend && npm install && npm run dev   # http://localhost:3000 (frontend/.env.local)
```

Tests and measurements (from `backend/`): `python -m pytest -q`,
`python -m scripts.bench --runs 10` (endpoint latency + queries per request),
`python -m scripts.loadtest --users 50` (concurrent students). Deployment:
[DEPLOYMENT.md](DEPLOYMENT.md). Performance work and numbers:
[PERFORMANCE_UPGRADE.md](PERFORMANCE_UPGRADE.md).
