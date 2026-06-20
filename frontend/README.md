# SmartCoaching — Frontend

The **Next.js 14** web client for the SmartCoaching platform — four role-based
dashboards (Student · Teacher · Parent · Admin) plus the marketing landing page.
Talks to the FastAPI backend over REST + SSE, and uses Supabase directly for auth.

> 🔗 **UI repository:** https://github.com/SanjayRawat0570/coaching_inst_ui
>  **Backend:** the FastAPI engine (LangGraph agents, RAG, Supabase, Qdrant) — see
> [`../backend/README.md`](../backend/README.md) for the complete server flow.

---

## Stack

| Layer | Choice |
|-------|--------|
| Framework | Next.js 14 (Pages Router) + React 18 |
| Styling | Tailwind CSS (token-driven theme, dark mode via `class`) |
| Auth | `@supabase/supabase-js` (JWT stored client-side, sent as Bearer to the API) |
| Charts | Recharts |
| Icons | lucide-react |

---

## Quick start

```bash
# 1. Install
npm install

# 2. Secrets — copy the template and fill in your values
cp .env.local.example .env.local

# 3. Run (http://localhost:3000)
npm run dev
```

Make sure the **backend is running** (default `http://localhost:8000`) — the UI calls it.

```bash
npm run dev     # local dev server
npm run build   # production build
npm run start   # serve the production build
```

---

## Environment ([.env.local.example](.env.local.example))

```
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
NEXT_PUBLIC_SUPABASE_KEY=your_supabase_anon_public_key   # anon/public key only
NEXT_PUBLIC_API_URL=http://localhost:8000                # FastAPI backend base URL
```

> `NEXT_PUBLIC_*` values are **inlined at build time** — change them and rebuild.
> Only ever use the Supabase **anon** key here; the service key stays on the backend.

---

## How it connects to the backend

```
Browser ──(Supabase JS)──▶ Supabase Auth      → returns a JWT
   │
   └──(fetch, Bearer JWT)──▶ FastAPI backend   → role-checked REST + SSE
                              (NEXT_PUBLIC_API_URL)
```

- [lib/supabase.js](lib/supabase.js) — Supabase client (login/signup, session).
- [lib/useAuth.js](lib/useAuth.js) — auth hook; guards pages and exposes the current role.
- [lib/api.js](lib/api.js) — fetch wrapper that attaches the Bearer token and hits the API
  (incl. SSE for streamed doubt answers).
- [lib/useTheme.js](lib/useTheme.js) — light/dark theme toggle.

Each role lands on its own dashboard and only sees its own data (enforced by the
backend's `require_role` + Supabase RLS).

---

## Pages ([pages/](pages/))

| Route | Purpose |
|-------|---------|
| `/` | Landing page ([index.js](pages/index.js)) |
| `/login` | Sign up / log in; role chosen on signup |
| `/architecture` | How the platform works |
| `/student/doubt` | Ask doubts — text, voice or photo; streamed AI answer |
| `/student/test` | Take assigned tests (timer, instant score) |
| `/student/progress` | Concept mastery, streak, XP, predicted rank |
| `/student/challenges` | Practice challenges / flashcards |
| `/teacher/dashboard` | Class KPIs, at-risk alerts, doubt clusters, roster |
| `/teacher/review` | Review, edit marks, and approve generated tests (HITL) |
| `/parent/report` | Weekly per-child progress report |
| `/admin/analytics` | Institute-wide analytics & audit logs |

Shared UI: [components/Shell.js](components/Shell.js) (app frame/nav),
[components/ui.js](components/ui.js) (primitives), [components/ActivityHeatmap.js](components/ActivityHeatmap.js),
[components/ThemeToggle.js](components/ThemeToggle.js), [components/Icon.js](components/Icon.js).

---

## Theming

Colors and elevation are driven by design tokens in
[tailwind.config.js](tailwind.config.js) + component classes in
[styles/globals.css](styles/globals.css) (`brand`, `card`, `btn-primary`, `badge-brand`, …).
Changing the `brand` token re-skins the entire app, including all dashboards.

---

## Deployment

Deploys to **Vercel** as a standard Next.js app. Set the three `NEXT_PUBLIC_*` env vars
in the Vercel project, pointing `NEXT_PUBLIC_API_URL` at your deployed backend
(e.g. the HuggingFace Space). The backend deploys separately — see
[`../backend/README.md`](../backend/README.md).
