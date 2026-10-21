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

> Databases created from an older `schema.sql` may also lack the `study_plans` table
> (the study-plan feature then fails quietly). Copy its `CREATE TABLE IF NOT EXISTS
> study_plans …` block and index from [`backend/schema.sql`](backend/schema.sql) and run
> it first. To see what's missing, query each table in the SQL editor — PostgREST
> answers `PGRST205` for a table that doesn't exist.

| # | File | What it adds |
|---|------|--------------|
| 1 | `2026-10-17_rag_server.sql` | `institutes.rag_tenant`, `institute_secrets` (per-institute RAG_SERVER key) |
| 2 | `2026-10-18_doubt_rag_server.sql` | `doubt_logs` citations, answerable, rag_confidence, conversation_id, rating; index for `content_gap` alerts |
| 3 | `2026-10-18_study_materials.sql` | `study_materials` table + the `study-materials` Storage bucket |
| 4 | `2026-10-18_grounded_agents.sql` | `flashcards.source`, `nta_cutoffs` table (rank predictor) |
| 5 | `2026-10-18_remove_old_rag.sql` | `student_memories` (pgvector long-term memory, replaces Qdrant) |
| 6 | `2026-10-18_insights.sql` | `doubt_clusters.source` (each hot topic's top RAG_SERVER source) |
| 7 | `2026-10-22_performance_indexes.sql` | Indexes for the dashboard / leaderboard / parent-report queries (adds indexes only, changes no data) |
| 8 | `2026-10-22_jobs.sql` | `jobs` table for background test generation / grading (until it exists, jobs live in memory) |

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

   # Optional (defaults shown)
   LLM_TIMEOUT=20          # seconds per LLM provider before failing over to the next
   GROQ_MODEL=llama-3.3-70b-versatile
   GEMINI_MODEL=gemini-2.5-flash
   OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
   GROQ_FAST_MODEL=        # model for short tasks (labels, checks); empty = GROQ_MODEL
   LLM_CONCURRENCY=3       # LLM calls run side by side at most (free-tier rate limits)
   JOB_WORKERS=2           # background jobs (?job=1) running at once
   RATE_LIMIT_DOUBT=8/60   # doubts per student per 60 s
   RATE_LIMIT_TEST_GEN=5/60  # test generations per user per 60 s
   WARM_START=1            # load the embedding model in the background at boot
   SCHEDULER_ENABLED=1     # 0 = don't run the scheduled jobs in this instance
   SLOW_REQUEST_MS=2000    # requests slower than this are logged as warnings
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
- **Image:** CPU-only torch (the default Linux torch also downloads ~2.4 GB of CUDA
  libraries this service never uses) and the MiniLM model baked in at build time, so a
  new container never downloads it. The first build after this change takes a few
  minutes; check the build log for `torch-…+cpu`.
- **Memory:** the embedding model (long-term memory, copy detection, doubt clustering)
  loads in the background at boot. Give the service **≥ 1 GB RAM**.
- **Scheduler:** APScheduler runs in-process and starts on boot — no extra service.
  Every job takes a lock first, so with several workers or replicas each job still runs
  once (Postgres advisory lock via `SUPABASE_DB_URL` — use the **direct** connection on
  port 5432, not the transaction pooler on 6543 — or a file lock inside one container).
- **Workers:** the image runs **one** uvicorn worker. The response cache, rate limits
  and in-memory jobs are per process, so extra workers each keep their own. Raise it
  only if the service has the RAM (each worker loads its own copy of the model, about
  +300 MB): change the Dockerfile `CMD` to `uvicorn main:app --workers 2 …`. Running
  the `2026-10-22_jobs.sql` migration first keeps background jobs visible to all workers.
- **Logs:** one line per request in Railway's log view —
  `request id=… method=GET path=/progress status=200 ms=84 role=student` (route, status,
  time and role only: no user ids, emails, tokens or query strings). Requests slower than
  `SLOW_REQUEST_MS` are `WARNING … SLOW /route`. Every response carries `X-Request-ID`;
  search the logs for it when a user reports a problem.
- **System health:** the admin Analytics page has a card with uptime, the `/ready`
  checks, RAG server status, each scheduled job's last run / duration / next run, and the
  last hour's requests (5xx errors, slow requests, p50/p95). Per backend instance.
- **Error tracking (optional):** Sentry's free tier can be added for backend and frontend
  later — it's an outside service, so only with your go-ahead.
- **Uptime ping (optional, free):** a free monitor such as UptimeRobot can call
  `https://<your-railway-domain>/health` every 5 minutes and email you when it's down.
  It's an outside service, so set it up only if you want one.
- **Health vs ready:** `/health` answers instantly (Railway's health check uses it).
  `/ready` returns 200 once Supabase answers and the embedding model has loaded
  (about 20–45 s after a deploy), else 503 with each check listed.
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
