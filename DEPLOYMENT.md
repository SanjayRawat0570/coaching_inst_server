# Deployment — 100% free: Backend on Hugging Face Spaces, Frontend on Vercel

Two services, deployed independently, both on free plans (no credit card):

```
  Vercel (Next.js)  ──HTTPS──▶  Hugging Face Space (FastAPI/Docker)  ──▶ Supabase · RAG_SERVER · LLMs · Resend
  NEXT_PUBLIC_API_URL ────────────────^ (https://<user>-<space>.hf.space)
```

Order matters: **deploy the backend first**, grab its public URL, then give that URL
to the frontend as `NEXT_PUBLIC_API_URL`.

---

## What everything costs

| Service | Used for | Plan | Card needed? |
|---|---|---|---|
| Hugging Face Spaces | Backend hosting (2 vCPU, 16 GB RAM) | Free CPU basic | No |
| Vercel | Frontend hosting | Hobby (free) | No |
| Supabase | Auth, Postgres + pgvector, Storage | Free | No |
| Groq / Gemini / OpenRouter | LLMs (fallback chain) | Free tiers | No |
| Resend | Parent / teacher emails | Free, 100/day, 3000/month | No |
| RAG_SERVER | Doubts, study material search | Your own service — host it on a free plan too | — |

There is no WhatsApp channel: every WhatsApp provider is paid, so the app sends email only.

### Free-plan limits to know
- **Hugging Face:** a free Space **sleeps after 48 h without traffic**. The next request
  wakes it (1–2 minutes). Scheduled jobs (weekly reports, nightly alerts) only run while
  it is awake. A Space is public by default — it only exposes the API, and every
  endpoint already requires a Supabase login, so that's fine.
- **Supabase:** a free project **pauses after 7 days with no activity**; un-pause it in
  the dashboard. 500 MB database, 1 GB storage.
- **Vercel Hobby** is meant for personal / non-commercial use. If the institute starts
  charging money through the site, move the frontend to Cloudflare Pages or Netlify
  (both have free commercial-use plans).
- **Resend** without your own domain can only send from `onboarding@resend.dev`, and only
  to the email you signed up with. Verify a domain (free) to email real parents.

---

## Prerequisites (one-time)

- **Supabase** project — run [`backend/schema.sql`](backend/schema.sql) once in the SQL editor
  (existing DB: the files in [`backend/migrations/`](backend/migrations/)). This also creates
  the private Storage bucket `study-materials`.
- **RAG_SERVER** (hosted, used as-is) — its URL, plus a tenant + `member` API key per
  institute that you create with your RAG_SERVER login (`POST /api/v1/tenants`,
  `POST /api/v1/security/api-keys`).
- **LLM keys** — Groq (and/or Gemini, OpenRouter). All free sign-ups.
- Optional: **Resend** (email).
- A free **Hugging Face** account and a free **Vercel** account.

---

## 1 — Backend → Hugging Face Spaces

The Space builds from the root [`Dockerfile`](Dockerfile). Its settings are in the front
matter at the top of the root [`README.md`](README.md) (`sdk: docker`, `app_port: 8000`).

1. On huggingface.co: **New → Space** → name it (e.g. `smart-coaching`), SDK **Docker**
   (blank template), hardware **CPU basic · free**.
2. **Settings → Variables and secrets** → add each as a **secret**:

   ```
   GROQ_API_KEY=...
   GEMINI_API_KEY=...
   OPENROUTER_API_KEY=...
   SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
   SUPABASE_KEY=your_anon_key
   SUPABASE_SERVICE_KEY=your_service_role_key
   SUPABASE_DB_URL=postgresql://postgres:PASSWORD@db.YOUR_PROJECT_ID.supabase.co:5432/postgres
   RAG_SERVER_URL=https://your-rag-server.example.com
   RAG_SERVER_API_KEY=sk-...        # default tenant's member key (or per-institute rows)
   RAG_SERVER_TENANT=smartcoaching
   RAG_SERVER_TIMEOUT=30
   RESEND_API_KEY=...
   APP_ENV=production
   ```
   > Do **not** set `PORT`.

3. Connect GitHub so pushes deploy automatically
   ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)):
   - Hugging Face → **Settings → Access Tokens** → new token, role **Write**.
   - GitHub repo → **Settings → Secrets and variables → Actions**:
     - secret `HF_TOKEN` = that token
     - variable `HF_SPACE` = `your-hf-username/smart-coaching`
   - Push to `main` (or run the workflow by hand from the **Actions** tab).
4. Wait for the build in the Space's **Logs** tab (the ML deps make the first build a few
   minutes). Then verify:

   ```
   https://<user>-<space>.hf.space/health   ->  {"status":"ok"}
   https://<user>-<space>.hf.space/docs     ->  interactive API docs
   ```

**Copy that `.hf.space` URL — the frontend needs it next.**

### Notes / gotchas
- **Model cache:** the MiniLM model downloads into `/tmp` at runtime (env vars already set
  in the Dockerfile). Expect a slow *first* request after each wake-up, fast afterwards.
- **Scheduler:** APScheduler runs in-process and starts on boot — no extra service needed.

---

## 2 — Frontend → Vercel (Hobby, free)

1. **Add New… → Project** → import the frontend repo.
   - Using the **dedicated UI repo** (`coaching_inst_ui`): Root Directory = repo root.
   - Using **this monorepo**: set **Root Directory = `frontend`**.
2. Framework preset: **Next.js** (auto-detected). Build = `next build`, output auto.
3. **Environment Variables** (Production + Preview):

   ```
   NEXT_PUBLIC_SUPABASE_URL = https://YOUR_PROJECT_ID.supabase.co
   NEXT_PUBLIC_SUPABASE_KEY = your_anon_public_key
   NEXT_PUBLIC_API_URL      = https://<user>-<space>.hf.space     # from step 1.4
   ```
   > `NEXT_PUBLIC_*` are inlined at **build time** — if you change `NEXT_PUBLIC_API_URL`
   > later, **redeploy** the frontend.

4. **Deploy.** Open the Vercel URL and log in to confirm the dashboards load data.

---

## 3 — Connect & verify

1. The backend already allows all origins (`CORS allow_origins=["*"]`), so the Vercel
   domain works out of the box. To lock it down later, restrict origins in
   [`backend/main.py`](backend/main.py) to your Vercel domain.
2. Smoke test end-to-end:
   - Sign up (student) on the Vercel site → lands on the student dashboard.
   - Ask a doubt → confirms Vercel → Space → LLM/RAG → response works.
   - As a teacher, generate + approve a test; as the student, take it.

---

## Quick reference

| | Backend | Frontend |
|---|---------|----------|
| Host | Hugging Face Spaces (free) | Vercel Hobby (free) |
| Build | Root `Dockerfile` | Next.js (auto) |
| Deploys on | push to `main` (GitHub Action) | push (Vercel Git integration) |
| Port | `8000` (`app_port` in README front matter) | n/a |
| Health | `/health` | — |
| Key env | `SUPABASE_*`, `RAG_SERVER_*`, `GROQ_API_KEY` | `NEXT_PUBLIC_*` |
| Depends on | — | Space URL via `NEXT_PUBLIC_API_URL` |
