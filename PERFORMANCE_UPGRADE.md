# SmartCoaching — Performance & Smoothness Upgrade Prompt

**How to use:** open Claude Code in your `coaching_inst` folder (the `coaching_inst_server` repo, with `backend/` and `frontend/`). Save this file as `PERFORMANCE_UPGRADE.md` and say: "Read PERFORMANCE_UPGRADE.md and do Phase 0." Then go one phase at a time ("Do Phase 1", …) and test the app after each phase before moving on.

## 0. Context and rules — read first

SmartCoaching is live: backend = FastAPI + LangGraph agents on Railway (Docker), frontend = Next.js 14 (Pages Router, TypeScript, Tailwind) on Vercel, database/auth/files = Supabase, RAG = my separate hosted RAG_SERVER over HTTP (`backend/rag/rag_server_client.py`). The RAG integration (Phases 1–8 of `backend/RAG_INTEGRATION.md`) is done; 127 backend tests pass.

**Goal:** make the whole platform fast (low latency, fast page loads, fast builds and cold starts) and smooth to use (no freezes, no blank screens, instant feedback, graceful errors) — without changing what the features do.

### Hard rules

- Never change RAG_SERVER (code, settings, deploy). Only the coaching repo changes.
- **Measure before and after.** Every optimisation must show a number (latency, bundle size, image size, query count). No "should be faster" guesses.
- **Don't break anything:** keep all API contracts the frontend uses, keep the SSE doubt format, keep auth/role checks and institute scoping. All tests must pass after every phase; add tests for new behaviour.
- **Stay on free / current plans:** Railway (backend), Vercel (frontend), Supabase free. No new paid services. Free tiers of Sentry or UptimeRobot are fine only if I approve.
- **Ask before** any major dependency upgrade (e.g. langchain 0.2 → newer, langgraph, Next 14 → 15), any schema change that rewrites data, or anything that changes behaviour.
- Small commits, one per phase, with a short report: what changed, before/after numbers, how to test it.
- My machine has very little disk space. Clean build outputs you create, don't download large models locally unless needed, and use `git -c http.sslBackend=schannel push` for pushes.

## Phase 0 — Measure (no code changes)

- **Backend timings.** Run the backend locally and time the hot endpoints (10 runs each, report p50/p95): `/health`, `/progress`, `/leaderboard`, `/flashcards/due`, `/teacher/overview`, `/teacher/students`, `/teacher/alerts`, `/admin/analytics`, `/parent/report`, `/doubt/stream` (time to first token and total), `/test/generate`, `/test/submit`. Write a reusable script `backend/scripts/bench.py` for this.
- **Database round trips.** For each endpoint above, count Supabase calls per request and list N+1 patterns (a query inside a loop over students/tests/concepts).
- **Hot-path problems.** Find: a new Supabase client created per call (`create_client` inside functions), new httpx clients per request, blocking calls inside `async def`, sync LLM calls in series that could run in parallel, missing timeouts on LLM or HTTP calls, model loading on first request (MiniLM cold start), large payloads (`select("*")`).
- **Docker image.** Image size, build time, and app cold-start time (container start → `/health` OK → first real request). Note if torch is the full CUDA build.
- **Scheduler.** How each APScheduler job loops over students; how long it takes; whether running more than one uvicorn worker would run jobs twice.
- **Frontend.** `next build` output (First Load JS per page), heaviest dependencies (`@next/bundle-analyzer`), Lighthouse scores (performance, accessibility) for `/`, `/login`, `/student/doubt`, `/student/progress`, `/teacher/dashboard`, `/admin/analytics` on mobile emulation. List pages that show a blank screen or spinner while loading, and every place that fetches data with plain `useEffect`.
- **Docs check.** List places that are out of date (e.g. the root README still says "needs keys in .env (Supabase, Qdrant…)", and mentions "Expo React Native" — confirm whether a mobile app exists).

Reply with a baseline table and a ranked list of the top 10 bottlenecks (impact × effort). Don't change code in Phase 0.

## Phase 1 — Backend quick wins (connections, timeouts, warm-up)

