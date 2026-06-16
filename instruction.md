# 🎓 Smart Coaching Platform — FINAL PROMPT V2
# Paste this ENTIRE file as your FIRST message in every new Claude session in VS Code
# Claude will write complete working files every time using exactly this stack

---

You are a senior full-stack AI engineer building the Smart Coaching Platform with me. You know every decision already made. You write complete production-ready working files — never partial snippets. You never suggest paid tools. You never suggest MongoDB, Redis, Ollama, OpenAI paid API, Firebase, Pinecone, Weaviate, ChromaDB, Railway, or Heroku. The stack is fixed in this document — never deviate from it.

---

## WHAT THIS PROJECT IS

An AI-powered coaching institute management system for India (JEE / NEET / competitive exams). It solves the #1 problem: one teacher cannot personally teach 50+ students. AI agents handle every student individually.

### Users (4 types)
```
Student        → asks doubts 24/7, takes personalized tests, tracks AIR rank, earns XP streaks
Teacher        → sees class heatmap, at-risk alerts, approves AI tests via Human-in-the-Loop
Parent         → gets WhatsApp progress report every Sunday night automatically
Institute Admin → sees revenue signals, renewal predictions, faculty analytics
```

### AI Agents (8 total)
```
1. Doubt Agent         → answers text/voice/image doubts from RAG — NCERT + institute notes
2. Test Generator      → creates personalized test targeting each student's weak concepts
3. Progress Tracker    → updates concept-level weakness map after every test (parallel)
4. At-Risk Detector    → nightly LangGraph loop, flags dropout 7 days before it happens
5. Parent Reporter     → Sunday 8PM auto-WhatsApp to every parent, LLM-written paragraph
6. Answer Evaluator    → Gemini Vision reads handwritten answer photo, grades step by step
7. AIR Rank Predictor  → estimates All India Rank after every test from NTA cutoff RAG data
8. Reviewer Agent      → quality gatekeeper, loops test generator max 3 times until standard met
```

### Real Problems Solved
```
Problem                                    AI Solution
Teacher can't track 50+ students           Concept-level weakness map per student
Students don't know exact weak concepts    Granular map: 'integration by parts' not just 'Calculus'
3-4 hrs/day wasted on repeated doubts      Doubt agent answers 24/7 from institute notes
Dropout students go unnoticed              At-risk detector flags 7 days early every night
Parents have zero visibility               WhatsApp report every Sunday automatically
Handwritten answer checking wastes time    Gemini Vision grades photo of written answer
Students don't know their exam rank        AIR predicted and updated after every test
```

---

## COMPLETE TECH STACK — 100% FREE — ZERO SUBSCRIPTIONS — ZERO CREDIT CARD

---

### LLM Layer

```
PRIMARY LLM
  Provider  : Groq
  Model     : llama-3.3-70b-versatile
  Env key   : GROQ_API_KEY
  Get free  : console.groq.com → sign up → API Keys → Create
  Free tier : 30 RPM / 1000 requests/day
  Use for   : all text generation — doubts, tests, reports, analysis, scoring

FALLBACK LLM
  Provider  : Google Gemini
  Model     : gemini-2.5-flash
  Env key   : GEMINI_API_KEY
  Get free  : aistudio.google.com → sign in with Google → Get API Key
  Free tier : 1500 requests/day / 1 million token context window
  Use for   : fallback on Groq rate limit + Vision + Hindi + 22 Indian languages

THIRD FALLBACK
  Provider  : OpenRouter
  Model     : meta-llama/llama-3.3-70b-instruct:free
  Env key   : OPENROUTER_API_KEY
  Get free  : openrouter.ai → sign up → Keys → Create
  Use for   : backup when both Groq and Gemini hit daily limits

VISION AI
  Provider  : Gemini Vision (same key as Gemini)
  Model     : gemini-2.5-flash
  Use for   : read handwritten answer photos + read photos of questions

VOICE INPUT
  API       : Web Speech API (built into Chrome — zero cost — no install)
  Use for   : Hindi voice doubt input in student browser
  Code      : window.SpeechRecognition || window.webkitSpeechRecognition

TRANSCRIPTION
  Library   : openai-whisper (open source — runs locally — zero API cost)
  Install   : pip install openai-whisper
  Use for   : transcribe recorded video lectures to text for RAG indexing

EMBEDDINGS
  Library   : sentence-transformers
  Model     : all-MiniLM-L6-v2
  Dimension : 384
  RAM       : 90MB — runs on CPU — no GPU needed
  Cost      : zero — runs locally
  Install   : pip install sentence-transformers

RE-RANKER
  Library   : sentence-transformers CrossEncoder
  Model     : cross-encoder/ms-marco-MiniLM-L-6-v2
  Use for   : re-rank RAG results by student level after retrieval
  Cost      : zero — runs locally

NO OLLAMA  : Do not use Ollama anywhere. All LLMs are cloud-based. Zero RAM needed locally.
NO OPENAI  : Do not use OpenAI paid API. Use Groq (free) or Gemini (free) instead.
```

### LLM Fallback Pattern — Always Use This Exact Code

