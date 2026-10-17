# smrt_chng_platform

AI-powered coaching institute management platform for India (JEE / NEET / competitive exams).
8 LangGraph agents handle each student individually — doubts, personalized tests, progress
tracking, at-risk detection, parent reports, answer evaluation, and AIR rank prediction.

## Stack (100% free tier)

- **LLMs:** Groq (llama-3.3-70b) → Gemini 2.5 Flash → OpenRouter fallback
- **Auth + DB + files:** Supabase (PostgreSQL + pgvector + Auth + RLS + Storage)
- **RAG:** [RAG_SERVER](https://github.com/SanjayRawat0570/RAG_SERVER) — the only RAG: a
  separate hosted, multi-tenant service (hybrid search, citations, semantic cache,
  conversation memory) used over HTTP; teachers upload notes / NCERT / PYQs on the
  Study Material page. See [backend/README.md](backend/README.md#rag-rag_server-is-the-only-retrieval-rag).
- **Orchestration:** LangGraph (Supervisor+Worker, Parallel, HITL, Streaming)
- **Backend:** FastAPI + APScheduler on HuggingFace Spaces (Docker)
- **Frontend:** Next.js 14 + Expo React Native on Vercel

## Setup

```bash
cp backend/.env.example backend/.env   # fill in your free API keys + RAG_SERVER_URL / key
pip install -r backend/requirements.txt
# Run backend/schema.sql once in the Supabase SQL editor (existing DB: backend/migrations/*.sql)
uvicorn main:app --reload --port 8000   # from inside backend/
```