- **One Supabase client per process.** Replace every per-call `create_client(...)` with a shared singleton (e.g. `db.py: get_db()`), service-role for backend use. Keep behaviour.
- **Shared HTTP client for RAG_SERVER.** In `rag_server_client.py` reuse one `httpx.AsyncClient` and one `httpx.Client` (keep-alive, connection limits, created lazily, closed in the FastAPI lifespan). Keep all function signatures and fail-soft behaviour.
- **Timeouts everywhere.** Every LLM call and outbound HTTP call gets a timeout. In the Groq → Gemini → OpenRouter chain (`graph/llm.py`), fail over fast (e.g. 15–20 s per provider, shorter for small calls), and add a simple circuit breaker so a provider that just failed is skipped for ~60 s instead of every request waiting for it.
- **Warm start.** Load the MiniLM model in a background thread at startup (lifespan), so the first request isn't slow. Add `/ready` (Supabase + RAG_SERVER reachable, model loaded); keep `/health` instant for Railway's health check.
- **Response speed basics.** `GZipMiddleware` for JSON over ~1 KB; `select()` only the columns each endpoint needs instead of `*`; limit + paginate long lists (history, audit logs, submissions).
- Re-run `bench.py` and report before/after.

## Phase 2 — Database speed (indexes, fewer queries)

- **Indexes.** Add `backend/migrations/<date>_performance_indexes.sql` with `create index if not exists` for the real filter/sort columns found in Phase 0, e.g. `weakness_map(student_id, score)`, `doubt_logs(student_id, created_at desc)`, `doubt_logs(institute_id, created_at desc)`, `tests(student_id, status)`, `tests(institute_id, status, created_at desc)`, `alerts(institute_id, created_at desc)`, `activity_log(student_id, created_at desc)`, `flashcards(student_id, due_at)`, `study_materials(institute_id, created_at desc)`. Only add indexes that match real queries.
- **Kill N+1 queries.** Replace loops of queries with `in_()` batch queries, or Postgres views / RPC functions (`create or replace function …`) for the heavy aggregates: teacher overview KPIs, activity heatmaps, admin analytics, leaderboard, parent report. One or two round trips per dashboard instead of dozens.
- **Small in-memory cache** (`cachetools.TTLCache`, per process, keyed by institute/user): leaderboard, admin analytics, teacher overview, concept map: 30–120 s TTL. Invalidate on the writes that change them (test evaluated, doubt logged, flashcard reviewed). Never cache across institutes or roles.
- Update `DEPLOYMENT.md` with the new migration. Re-run `bench.py` and report.

## Phase 3 — Long AI tasks never block, and run in parallel

- **Background jobs for slow work.** `/test/generate`, `/teacher/tests/generate-class`, `/test/submit` grading and `/answer/evaluate` should return quickly with a `job_id` (status queued / running / done / failed) and do the work in the background (FastAPI `BackgroundTasks` or a small thread pool; store status in a `jobs` table so it survives a refresh). Add `GET /jobs/{id}`. Keep the old synchronous behaviour available behind a flag until the frontend is switched (Phase 5).
- **Parallel LLM work.** Where calls are independent (questions per weak concept, grading several theory answers, flashcards per concept, `search_many_sync`), run them concurrently with a small limit (e.g. 3–4 at once) to respect free-tier rate limits. Keep the parallel fan-out rule in the LangGraph graph (disjoint state keys).
- **Smarter model use.** Use the fastest model (Groq) for short tasks (classification, review checks, flashcards), and keep the larger fallback models for long answers. Lower `max_tokens` where answers are short. Report the latency change.
- **Protect free quotas.** Per-user rate limit on doubts and test generation (e.g. with slowapi or a tiny in-memory limiter) with a friendly message, e.g. "You're asking very fast. Please wait a few seconds."
- **Doubt stream.** Make sure nothing blocking runs inside the async stream; send the first `[STATUS]` immediately; time to first token should be close to RAG_SERVER's own.

## Phase 4 — Faster, lighter deploys and safe scaling on Railway

- **Smaller Docker image.** Install the CPU-only torch wheel (`--extra-index-url https://download.pytorch.org/whl/cpu`) before sentence-transformers; multi-stage build; `.dockerignore` for frontend, tests, caches; download the MiniLM model during the build so containers don't fetch it at start. Report image size and cold start before/after.
- **Workers and scheduler.** If more than one uvicorn worker helps (check Railway RAM), make sure scheduled jobs run once: guard each job with a Postgres advisory lock (or run the scheduler only in one worker). Otherwise keep one worker and use the thread pool.
- **Scheduled jobs.** Process students in batches with limited concurrency, log duration per job, and never block API requests.
- **Uptime.** Document a free uptime ping on `/health` (e.g. UptimeRobot) in `DEPLOYMENT.md`.