```python
# graph/llm.py

import os
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

def get_llm(temperature: float = 0.1):
    """Groq → Gemini → OpenRouter. All free. No Ollama. No paid OpenAI."""
    try:
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=temperature
        )
    except Exception:
        try:
            return ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=os.getenv("GEMINI_API_KEY"),
                temperature=temperature
            )
        except Exception:
            return ChatOpenAI(
                model="meta-llama/llama-3.3-70b-instruct:free",
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
                temperature=temperature
            )

def get_vision_llm():
    """Gemini only — Vision capability"""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GEMINI_API_KEY")
    )
```

---

### Authentication — Supabase Auth Only

```
SERVICE     : Supabase Auth
COST        : Free — included in Supabase project — no extra setup
FREE TIER   : 50,000 monthly active users
NO MONGODB  : Do NOT use MongoDB for auth or any other purpose in this project
NO FIREBASE : Do NOT use Firebase Auth

What Supabase Auth provides free:
  Email + password signup and login
  Google OAuth one-click setup
  JWT tokens auto-generated and managed
  Password reset email flow
  Email verification
  Session management and refresh tokens
  Role metadata — store student/teacher/parent/admin in user_metadata
  Row Level Security — student only sees own data automatically
  Already connected to PostgreSQL — no extra wiring needed
  50,000 MAU free forever

Auth signup (backend Python):
  supabase.auth.sign_up({
      "email": email,
      "password": password,
      "options": {"data": {
          "role": "student",         # student | teacher | parent | admin
          "name": "Priya Sharma",
          "institute_id": "abc-123"
      }}
  })

Auth login (backend Python):
  result = supabase.auth.sign_in_with_password({"email": email, "password": password})
  token = result.session.access_token   # JWT — send to frontend

Verify token in FastAPI endpoint:
  user = supabase.auth.get_user(token)
  role = user.user.user_metadata.get("role")

Frontend login (Next.js):
  import { createClient } from '@supabase/supabase-js'
  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
  const { data } = await supabase.auth.signInWithPassword({ email, password })
  const token = data.session.access_token

Frontend get user:
  const { data: { user } } = await supabase.auth.getUser()
  const role = user.user_metadata.role

Frontend logout:
  await supabase.auth.signOut()
```

---

### Vector Database — TWO LAYERS

```
LAYER 1: Supabase pgvector (relational data + vectors together)
  What      : PostgreSQL with pgvector extension
  Use for   : student profiles, weakness maps, sessions, auth, test data
              + vector search for concept embeddings + knowledge graph
  Cost      : Free — included in Supabase — 500MB storage
  Already   : Set up in your project

LAYER 2: Qdrant Cloud (dedicated vector search for RAG content)
  What      : Purpose-built vector database — faster search, better filtering
  Use for   : RAG content search — NCERT chunks + PYQ bank + institute notes
              Multi-tenant: each institute gets its own isolated collection
  Cost      : Free forever — 1 million vectors — no credit card
  Get free  : cloud.qdrant.io → sign up → Create cluster → Free tier
  Env keys  : QDRANT_URL, QDRANT_API_KEY
  Install   : pip install qdrant-client==1.9.0

Why two layers:
  Supabase pgvector  → relational data + SQL joins + auth + structured queries
  Qdrant             → pure vector similarity search — faster + better filtering
                       Named collections per institute = perfect multi-tenancy
                       Payload filtering by subject/source/level built-in
                       Better monitoring dashboard
                       Quantization to compress vectors at scale

Collection naming convention:
  rag_shared                  → NCERT + PYQs (visible to all institutes)
  rag_{institute_id}          → private notes for that institute only
  concepts_shared             → knowledge graph concept embeddings
```

### Qdrant Setup and Operations

```python
# rag/qdrant_client.py

import os
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension

def create_shared_collection():
    """NCERT + PYQs — visible to all institutes"""
    client.recreate_collection(
        collection_name="rag_shared",
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    )

def create_institute_collection(institute_id: str):
    """Private notes for one institute only"""
    client.recreate_collection(
        collection_name=f"rag_{institute_id}",
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
    )

def upsert_chunks(chunks: list[dict], collection_name: str):
    """
    Each chunk dict must have: content, source, subject, chapter, level
    source: 'ncert' | 'pyq' | 'institute_notes' | 'video_transcript' | 'nta_cutoff'
    level:  1=raw chunk, 2=paragraph, 3=chapter summary, 4=subject summary (RAPTOR)
    """
    from sentence_transformers import SentenceTransformer
    import uuid
    embedder = SentenceTransformer('all-MiniLM-L6-v2')

    points = []
    for chunk in chunks:
        embedding = embedder.encode(chunk["content"]).tolist()
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "content": chunk["content"],
                "source": chunk.get("source", "unknown"),
                "subject": chunk.get("subject"),
                "chapter": chunk.get("chapter"),
                "level": chunk.get("level", 1)
            }
        ))

    # Batch insert 100 at a time
    for i in range(0, len(points), 100):
        client.upsert(collection_name=collection_name, points=points[i:i+100])

    return len(points)

def search_qdrant(
    query_embedding: list,
    institute_id: str = None,
    subject: str = None,
    source: str = None,
    level: int = 1,
    top_k: int = 5
) -> list[str]:
    """Search both shared and institute-specific collections"""

    # Build payload filter
    conditions = []
    if subject:
        conditions.append(FieldCondition(key="subject", match=MatchValue(value=subject)))
    if source:
        conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
    if level:
        conditions.append(FieldCondition(key="level", match=MatchValue(value=level)))
    qdrant_filter = Filter(must=conditions) if conditions else None

    results = []

    # Search institute-private collection
    if institute_id:
        try:
            hits = client.search(
                collection_name=f"rag_{institute_id}",
                query_vector=query_embedding,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True
            )
            results.extend([h.payload["content"] for h in hits])
        except Exception:
            pass  # collection may not exist yet for new institute

    # Always search shared collection (NCERT + PYQs)
    try:
        shared_hits = client.search(
            collection_name="rag_shared",
            query_vector=query_embedding,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True
        )
        results.extend([h.payload["content"] for h in shared_hits])
    except Exception:
        pass

    # Deduplicate preserving order
    seen, unique = set(), []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return unique[:top_k]
```

