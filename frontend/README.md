# SmartCoaching — Frontend

The **Next.js 14 + TypeScript** web client for the SmartCoaching platform — four
role-based dashboards (Student · Teacher · Parent · Admin) plus the marketing landing
page. Talks to the FastAPI backend over REST + SSE, and uses Supabase directly for auth.

> 🔗 **UI repository:** https://github.com/SanjayRawat0570/coaching_inst_ui
> 🧠 **Backend:** FastAPI engine (LangGraph agents, Supabase, RAG via RAG_SERVER) — see
> [`../backend/README.md`](../backend/README.md). Full deploy guide in [`../DEPLOYMENT.md`](../DEPLOYMENT.md).

---

## Stack

| Layer | Choice |
|-------|--------|
| Language | **TypeScript** (migrated from JavaScript; non-strict config) |
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

```bash
npm run dev     # local dev server
npm run build   # production build (also type-checks)
npm run start   # serve the production build
```

---

## Environment ([.env.local.example](.env.local.example))

```
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
NEXT_PUBLIC_SUPABASE_KEY=your_supabase_anon_public_key   # anon/public key only
NEXT_PUBLIC_API_URL=http://localhost:8000                # FastAPI backend base URL
```

> ⚠️ **The `NEXT_PUBLIC_` prefix is required.** Next.js only exposes variables with that
> prefix to the browser. Naming them `SUPABASE_URL` / `SUPABASE_KEY` makes Supabase fall
> back to a placeholder URL → `Failed to fetch` on login.
> These values are inlined at **build time** — change them and you must restart/redeploy.

---

## TypeScript

The project was migrated from JavaScript to TypeScript:

- All source files are **`.tsx`** (pages/components) or **`.ts`** (lib); config files stay `.js`.
- Config in [tsconfig.json](tsconfig.json) is **non-strict** (`strict: false`) for smooth
  adoption — the app behaves exactly as before. Tighten types incrementally by enabling
  `strict` later.
- `npm run build` runs the full type-check; `npx tsc --noEmit` checks types without building.
- Tailwind's `content` globs include `ts,tsx` ([tailwind.config.js](tailwind.config.js)) so
  classes in `.tsx` files aren't purged.

---

## How it connects to the backend

```
Browser ──(Supabase JS)──▶ Supabase Auth      → returns a JWT
   │
   └──(fetch, Bearer JWT)──▶ FastAPI backend   → role-checked REST + SSE
                              (NEXT_PUBLIC_API_URL)
```

- [lib/supabase.ts](lib/supabase.ts) — Supabase client (login/signup, session).
- [lib/useAuth.ts](lib/useAuth.ts) — auth hook; guards pages and exposes the current role.
- [lib/api.ts](lib/api.ts) — fetch wrapper that attaches the Bearer token: `api()` (JSON),
  `apiUpload()` (multipart, Study Material), `streamDoubt()` (SSE: tokens, `[STATUS]`,
  `[ERROR]`, `[META]` → `onMeta`, `[DONE]`; multi-line `data:` events are joined with `\n`).
- [lib/useTheme.ts](lib/useTheme.ts) — light/dark theme toggle.

Each role lands on its own dashboard and only sees its own data (enforced by the
backend's `require_role` + Supabase RLS).

---

## Pages ([pages/](pages/))

| Route | Purpose |
|-------|---------|
| `/` | Landing page ([index.tsx](pages/index.tsx)) |
| `/login` | Sign up / log in; role chosen on signup |
| `/architecture` | How the platform works — **direct URL only** (no nav link) |
| `/student/doubt` | Ask doubts — text, voice or photo; streamed AI answer with source chips, 👍/👎, "New chat" |
| `/student/test` | Take assigned tests (timer, instant score) |
| `/student/progress` | Concept mastery, streak, XP, predicted rank |
| `/student/challenges` | Practice challenges / flashcards |
| `/teacher/dashboard` | Class KPIs, content gaps, answer quality, at-risk alerts, doubt clusters (linked to notes), roster |
| `/teacher/review` | Review, edit marks, and approve generated tests (HITL); each question shows its source |
| `/teacher/materials` | **Study Material** (teacher + admin): upload notes / NCERT / PYQs, indexing status, Re-index, Delete; admin "Re-index all" |
| `/parent/report` | Weekly per-child progress report |
| `/admin/analytics` | Institute-wide analytics, AI usage (RAG_SERVER queries, tokens, cost, cache hit rate) & audit logs |

### RAG features in the UI

- **Citations** — every doubt answer lists its sources as chips (`Physics_Notes.pdf · p. 12`),
  de-duplicated. Confidence comes from `[META]` (falls back to an old `CONFIDENCE: XX%` line).
- **Not covered** — when an answer isn't backed by the institute's notes an amber note says
  so; the teacher sees it under **Content gaps**.
- **Conversation memory** — the chat keeps RAG_SERVER's `conversation_id`; **New chat** resets it.
- **Feedback** — 👍/👎 once per answer → `POST /doubt/feedback` (forwarded to RAG_SERVER).
- **Study Material** — the only way content enters the RAG. The list polls every 3 s while
  files index. Deleting removes the file from the list and storage; chunks already indexed
  stay in RAG_SERVER. **Re-index** restores a file after RAG_SERVER lost its data.
- `useAuth({ requireRole })` / `<Shell requireRole>` accept a role or a list of roles.

Shared UI: [components/Shell.tsx](components/Shell.tsx) (app frame/nav),
[components/ui.tsx](components/ui.tsx) (primitives), [components/ActivityHeatmap.tsx](components/ActivityHeatmap.tsx),
[components/ThemeToggle.tsx](components/ThemeToggle.tsx), [components/Icon.tsx](components/Icon.tsx).

> The **Architecture** link was removed from all dashboards and the landing nav/footer.
> The page still works at `/architecture` if you type the URL directly.

---

## Theming

Colors and elevation are driven by design tokens in [tailwind.config.js](tailwind.config.js)
+ component classes in [styles/globals.css](styles/globals.css) (`brand`, `card`,
`btn-primary`, `badge-brand`, …). The current palette is **Royal Violet + Plum**
(`brand` = violet `#7c3aed`). Changing the `brand` token re-skins the entire app.

---

## Deployment — Vercel

Deploys to **Vercel** as a standard Next.js app. If deploying this monorepo, set the
project's **Root Directory to `frontend`**; if deploying the dedicated UI repo, the root
is the repo itself. Set the three `NEXT_PUBLIC_*` env vars in the Vercel project, pointing
`NEXT_PUBLIC_API_URL` at your **Railway** backend domain.

The backend deploys separately to Railway — see [`../DEPLOYMENT.md`](../DEPLOYMENT.md).
