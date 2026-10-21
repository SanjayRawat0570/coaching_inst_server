# Deployment — Backend on Railway, Frontend on Vercel

Two services, deployed independently. Both redeploy automatically on every push to the
branch they are connected to (no GitHub Actions needed):

```
  Vercel (Next.js)  ──HTTPS──▶  Railway (FastAPI/Docker)  ──▶ Supabase · RAG_SERVER · LLMs · Resend
  NEXT_PUBLIC_API_URL ────────────────^ (Railway public URL)
```

Order matters: **set up Supabase, then the backend**, grab its public URL, then give that
URL to the frontend as `NEXT_PUBLIC_API_URL`.

The **RAG_SERVER** is a separate, already-hosted service. It is used as-is over HTTP —
nothing in this guide changes its code, settings, env vars or deployment.

---

## 1 — Supabase (database + storage)

### New project
Run [`backend/schema.sql`](backend/schema.sql) once in the **SQL editor**. It creates every
table and the Storage bucket below. Nothing is applied automatically.

### Existing project (upgrading this branch)
Run these files from [`backend/migrations/`](backend/migrations/) in the SQL editor,
**in this order** (each is safe to re-run):

| # | File | What it adds |
|---|------|--------------|
| 1 | `2026-10-17_rag_server.sql` | `institutes.rag_tenant`, `institute_secrets` (per-institute RAG_SERVER key) |
| 2 | `2026-10-18_doubt_rag_server.sql` | `doubt_logs` citations, answerable, rag_confidence, conversation_id, rating; index for `content_gap` alerts |
| 3 | `2026-10-18_study_materials.sql` | `study_materials` table + the `study-materials` Storage bucket |
| 4 | `2026-10-18_grounded_agents.sql` | `flashcards.source`, `nta_cutoffs` table (rank predictor) |
| 5 | `2026-10-18_remove_old_rag.sql` | `student_memories` (pgvector long-term memory, replaces Qdrant) |
| 6 | `2026-10-18_insights.sql` | `doubt_clusters.source` (each hot topic's top RAG_SERVER source) |

### Storage bucket
The app stores teachers' original study-material files in a **private** bucket named
**`study-materials`** (50 MB per file). Migration 3 (and `schema.sql`) creates it. If
your project doesn't allow creating buckets from SQL, create it by hand:
**Storage → New bucket → name `study-materials`, Public = off, file size limit 50 MB.**
Don't add any Storage policies — only the backend (service-role key) reads and writes it.

### NTA cutoffs (rank predictor)
The rank predictor reads the `nta_cutoffs` table. Fill it from a CSV with
`python -m scripts.import_nta_cutoffs <file.csv>` (run from `backend/`).

---

## 2 — Backend → Railway

Railway builds the root [`Dockerfile`](Dockerfile), configured by
[`railway.json`](railway.json) (health check `/health`, restart on failure). The Dockerfile
binds uvicorn to Railway's `$PORT` (falls back to 8000).

1. **New Project → Deploy from GitHub repo** → pick this repo
   ([`SanjayRawat0570/coaching_inst_server`](https://github.com/SanjayRawat0570/coaching_inst_server)). Leave **Root Directory** empty.
2. Railway picks up `railway.json` and the `Dockerfile`. No build command needed.
3. **Variables** → set these (Raw Editor makes this fast):

   ```
   # LLMs (fallback chain: Groq -> Gemini -> OpenRouter; at least one required)
   GROQ_API_KEY=...
   GEMINI_API_KEY=...
   OPENROUTER_API_KEY=...

   # Supabase
   SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
   SUPABASE_KEY=your_anon_key
   SUPABASE_SERVICE_KEY=your_service_role_key        # backend only, bypasses RLS
   SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.YOUR_PROJECT_ID.supabase.co:5432/postgres

   # RAG_SERVER (the only RAG)
   RAG_SERVER_URL=https://your-rag-server.up.railway.app   # base URL, without /api/v1
   RAG_SERVER_API_KEY=sk-...                               # default tenant's "member" key
   RAG_SERVER_TENANT=smartcoaching                         # tenant that key belongs to
   RAG_SERVER_TIMEOUT=30

   # Email (parent reports, alerts, reminders)
   RESEND_API_KEY=...

   # App config
   APP_ENV=production
   AT_RISK_THRESHOLD=70
   REVIEWER_MAX_ITERATIONS=3
   SESSION_TIMEOUT_MINUTES=30
   WORKING_MEMORY_TURNS=10
   INACTIVE_ALERT_DAYS=3
   ```
   > Do **not** set `PORT` — Railway provides it.
   >
   > Institutes with their own RAG_SERVER tenant get it from the database instead
   > (`institutes.rag_tenant` + `institute_secrets.rag_api_key`). `RAG_SERVER_API_KEY` /
   > `RAG_SERVER_TENANT` are the default for every account without one.

4. **Delete these old variables** if they are still set — nothing reads them any more:

   ```
   QDRANT_URL
   QDRANT_API_KEY
   TAVILY_API_KEY
   TWILIO_ACCOUNT_SID
   TWILIO_AUTH_TOKEN
   TWILIO_WHATSAPP_FROM
   ```
   (`QDRANT_*` is only used once, locally, by `scripts/migrate_to_rag_server.py` if you
   export the old Qdrant data — never on Railway.)

5. **Settings → Networking → Generate Domain** (already done for the live service:
   `https://coachinginstserver-production.up.railway.app`).
6. Wait for the build, then verify:

   ```
   https://<your-railway-domain>/health   ->  {"status":"ok"}
   https://<your-railway-domain>/docs     ->  interactive API docs
   ```
   As an admin user, `GET /admin/rag/health` should report the RAG_SERVER as
   `configured` and `reachable`.

**Copy the Railway domain — the frontend needs it next.**

### Railway notes
- **Memory:** the MiniLM embedding model (long-term memory, copy detection, doubt
  clustering) loads on first use. Give the service **≥ 1 GB RAM** so it doesn't run out
  of memory on that first request.
- **Model cache:** the model downloads into `/tmp` at runtime (env vars set in the
  Dockerfile). Expect a slow *first* request after each deploy, fast afterwards.
- **Scheduler:** APScheduler runs in-process and starts on boot — no extra service.
- **Email:** notifications are email-only (Resend). Without a verified domain, Resend
  only delivers to the address you signed up with — verify a domain to email parents.

---

## 3 — Frontend → Vercel

1. **Add New… → Project** → import the frontend repo.
   - Using the **dedicated UI repo** ([`coaching_inst_ui`](https://github.com/SanjayRawat0570/coaching_inst_ui)): Root Directory = repo root.
   - Using **this monorepo**: set **Root Directory = `frontend`**.
2. Framework preset: **Next.js** (auto-detected). Build = `next build`, output auto.
3. **Environment Variables** (Production + Preview):

   ```
   NEXT_PUBLIC_SUPABASE_URL = https://YOUR_PROJECT_ID.supabase.co
   NEXT_PUBLIC_SUPABASE_KEY = your_anon_public_key
   NEXT_PUBLIC_API_URL      = https://<your-railway-domain>     # from step 2
   ```
   > `NEXT_PUBLIC_*` are inlined at **build time** — after changing `NEXT_PUBLIC_API_URL`,
   > **redeploy** the frontend. Never put the service-role key or any RAG_SERVER key here.

4. **Deploy.** Open the Vercel URL and log in to confirm the dashboards load data.

---

## 4 — Connect & verify

1. The backend allows all origins (`CORS allow_origins=["*"]`), so the Vercel domain works
   out of the box. To lock it down later, restrict origins in
   [`backend/main.py`](backend/main.py) to your Vercel domain.
2. Smoke test end-to-end:
   - Sign up (student) on the Vercel site → lands on the student dashboard.
   - Ask a doubt → confirms Vercel → Railway → RAG_SERVER/LLM → answer with sources.
   - As a teacher, upload a PDF on **Study Material** → status goes to *ready*.
   - As a teacher, generate + approve a test; as the student, take it.

---

## Quick reference

| | Backend | Frontend |
|---|---------|----------|
| Host | Railway | Vercel |
| Build | Root `Dockerfile` (`railway.json`) | Next.js (auto) |
| Deploys on | push to the connected branch | push to the connected branch |
| Port | `$PORT` (Railway-provided) | n/a |
| Health | `/health` | — |
| Key env | `SUPABASE_*`, `RAG_SERVER_*`, `GROQ_API_KEY`, `RESEND_API_KEY` | `NEXT_PUBLIC_*` |
| Depends on | Supabase, RAG_SERVER | Railway URL via `NEXT_PUBLIC_API_URL` |