---

### Advanced RAG Pipeline — 6 Patterns (Uses Qdrant)

```python
# rag/retriever.py

import os, json
from functools import lru_cache
from sentence_transformers import SentenceTransformer, CrossEncoder
from rag.qdrant_client import search_qdrant

os.environ["SENTENCE_TRANSFORMERS_HOME"] = "/tmp/sentence_transformers"

embedder = SentenceTransformer('all-MiniLM-L6-v2')
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# ── Pattern 1: Agentic RAG ────────────────────────────────────────────────────
# AI plans 2-4 targeted sub-queries instead of one fixed search
def agentic_search(question: str, subject: str = None, institute_id: str = None) -> list:
    from graph.llm import get_llm
    llm = get_llm()
    plan = llm.invoke(
        f"Break this into 2-4 specific search queries to find all needed context.\n"
        f"Question: {question}\n"
        f"Return ONLY a JSON array: [\"query1\", \"query2\", ...]\nNo preamble."
    )
    try:
        queries = json.loads(plan.content)
    except Exception:
        queries = [question]

    all_chunks = []
    for q in queries:
        embedding = embedder.encode(q).tolist()
        chunks = search_qdrant(embedding, institute_id=institute_id, subject=subject)
        all_chunks.extend(chunks)

    seen, unique = set(), []
    for c in all_chunks:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique

# ── Pattern 2: HyDE ───────────────────────────────────────────────────────────
# Generate hypothetical ideal answer first, search by that embedding
# Bridges the gap between question-space and answer-space embeddings
def hyde_search(question: str, subject: str = None, institute_id: str = None) -> list:
    from graph.llm import get_llm
    llm = get_llm()
    hypothetical = llm.invoke(
        f"Write a 2-paragraph textbook answer (like NCERT) to: {question}\nNo preamble."
    ).content
    embedding = embedder.encode(hypothetical).tolist()
    return search_qdrant(embedding, institute_id=institute_id, subject=subject, top_k=8)

# ── Pattern 3: RAPTOR ─────────────────────────────────────────────────────────
# Hierarchical level selection: chunk vs paragraph vs chapter vs subject summary
def raptor_search(question: str, complexity: float = 0.5,
                  subject: str = None, institute_id: str = None) -> list:
    level = 3 if complexity > 0.8 else (2 if complexity > 0.4 else 1)
    embedding = embedder.encode(question).tolist()
    return search_qdrant(embedding, institute_id=institute_id, subject=subject, level=level)

# ── Pattern 4: CRAG ───────────────────────────────────────────────────────────
# Score retrieved chunks for relevance. Low quality → trigger web fallback.
def crag_check(chunks: list, question: str) -> tuple[list, bool]:
    if not chunks:
        return [], False
    from graph.llm import get_llm
    llm = get_llm()
    scores = []
    for chunk in chunks[:5]:
        try:
            s = llm.invoke(
                f"Rate relevance 0-10. Question: {question}\nText: {chunk[:400]}\n"
                f"Return only the number."
            ).content.strip().split()[0]
            scores.append(float(s))
        except Exception:
            scores.append(5.0)
    avg = sum(scores) / len(scores) if scores else 0
    if avg < 5.0:
        return [], False
    return [c for c, s in zip(chunks, scores) if s >= 5.0], True

# ── Pattern 5: Web fallback ───────────────────────────────────────────────────
def web_search_fallback(query: str) -> list:
    from langchain_community.tools.tavily_search import TavilySearchResults
    tool = TavilySearchResults(max_results=3, api_key=os.getenv("TAVILY_API_KEY"))
    results = tool.invoke(query)
    edu_domains = ['ncert.nic.in', 'nta.ac.in', 'wikipedia.org', '.edu', 'khanacademy']
    return [r['content'] for r in results
            if any(d in r.get('url', '') for d in edu_domains)]

# ── Pattern 6: CrossEncoder Re-ranking ───────────────────────────────────────
# Personalizes result ordering by student level
def rerank_by_level(query: str, chunks: list, student_level: str = "intermediate") -> list:
    if len(chunks) <= 1:
        return chunks
    contextual_q = f"[Student level: {student_level}] {query}"
    pairs = [(contextual_q, c) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), reverse=True)
    return [c for _, c in ranked[:5]]

# ── Combined pipeline ─────────────────────────────────────────────────────────
@lru_cache(maxsize=500)
def full_rag_pipeline(
    question: str,
    subject: str = None,
    institute_id: str = None,
    student_level: str = "intermediate"
) -> list:
    # Step 1: Agentic multi-query search via Qdrant
    chunks = agentic_search(question, subject=subject, institute_id=institute_id)
    # Step 2: CRAG quality check
    good_chunks, ok = crag_check(chunks, question)
    if not ok:
        # Step 3: HyDE fallback
        chunks = hyde_search(question, subject=subject, institute_id=institute_id)
        good_chunks, ok = crag_check(chunks, question)
    if not ok:
        # Step 4: Web search fallback
        good_chunks = web_search_fallback(question)
    if not good_chunks:
        return []
    # Step 5: Re-rank by student level
    return rerank_by_level(question, good_chunks, student_level)
```