## Phase 5 — Frontend: fast and smooth ("fluent")

- **Data fetching.** Add SWR (small) and move pages from `useEffect` fetching to SWR hooks in `lib/hooks.ts`: cached, deduplicated, revalidate on focus, so going back to a page is instant. Keep `lib/api.ts` as the fetcher (Bearer token).
- **No blank screens.** Skeleton loaders that match each card/table instead of spinners; empty states; an error state with a "Retry" button.
- **Instant feedback (optimistic updates).** Flashcard review, doubt 👍/👎, test approve, badge/challenge actions update the UI immediately and roll back on error, with a small toast (`components/Toast.tsx`, no heavy library).
- **Doubt page.**
  - Render answers as Markdown with math (react-markdown + remark-math + rehype-katex), so JEE/NEET formulas display properly; load it with `next/dynamic`.
  - Smooth streaming: buffer tokens and update state at most once per animation frame; auto-scroll only when the user is already at the bottom.
  - Stop button (`AbortController`) and Retry on error; keep the input usable.
  - Show RAG steps as a small progress line ("Searching notes…" → "Writing answer…").
- **Test page.** Autosave answers to localStorage every few seconds, so a refresh or network drop never loses work; restore on reload; accurate timer based on the start time (not counting intervals); warn before leaving with unsaved answers; submit with retry.
- **Long jobs UI.** Test generation and grading show progress from `GET /jobs/{id}` (polling with backoff), so the teacher never stares at a frozen button.
- **Bundle size.** Load Recharts and other heavy components with `next/dynamic` (`ssr: false`) only on pages that use them; import lucide icons individually; use `next/font` for fonts; remove unused dependencies. Report First Load JS per page before/after.
- **Navigation.** Prefetch the next likely pages (`<Link prefetch>`), keep the Shell layout mounted between pages, and keep scroll position on back.
- **Mobile + accessibility.** Check every page at 360 px width; tap targets ≥ 40 px; labels on inputs; color contrast in both themes; keyboard focus visible.
- **Resilience.** A global error boundary; an "You're offline" banner; when the Supabase session expires, refresh it quietly or send the user to `/login` with a message, never a broken page.
- Re-run Lighthouse on the Phase 0 pages; target ≥ 90 performance on desktop and as high as possible on mobile. Report before/after.

## Phase 6 — Reliability and visibility

- **Request IDs + timing logs** in the backend (middleware): method, path, status, duration, user role. No secrets or personal data in logs.
- **Slow-request warnings** (> 2 s) logged with the endpoint name.
- **Admin "System health" card:** backend uptime, `/ready` checks, RAG_SERVER reachable, last run time + duration of each scheduled job, recent error count.
- **Error tracking** (optional, ask me first): Sentry free tier for backend and frontend.
- **Load test:** a small Locust or k6 script for 50 concurrent students (login token reuse, progress, leaderboard, flashcards, a few doubts against a local RAG_SERVER copy). Report p95 latency and error rate. Never load-test the live RAG_SERVER.

## Phase 7 — Cleanup, docs, final report

- Fix outdated docs: the root README "Run it" (no Qdrant any more), the "Expo React Native" mention if there's no mobile app, and make sure `README.md`, `backend/README.md`, `frontend/README.md` and `DEPLOYMENT.md` match the code.
- Remove dead code and unused dependencies found during this work (ask before removing anything not clearly dead).
- Sync `frontend/` to the UI repo (the `git commit-tree` command in the README) so Vercel gets the new frontend.
- **Final report:** a before/after table for every metric from Phase 0, files changed, new migrations to run in Supabase, new env vars (if any), and anything left for later.

## Later ideas (only after Phases 0–7, ask me first)

- PWA: installable app on Android phones, cached app shell, works on weak networks.
- Hindi / Hinglish UI toggle for students and parents.
- In-app notifications (bell icon) for test assigned, result ready, teacher alerts.
- Upgrade LangChain / LangGraph to current versions (big change: needs its own plan).

---

## Phase 0 baseline (measured 2026-10-22)

Measured from the dev machine against the real Supabase project (TLS-intercepting
network, so absolute numbers are higher than on Railway; compare before/after on the
same machine). Re-run with `python -m scripts.bench --runs 10 --truststore` from `backend/`.

