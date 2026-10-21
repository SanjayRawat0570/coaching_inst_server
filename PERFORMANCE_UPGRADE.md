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

## Phase 2 results (2026-10-22)

Same machine and command. "No cache" = `--no-cache` (the queries themselves);
"cached" = a repeat visit within the TTL. The indexes migration is **not applied yet**,
so these numbers are without it.

| Endpoint | Phase 1 p50 | Phase 2 p50, no cache | Phase 2 p50, cached | Supabase calls (Phase 0 → now) |
|---|---|---|---|---|
| /teacher/overview | 236 ms | 120 ms (3 reads in parallel) | 15 ms | 4 → 4 (0 when cached) |
| /admin/analytics | 439 ms | 167 ms (5 reads in parallel) | 11 ms | 8 → 7 (0 when cached) |
| /parent/report (1 child) | 370 ms | 192 ms | not cached | 8 → 6 (2 children: 15 → 6) |
| /leaderboard | 61 ms | 59 ms | 10 ms | 3 → 1 (0 when cached) |
| /student/concept-map | – | 47 ms (bench student has no weak concepts) | 7 ms | 1 + 3 per concept → 3 |

Concept map on real data (6 weak concepts): 18 → 3 Supabase calls, 787 → 127 ms,
identical results. Weekly summary for 5 students: 25 → 4 queries, 1221 → 196 ms,
identical values. Test submit: weakness_map 2 queries per concept → 2 in total.
Flashcard reminder job: 1 + 1 per student → 1 paged read + 1 per 200 due students.

## Phase 3 results (2026-10-22)

Measured with real LLMs from the dev machine.

| What | Before | After |
|---|---|---|
| Grade 3 theory answers (Groq qwen/qwen3.8-27b) | 3450 ms one at a time | 1500 ms side by side (same marks) |
| /test/submit post-test agents (rank, progress, flashcards) | sum of the three | the slowest one (test: 3 x 0.2 s -> < 0.5 s) |
| Weak concepts' prerequisite links (1 LLM call each) | one after another | 3 at a time |
| Class test generation (1 LLM call per student) | one after another | 3 at a time |
| Slow endpoints with ?job=1 | request held open for the whole LLM work | returns {job_id} at once; GET /jobs/{id} |
| /doubt/stream first byte | after the first RAG / LLM step | a [STATUS] at once (test: < 0.25 s while the answer takes 0.3 s+) |

Short-task model choice (cluster label, median of 3): Groq qwen/qwen3.8-27b 111 ms,
openai/gpt-oss-120b 286 ms, openai/gpt-oss-20b 606 ms, Gemini 2.5 Flash 2852 ms.
A max_tokens cap was tried and dropped: it saved ~0–90 ms and made the gpt-oss models
return empty answers (they spend the budget on reasoning).

Provider status on 2026-10-22: Groq's default `llama-3.3-70b-versatile` returns 404;
Gemini free tier allows 5 requests/min for gemini-2.5-flash; OpenRouter's
`meta-llama/llama-3.3-70b-instruct:free` is no longer free (404).

## Phase 4 results (2026-10-22)

The image could not be built on the dev machine (Docker Desktop stopped, < 4 GB free),
so the size numbers are measured download sizes of the exact wheels pip resolves for
Linux / Python 3.11 — confirm on the first Railway build.

| What | Before | After |
|---|---|---|
| torch download in the image | 2,988 MB (torch 2.14.1 555 MB + 19 CUDA packages 2,433 MB) | 207 MB (torch 2.14.1+cpu 196 MB + deps) |
| MiniLM model on a new container | downloaded on first use (34.5 s here) | baked into the image (88 MB) |
| Model load from disk | 16.3 s (hub still checked online) | 11.5 s (`HF_HUB_OFFLINE=1`) |
| Build context | everything but frontend / .git | also drops backend/tests and dev requirements |
| Scheduled jobs with 2+ workers | every worker runs every job (duplicate emails) | one runs, the others skip (advisory / file lock, held >= 60 s) |
| Flashcard reminder trigger | interval from each process's start | cron */5, aligned across workers |
| Per-student job loops | one student at a time | batches of 50, 3 at a time (2 for emailing jobs, 1 for the inactivity job) |
| Job visibility | a print of the result | duration + outcome logged and kept in LAST_RUNS |

## Phase 5 results (2026-10-22)

`next build`, First Load JS:

| Page | Phase 0 | Phase 5 |
|---|---|---|
| /teacher/dashboard | 259 kB | 167 kB |
| /admin/analytics | 257 kB | 165 kB |
| /student/progress | 252 kB | 166 kB |
| /student/doubt | 154 kB | 159 kB (Markdown + KaTeX load as a separate chunk) |
| other signed-in pages | 154 kB | 163 kB (SWR, toasts) |
| /login | 152 kB | 156 kB |
| / and /architecture | 91.7 / 92.5 kB | 95.2 / 95.9 kB |

Lighthouse (local production build, median of 3 mobile runs):

| Page | Phase 0 mobile perf / a11y | Phase 5 mobile perf / a11y | Phase 5 desktop perf / a11y |
|---|---|---|---|
| / | 81 / 91 | 89 / 100 | 100 / 100 |
| /login | 96 / 96 | 94 / 100 | 100 / 100 |

Logged-in pages still need a manual Lighthouse run while signed in (DevTools).

What changed: one auth state per visit (no `getUser()` round trip or "Loading…" screen per
navigation; Supabase JS loaded on demand); SWR data hooks; skeletons + Retry error
states; optimistic flashcard review, alert read, test approve/reject, doubt rating, target
exam, with toasts and rollback; doubt page with Markdown + maths, rAF-batched streaming,
bottom-only auto-scroll, Stop / Retry, step line; test page autosave + restore, wall-clock
timer, leave warning, submit as a background job with retry that never submits twice;
teacher test generation as background jobs with live status; Recharts behind
`next/dynamic`; Inter via `next/font`; scroll restoration; 40 px tap targets, visible
keyboard focus, input labels, reduced motion; error boundary, offline banner, expired
session -> /login with a message.

## Phase 6 results (2026-10-22)

- Request log line per request (id, method, route, status, ms, role — no personal data),
  `X-Request-ID` on every response, `WARNING SLOW` above 2 s (streams judged by first byte).
- `GET /admin/system-health` + a System health card on the admin Analytics page.
- `scripts/loadtest.py`: N concurrent students, no new dependency; refuses doubts unless
  RAG_SERVER_URL is local.

Load test, 50 concurrent students, 20 s, ~1 s think time (in-process, real Supabase,
token check skipped):

| | First run | After the fix it found |
|---|---|---|
| Error rate | 2.4% (`/progress` 10.6%: ReadError / RemoteProtocolError) | 0.0% |
| p50 / p95, all requests | 49 / 1934 ms | 42 / 156 ms |
| `/progress` p50 / p95 | 174 / 4805 ms | 133 / 260 ms |
| Throughput | 33.8 req/s | 39.7 req/s |

Cause: newer supabase-py talks HTTP/2 to PostgREST, and one HTTP/2 connection shared by
all request threads breaks under load. The shared client now uses a pooled HTTP/1.1
connection where the library allows it (the pinned supabase 2.5 is HTTP/1.1 already).

Found while load testing: the live database is missing `study_plans` (in schema.sql,
never created) and the tables of migrations not yet run (`institute_secrets`,
`study_materials`, `nta_cutoffs`, `student_memories`, `jobs`).