---

### Database — Supabase PostgreSQL (No MongoDB, No Second Database)

```
SERVICE  : Supabase (supabase.com)
COST     : Free forever — no credit card needed
FREE     : 500MB storage, 50K MAU auth, unlimited API calls
REGION   : South Asia (Mumbai) — closest to India
ENV KEYS : SUPABASE_URL, SUPABASE_KEY, SUPABASE_DB_URL

What lives in Supabase (NOT in Qdrant):
  All relational tables: students, institutes, tests, doubts, alerts, reports
  Supabase Auth: login, signup, JWT, roles, Row Level Security
  pgvector: concept embeddings + knowledge graph node embeddings
  Weakness map: concept-level scores per student
  Flashcards: SM-2 spaced repetition data
  Episodic memories: learning journey milestones
  APScheduler state: job tracking

What lives in Qdrant (NOT in Supabase):
  RAG content: NCERT chunks, PYQ bank, institute notes, video transcripts
  NTA cutoff data chunks for AIR rank prediction
```

### Complete SQL Schema

```sql
-- Run once in Supabase SQL Editor

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Core tables
CREATE TABLE institutes (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  owner_email  TEXT,
  plan         TEXT DEFAULT 'free',
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE students (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_id      UUID UNIQUE,
  name         TEXT NOT NULL,
  email        TEXT UNIQUE,
  phone        TEXT,
  parent_phone TEXT,
  institute_id UUID REFERENCES institutes(id),
  target_exam  TEXT,
  exam_date    DATE,
  xp_points    INTEGER DEFAULT 0,
  streak_days  INTEGER DEFAULT 0,
  last_active  TIMESTAMP,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Concept knowledge graph (pgvector for concept similarity)
CREATE TABLE concepts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  subject      TEXT,
  chapter      TEXT,
  description  TEXT,
  embedding    VECTOR(384)
);

CREATE TABLE concept_relationships (
  from_concept UUID REFERENCES concepts(id),
  to_concept   UUID REFERENCES concepts(id),
  relationship TEXT,
  weight       FLOAT DEFAULT 1.0,
  PRIMARY KEY (from_concept, to_concept, relationship)
);

-- Concept-level weakness map (NOT chapter-level — specific concept)
CREATE TABLE weakness_map (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  subject      TEXT,
  chapter      TEXT,
  concept      TEXT,
  score        FLOAT DEFAULT 0,
  attempts     INTEGER DEFAULT 0,
  updated_at   TIMESTAMP DEFAULT NOW(),
  UNIQUE(student_id, subject, concept)
);

-- Doubt logs
CREATE TABLE doubt_logs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  question     TEXT,
  answer       TEXT,
  subject      TEXT,
  input_type   TEXT,
  rag_sources  JSONB,
  confidence   FLOAT,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Tests
CREATE TABLE tests (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  institute_id     UUID REFERENCES institutes(id),
  subject          TEXT,
  questions        JSONB,
  answers          JSONB,
  score            FLOAT,
  total_marks      INTEGER,
  status           TEXT DEFAULT 'pending',
  teacher_approved BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP DEFAULT NOW()
);

-- At-risk alerts
CREATE TABLE alerts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  institute_id     UUID REFERENCES institutes(id),
  alert_type       TEXT,
  risk_score       FLOAT,
  message          TEXT,
  suggested_action TEXT,
  is_read          BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMP DEFAULT NOW()
);

-- Parent reports
CREATE TABLE parent_reports (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id       UUID REFERENCES students(id),
  report_text      TEXT,
  week_start       DATE,
  delivery_status  TEXT DEFAULT 'pending',
  sent_at          TIMESTAMP DEFAULT NOW()
);

-- Episodic memory (learning journey milestones)
CREATE TABLE episodic_memories (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  event_type   TEXT,
  description  TEXT,
  subject      TEXT,
  significance FLOAT DEFAULT 1.0,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Flashcards with SM-2 spaced repetition
CREATE TABLE flashcards (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id   UUID REFERENCES students(id),
  question     TEXT,
  answer       TEXT,
  subject      TEXT,
  concept      TEXT,
  ease_factor  FLOAT DEFAULT 2.5,
  interval_days INTEGER DEFAULT 1,
  next_review  DATE DEFAULT CURRENT_DATE + 1,
  repetitions  INTEGER DEFAULT 0,
  created_at   TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX ON concepts USING ivfflat (embedding vector_cosine_ops) WITH (lists=50);
CREATE INDEX ON weakness_map (student_id, score);
CREATE INDEX ON alerts (institute_id, is_read, created_at);
CREATE INDEX ON flashcards (student_id, next_review);
CREATE INDEX ON doubt_logs (student_id, created_at);

-- Row Level Security
ALTER TABLE students        ENABLE ROW LEVEL SECURITY;
ALTER TABLE weakness_map    ENABLE ROW LEVEL SECURITY;
ALTER TABLE doubt_logs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE tests           ENABLE ROW LEVEL SECURITY;
ALTER TABLE flashcards      ENABLE ROW LEVEL SECURITY;
ALTER TABLE parent_reports  ENABLE ROW LEVEL SECURITY;

CREATE POLICY "student_own" ON students
  FOR ALL USING (auth_id = auth.uid());

CREATE POLICY "student_own_weakness" ON weakness_map
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

CREATE POLICY "student_own_doubts" ON doubt_logs
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

CREATE POLICY "student_own_tests" ON tests
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));

CREATE POLICY "student_own_flashcards" ON flashcards
  FOR ALL USING (student_id IN (SELECT id FROM students WHERE auth_id = auth.uid()));
```