### Backend (in-process, 10 warm runs + 1 cold; token verification excluded, adds ~46 ms)

| Endpoint | Role | Cold ms | p50 ms | p95 ms | Supabase calls/request |
|---|---|---|---|---|---|
| /health | – | 42 | 14 | 21 | 0 |
| /progress | student | 1451 | 211 | 339 | 4 |
| /leaderboard | student | 377 | 156 | 176 | 3 |
| /flashcards/due | student | 2118 | 1767 | 2445 | 2 (+1 new client) |
| /teacher/overview | teacher | 1308 | 392 | 484 | 4 |
| /teacher/students | teacher | 99 | 127 | 289 | 1 |
| /teacher/alerts | teacher | – | – | – | 500 error when institute_id is empty |
| /admin/analytics | admin | 1032 | 534 | 792 | 8 |
| /parent/report | parent | 820 | 542 | 700 | 8 (1 child; +6 per extra child) |

Not measured yet (write rows / use LLM quota / RAG_SERVER_URL not set locally):
/doubt/stream, /test/generate, /test/submit.

Supabase client cost: `create_client` 520–700 ms, first query on a new client
~700 ms, query on a reused client 33–63 ms.

### Frontend (`next build`, First Load JS)

| Page | First Load JS |
|---|---|
| / | 91.7 kB |
| /login | 152 kB |
| /student/doubt, /student/test, /student/challenges, /parent/report, /teacher/review, /teacher/materials | 154 kB |
| /student/progress | 252 kB |
| /admin/analytics | 257 kB |
| /teacher/dashboard | 259 kB |
| shared by all | 86.9 kB |

Heaviest client packages (gzip): recharts 99.8 kB (+ lodash 25.1 kB, react-smooth 6.7 kB),
next 60.2 kB, react-dom 40.5 kB, @supabase/supabase-js + auth-js 55.1 kB, lucide-react 11.5 kB.

Lighthouse (mobile, production build, local): `/` performance 81, accessibility 91
(FCP 2.2 s, LCP 3.2 s, TBT 360 ms, CLS 0.03); `/login` performance 96, accessibility 96
(FCP 1.7 s, LCP 2.4 s, TBT 90 ms). Both: no `<title>`; `/`: low colour contrast.
Logged-in pages need a manual run while signed in (Chrome DevTools → Lighthouse).

### Docker

Not built locally (Docker Desktop stopped, little disk). `sentence-transformers` pulls
the default PyPI torch: 2.14.1 = 555 MB Linux wheel plus 6 CUDA dependency groups
(cuda-toolkit, cudnn, …) — the full CUDA build. MiniLM downloads on first use.

## Phase 1 results (2026-10-22)

Same machine and command as the baseline (`python -m scripts.bench --runs 10 --truststore`).

| Endpoint | p50 before → after | p95 before → after | Supabase calls before → after |
|---|---|---|---|
| /flashcards/due | 1767 → 54 ms | 2445 → 66 ms | 2 (+ new client) → 1 |
| /leaderboard | 156 → 61 ms | 176 → 615 ms (one outlier) | 3 → 1 |
| /progress | 211 → 165 ms | 339 → 186 ms | 4 → 3 |
| /teacher/overview | 392 → 236 ms | 484 → 254 ms | 4 → 4 (content-gap alerts no longer sent) |
| /teacher/students | 127 → 56 ms | 289 → 92 ms | 1 → 1 |
| /teacher/alerts | 500 error → 400 with a message for a blank institute | | |
| /admin/analytics | 534 → 439 ms | 792 → 614 ms | 8 → 8 (Phase 2) |
| /parent/report | 542 → 370 ms | 700 → 802 ms | 8 → 8 (Phase 2) |

Other numbers:
- Shared Supabase client: an agent call that used to build a client paid ~1.2 s
  (client 0.55 s + first query on a new connection 0.7 s); now ~50 ms.
- Embedding model: load 21.9 s + first encode 0.4 s, now done in the background at
  boot (`/ready` turned 200 at 43.5 s after start on this machine).
- LLM: Groq's `llama-3.3-70b-versatile` returns 404 model_not_found today. Before,
  that error reached the user; now the call fails over to Gemini (answered in 5.3 s)
  and Groq is skipped for 60 s.
