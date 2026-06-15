# smrt_chng_platform

AI-powered coaching institute management platform for India (JEE / NEET / competitive exams).
8 LangGraph agents handle each student individually — doubts, personalized tests, progress
tracking, at-risk detection, parent reports, answer evaluation, and AIR rank prediction.

## Stack (100% free tier)

- **LLMs:** Groq (llama-3.3-70b) → Gemini 2.5 Flash → OpenRouter fallback
- **Auth + DB:** Supabase (PostgreSQL + pgvector + Auth + RLS)
- **Vector DB:** Qdrant Cloud (RAG content — NCERT, PYQs, institute notes)
- **Orchestration:** LangGraph (Supervisor+Worker, Parallel, HITL, Streaming)
- **RAG:** 6 patterns — Agentic, HyDE, RAPTOR, CRAG, Web fallback, CrossEncoder rerank
- **Backend:** FastAPI + APScheduler on HuggingFace Spaces (Docker)
- **Frontend:** Next.js 14 + Expo React Native on Vercel

## Setup

```bash
cp .env.example .env        # fill in your free API keys
pip install -r backend/requirements.txt
# Run schema.sql once in the Supabase SQL editor
uvicorn main:app --reload --port 8000   # from inside backend/
```