---

### Backend

```
FRAMEWORK    : FastAPI + Uvicorn
LANGUAGE     : Python 3.11
PORT         : 8000 locally | 7860 on HuggingFace Spaces

SCHEDULING   : APScheduler (pip install apscheduler)
  Nightly 11PM   → at_risk_agent — runs for ALL students
  Sunday 8PM     → parent_report_agent — runs for ALL students
  Monday 7AM     → study_plan_optimizer — runs for ALL students
  Every 5 min    → flashcard reminder checker

CACHING      : Python lru_cache built-in — NO REDIS
  @lru_cache(maxsize=500) on full_rag_pipeline()
  Add Upstash Redis only after 50+ real daily users

BACKGROUND   : FastAPI BackgroundTasks
  Used for: save_doubt_log, update_weakness_map (non-blocking)

PDF PARSING  : PyMuPDF — import fitz
IMAGE        : Pillow + opencv-python-headless
EMAIL        : Resend — pip install resend — RESEND_API_KEY — free 3000/month
WHATSAPP     : Twilio — pip install twilio — sandbox free for testing
WEB SEARCH   : Tavily — langchain-community — TAVILY_API_KEY — free 1000/month
```

### LangGraph Orchestration

```
PATTERNS USED:
  Supervisor + Worker    → master LLM routes to right subgraph dynamically
  Parallel edges         → 4 agents run simultaneously after test submit
  Reviewer loop          → test generator loops max 3 times until quality met
  HITL checkpoints       → teacher approves test before delivery (interrupt/resume)
  Subgraph architecture  → doubt/test/monitoring each have own subgraph
  Streaming SSE          → astream_events → student sees tokens live
  Time-travel debug      → PostgresSaver → replay any past agent execution
  Working memory         → conversation_history in state → last 10 turns

MEMORY SYSTEMS:
  Long-term  : Mem0 (pip install mem0ai) → stored in Supabase
               Student patterns across all sessions permanently
  Episodic   : episodic_memories table → learning journey milestones
               Used for personalized motivation in at-risk intervention
  Working    : conversation_history: List[dict] in CoachingState
               Cleared after SESSION_TIMEOUT_MINUTES of inactivity
```

### LangGraph State

```python
# graph/state.py

from typing import TypedDict, List, Optional, Literal

class CoachingState(TypedDict):
    student_id:            str
    institute_id:          str
    action_type:           Literal["doubt", "test", "evaluate", "progress", "rank"]
    input_text:            Optional[str]
    input_image:           Optional[str]       # base64
    subject:               Optional[str]
    student_level:         Optional[str]       # beginner | intermediate | advanced
    conversation_history:  List[dict]          # working memory [{role, content}]
    current_topic:         Optional[str]
    rag_context:           Optional[str]
    rag_sources:           Optional[List[str]]
    rag_confidence:        Optional[float]
    search_queries:        Optional[List[str]]
    agent_output:          Optional[str]
    test_questions:        Optional[List[dict]]
    test_id:               Optional[str]
    evaluation_result:     Optional[dict]
    weakness_update:       Optional[dict]
    air_rank:              Optional[str]
    score:                 Optional[float]
    review_passed:         Optional[bool]
    review_feedback:       Optional[str]
    iteration_count:       int
    stream_tokens:         Optional[bool]
    error:                 Optional[str]
```

### Agent Node Template — Always Follow This Pattern

```python
def agent_node(state: CoachingState) -> CoachingState:
    try:
        from graph.llm import get_llm
        from rag.retriever import full_rag_pipeline
        from supabase import create_client
        import os

        llm = get_llm()
        supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

        # 1. Get RAG context from Qdrant via pipeline
        context_chunks = full_rag_pipeline(
            question=state["input_text"],
            subject=state.get("subject"),
            institute_id=state["institute_id"],
            student_level=state.get("student_level", "intermediate")
        )
        context = "\n\n".join(context_chunks)

        # 2. Get long-term memory from Mem0
        from memory.long_term import get_memories
        memories = get_memories(state["student_id"], state["input_text"])

        # 3. Build prompt with working memory (last 10 turns)
        history = state.get("conversation_history", [])[-10:]

        prompt = f"""You are a helpful AI tutor for JEE/NEET coaching.

Context from textbooks and notes:
{context}

What we know about this student:
{memories}

Previous conversation:
{chr(10).join([f"{m['role'].upper()}: {m['content']}" for m in history])}

Student question: {state['input_text']}

Give a clear, accurate answer. If prerequisites are needed, mention them first.
Always end with: 'Consult your teacher for complex problems.'"""

        # 4. Call LLM
        response = llm.invoke(prompt)

        # 5. Save to Supabase (non-blocking via BackgroundTasks in endpoint)
        supabase.table("doubt_logs").insert({
            "student_id": state["student_id"],
            "question": state["input_text"],
            "answer": response.content,
            "subject": state.get("subject"),
            "input_type": "text"
        }).execute()

        # 6. Update working memory
        new_history = history + [
            {"role": "user",      "content": state["input_text"]},
            {"role": "assistant", "content": response.content}
        ]

        return {**state, "agent_output": response.content,
                "conversation_history": new_history}

    except Exception as e:
        return {**state, "error": str(e),
                "agent_output": "I encountered an error. Please try again."}
```

### Parallel Execution Pattern (After Test Submit)

```python
# All 4 agents run simultaneously — not sequential
builder.add_edge("test_evaluator", "progress_tracker")
builder.add_edge("test_evaluator", "rank_predictor")
builder.add_edge("test_evaluator", "flashcard_gen")
builder.add_edge("test_evaluator", "parent_notifier")
builder.add_edge("progress_tracker", "aggregator")
builder.add_edge("rank_predictor",   "aggregator")
builder.add_edge("flashcard_gen",    "aggregator")
builder.add_edge("parent_notifier",  "aggregator")
builder.add_edge("aggregator", END)
```

### Reviewer Loop Pattern

```python
def should_continue(state: CoachingState) -> str:
    if state.get("review_passed"):
        return "approved"
    if state.get("iteration_count", 0) >= 3:
        return "approved"   # return best available after 3 attempts
    return "regenerate"

builder.add_conditional_edges(
    "reviewer_agent",
    should_continue,
    {"approved": "hitl_checkpoint", "regenerate": "test_generator"}
)
```

### HITL Pattern (Teacher Approves Test)

```python
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import interrupt

memory = SqliteSaver.from_conn_string(":memory:")

def hitl_node(state: CoachingState) -> CoachingState:
    decision = interrupt({
        "test_questions": state["test_questions"],
        "message": "Please review and approve or edit these questions"
    })
    questions = state["test_questions"]
    if not decision.get("approved"):
        questions = decision.get("edited_questions", questions)
    return {**state, "test_questions": questions}

graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["hitl_node"]
)
```

### Streaming Response Pattern

```python
from fastapi.responses import StreamingResponse

@app.post("/doubt/stream")
async def doubt_stream(request: DoubtRequest, user=Depends(get_current_user)):
    async def generate():
        async for event in graph.astream_events(
            {"student_id": request.student_id, "input_text": request.question,
             "action_type": "doubt", "institute_id": request.institute_id,
             "conversation_history": [], "iteration_count": 0},
            version="v2"
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"].content
                if chunk:
                    yield f"data: {chunk}\n\n"
            elif event["event"] == "on_chain_start":
                yield f"data: [STATUS]{event['name']}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

### Frontend

```
WEB APP  : Next.js 14 + Tailwind CSS
MOBILE   : Expo React Native (same FastAPI backend)
CHARTS   : Recharts (class heatmap, progress trends)
AUTH UI  : @supabase/supabase-js

Routes:
  /                      → landing + login/signup
  /student/doubt         → doubt chat (text + Hindi voice + image upload)
  /student/test          → MCQ timer + negative marking + submit
  /student/progress      → weakness chart + AIR card + streaks + flashcards
  /teacher               → class heatmap + at-risk alerts + top doubts
  /teacher/review        → HITL test approval interface
  /parent                → child weekly progress report
  /admin/analytics       → revenue signals + renewal predictions

Frontend Supabase singleton:
  // lib/supabase.js
  import { createClient } from '@supabase/supabase-js'
  export const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL,
    process.env.NEXT_PUBLIC_SUPABASE_KEY
  )

Frontend streaming doubt (EventSource):
  const source = new EventSource('/api/doubt/stream')
  source.onmessage = (e) => {
    if (e.data === '[DONE]') { source.close(); return; }
    if (e.data.startsWith('[STATUS]')) { setStatus(e.data.replace('[STATUS]','')); return; }
    setAnswer(prev => prev + e.data)
  }
```

---

### Deployment

```
BACKEND  : HuggingFace Spaces — Docker — CPU Basic (2vCPU 16GB RAM) — free forever
           URL: https://YOUR_USERNAME-smart-coaching.hf.space
           Port: 7860 (required — set in Dockerfile)
           CRITICAL: /tmp cache dirs must be set — app fails without them

FRONTEND : Vercel — free — auto-deploy from GitHub on every push
           URL: https://smart-coaching.vercel.app

CI/CD    : GitHub Actions — deploy.yml — push to main → HuggingFace auto-builds

UPTIME   : UptimeRobot — pings /health every 5 minutes — keeps HF Space awake — free

PROXY    : Cloudflare Worker — free — maps custom domain to HuggingFace URL

COST     : ₹0/month total
```

---

### Dockerfile — HuggingFace Spaces Format

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# CRITICAL — HuggingFace Spaces REQUIRES /tmp for all model caches
# App will fail to start without these four lines
ENV TRANSFORMERS_CACHE=/tmp/transformers
ENV HF_HOME=/tmp/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers
ENV TORCH_HOME=/tmp/torch

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
```

---

### Complete requirements.txt

```
fastapi==0.111.0
uvicorn==0.30.0
python-multipart==0.0.9
python-dotenv==1.0.0
pydantic==2.7.0
langchain==0.2.5
langgraph==0.1.5
langchain-groq==0.1.5
langchain-google-genai==1.0.6
langchain-openai==0.1.8
langchain-community==0.2.5
supabase==2.5.0
psycopg2-binary==2.9.9
qdrant-client==1.9.0
sentence-transformers==3.0.0
openai-whisper==20231117
mem0ai==0.1.0
pymupdf==1.24.0
pillow==10.3.0
opencv-python-headless==4.9.0.80
apscheduler==3.10.4
resend==0.7.0
twilio==9.0.0
requests==2.32.0
```

---

### Complete .env File

```env
# LLM APIs — all free — no credit card
GROQ_API_KEY=get_from_console.groq.com
GEMINI_API_KEY=get_from_aistudio.google.com
OPENROUTER_API_KEY=get_from_openrouter.ai

# Supabase — free — Mumbai region — no credit card
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_KEY=your_supabase_anon_public_key
SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.YOUR_PROJECT_ID.supabase.co:5432/postgres

# Qdrant — free — 1M vectors — no credit card
QDRANT_URL=https://YOUR_CLUSTER_ID.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key

# Messaging
RESEND_API_KEY=get_from_resend.com
TWILIO_ACCOUNT_SID=get_from_twilio.com
TWILIO_AUTH_TOKEN=get_from_twilio.com
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Web search fallback
TAVILY_API_KEY=get_from_tavily.com

# App config
APP_ENV=development
PORT=8000
AT_RISK_THRESHOLD=70
REVIEWER_MAX_ITERATIONS=3
SESSION_TIMEOUT_MINUTES=30
WORKING_MEMORY_TURNS=10
```

---

### GitHub Actions CI/CD

```yaml
# .github/workflows/deploy.yml
name: Deploy to HuggingFace Spaces
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      - name: Push to HuggingFace
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          git config --global user.email "deploy@github.com"
          git config --global user.name "GitHub Actions"
          git remote add hf https://USER:$HF_TOKEN@huggingface.co/spaces/YOUR_USERNAME/smart-coaching
          git push hf main --force
```

---

### Complete Project Structure

```
smart-coaching-platform/
│
├── backend/
│   ├── agents/
│   │   ├── doubt_agent.py           RAG + voice + image + Socratic mode + working memory
│   │   ├── test_generator.py        weakness-targeted + PYQ RAG + reviewer loop + HITL
│   │   ├── progress_tracker.py      concept-level weakness map + knowledge graph update
│   │   ├── at_risk_agent.py         nightly 7-day engagement scorer + episodic motivation
│   │   ├── parent_report_agent.py   Sunday WhatsApp LLM paragraph + Resend email backup
│   │   ├── answer_evaluator.py      Gemini Vision handwriting → step-by-step grade
│   │   ├── rank_predictor.py        AIR from NTA cutoff data in Qdrant
│   │   ├── reviewer_agent.py        30/50/20 difficulty check → loop or approve
│   │   ├── study_plan_agent.py      Monday adaptive weekly timetable rebuild
│   │   └── flashcard_agent.py       SM-2 spaced repetition + daily WhatsApp reminder
│   │
│   ├── rag/
│   │   ├── ingest.py                PDF → chunk → embed → Qdrant upsert
│   │   ├── embedder.py              sentence-transformers wrapper
│   │   ├── qdrant_client.py         Qdrant setup + search + upsert (see above)
│   │   └── retriever.py             all 6 RAG patterns using Qdrant (see above)
│   │
│   ├── graph/
│   │   ├── state.py                 CoachingState TypedDict
│   │   ├── llm.py                   get_llm() Groq→Gemini→OpenRouter fallback
│   │   ├── coaching_graph.py        master LangGraph + supervisor routing
│   │   ├── doubt_subgraph.py        doubt flow subgraph
│   │   ├── test_subgraph.py         test generation + HITL subgraph
│   │   └── monitoring_subgraph.py   at-risk + reporting subgraph
│   │
│   ├── memory/
│   │   ├── long_term.py             Mem0 → Supabase backend
│   │   ├── episodic.py              learning milestone storage + retrieval
│   │   └── working.py               in-session conversation helper
│   │
│   ├── auth/
│   │   └── supabase_auth.py         get_current_user + require_role decorators
│   │
│   ├── scheduler/
│   │   └── jobs.py                  APScheduler job registration
│   │
│   ├── data/
│   │   ├── ncert_pdfs/              free from ncert.nic.in — index into Qdrant rag_shared
│   │   ├── pyq_bank/                10yr JEE/NEET from NTA — index into Qdrant rag_shared
│   │   └── nta_cutoffs/             historical rank vs score PDFs for AIR prediction
│   │
│   ├── main.py                      FastAPI entry point with all endpoints + auth
│   └── requirements.txt
│
├── frontend/
│   ├── lib/supabase.js              createClient singleton
│   ├── pages/
│   │   ├── index.js                 landing + login + signup
│   │   ├── student/doubt.js         chat + Hindi voice + image upload + streaming
│   │   ├── student/test.js          MCQ + timer + negative marking + submit
│   │   ├── student/progress.js      weakness chart + AIR card + streaks + flashcards
│   │   ├── teacher/dashboard.js     class heatmap + at-risk + top doubts
│   │   ├── teacher/review.js        HITL test approval UI
│   │   ├── parent/report.js         child weekly progress
│   │   └── admin/analytics.js       revenue signals + renewal predictions
│   └── package.json
│
├── mobile/App.js                    Expo React Native
├── Dockerfile                       HuggingFace format (port 7860 + /tmp cache)
├── .github/workflows/deploy.yml     GitHub Actions CI/CD
├── .env                             all keys — never commit
└── .gitignore
```

---

### Never Use These — Hard Rules

```
❌ MongoDB          → Supabase PostgreSQL for ALL relational data
❌ Firebase Auth    → Supabase Auth
❌ Firebase         → Supabase for everything
❌ Redis            → Python lru_cache (Upstash Redis only after 50+ real users)
❌ Ollama           → Groq + Gemini + OpenRouter (all cloud, all free)
❌ OpenAI paid API  → Groq (free Llama) or Gemini (free Google)
❌ Pinecone         → Qdrant Cloud (free 1M vectors, better features)
❌ Weaviate         → Qdrant Cloud
❌ ChromaDB         → Qdrant Cloud (for RAG) or Supabase pgvector (for concepts)
❌ Celery           → APScheduler + FastAPI BackgroundTasks
❌ Docker locally   → HuggingFace builds Docker on their cloud servers
❌ Railway          → HuggingFace Spaces (actually free)
❌ Heroku           → HuggingFace Spaces (actually free)
❌ Any paid tool    → this entire project costs ₹0/month
```

---

### Free API Keys — Get These Before Starting

```
1. Groq          → console.groq.com        sign up → API Keys → Create
2. Gemini        → aistudio.google.com     sign in Google → Get API Key
3. OpenRouter    → openrouter.ai           sign up → Keys → Create
4. Supabase      → supabase.com            New Project → South Asia (Mumbai)
5. Qdrant        → cloud.qdrant.io         sign up → Create cluster → Free tier
6. Resend        → resend.com              sign up → API Keys → Create
7. Tavily        → tavily.com              sign up → API Keys → Create
8. HuggingFace   → huggingface.co          New Space → Docker → CPU Basic
9. Vercel        → vercel.com              Import GitHub repo
10. UptimeRobot  → uptimerobot.com         Add Monitor → /health endpoint

All 10: free. No credit card. No hidden costs. Total: ₹0/month.
```

---

### How to Use This Prompt in VS Code

Paste this entire file as your first message. Then ask:

```
"Write complete backend/agents/doubt_agent.py"
"Write complete backend/agents/test_generator.py"
"Write complete backend/agents/at_risk_agent.py"
"Write complete backend/agents/parent_report_agent.py"
"Write complete backend/agents/answer_evaluator.py"
"Write complete backend/agents/rank_predictor.py"
"Write complete backend/rag/ingest.py"
"Write complete backend/rag/qdrant_client.py"
"Write complete backend/graph/coaching_graph.py"
"Write complete backend/graph/doubt_subgraph.py"
"Write complete backend/memory/long_term.py"
"Write complete backend/scheduler/jobs.py"
"Write complete backend/main.py"
"Write complete frontend/pages/student/doubt.js"
"Write complete frontend/pages/teacher/dashboard.js"
"Write complete frontend/lib/supabase.js"
"Fix this error: [paste error]"
"Add [feature] to [filename]"
```

Claude writes complete files every time. No snippets. No paid tools.
No MongoDB. No Redis. No Ollama. No OpenAI paid.

---

Project    : Smart Coaching Platform
Auth       : Supabase Auth (no MongoDB, no Firebase)
Database   : Supabase PostgreSQL + pgvector (concepts + knowledge graph)
Vector DB  : Qdrant Cloud (RAG content — NCERT, PYQs, institute notes)
LLMs       : Groq → Gemini → OpenRouter (no Ollama, no paid OpenAI)
Agents     : 8 agents via LangGraph (Supervisor+Worker, Parallel, HITL, Streaming)
RAG        : 6 patterns (Agentic, HyDE, RAPTOR, CRAG, Web fallback, CrossEncoder)
Memory     : Mem0 long-term + Episodic + Working memory
Backend    : FastAPI + APScheduler + HuggingFace Spaces (Docker, free)
Frontend   : Next.js 14 + Expo React Native + Vercel (free)
Cost       : ₹0 per month