import Link from "next/link";

/* ── Data (mirrors instruction.md spec) ─────────────────────────────────────── */
const STATS = [
  { v: "8", l: "AI Agents" },
  { v: "6", l: "RAG Patterns" },
  { v: "4", l: "User Roles" },
  { v: "₹0", l: "Monthly Cost" },
];

const ROLES = [
  { icon: "🎓", name: "Student", color: "neon-cyan", points: ["24/7 doubts (text/voice/photo)", "Weakness-targeted tests", "AIR rank + XP streaks"] },
  { icon: "🧑‍🏫", name: "Teacher", color: "neon-green", points: ["Class concept heatmap", "At-risk alerts", "Approve AI tests (HITL)"] },
  { icon: "👨‍👩‍👦", name: "Parent", color: "neon-amber", points: ["Weekly WhatsApp report", "Avg score & focus areas", "Zero effort, automatic"] },
  { icon: "🏢", name: "Institute Admin", color: "neon-violet", points: ["Revenue & renewal signals", "Engagement analytics", "Faculty overview"] },
];

const AGENTS = [
  { n: "Doubt Agent", d: "Answers text/voice/image doubts from RAG", t: "Groq + Qdrant" },
  { n: "Test Generator", d: "Builds tests targeting weak concepts", t: "Groq + PYQ RAG" },
  { n: "Progress Tracker", d: "Updates concept weakness map post-test", t: "Supabase" },
  { n: "At-Risk Detector", d: "Nightly dropout scorer, flags 7 days early", t: "Scheduler" },
  { n: "Parent Reporter", d: "Sunday LLM-written progress report", t: "Groq + Twilio" },
  { n: "Answer Evaluator", d: "Grades handwriting photos step-by-step", t: "Gemini Vision" },
  { n: "AIR Rank Predictor", d: "Estimates All-India Rank from NTA data", t: "Qdrant" },
  { n: "Reviewer Agent", d: "Quality gate, loops generator ≤3×", t: "LangGraph loop" },
];

const RAG = [
  { n: "1 · Agentic", d: "LLM plans 2–4 targeted sub-queries" },
  { n: "2 · CRAG gate", d: "Scores relevance; weak → fallback" },
  { n: "3 · HyDE", d: "Hypothetical answer → embed → search" },
  { n: "4 · RAPTOR", d: "Picks chunk vs chapter-summary level" },
  { n: "5 · Web fallback", d: "Tavily over .edu / NCERT domains" },
  { n: "6 · CrossEncoder", d: "Re-ranks results by student level" },
];

const STACK = [
  { layer: "Frontend", color: "neon-cyan", items: ["Next.js 14", "Tailwind", "Recharts", "Supabase JS"] },
  { layer: "Backend", color: "neon-violet", items: ["FastAPI", "LangGraph", "APScheduler", "BackgroundTasks"] },
  { layer: "LLMs (free)", color: "neon-green", items: ["Groq Llama-3.3-70B", "Gemini 2.5 Flash", "OpenRouter", "Vision"] },
  { layer: "Data & Vectors", color: "neon-amber", items: ["Supabase Postgres", "pgvector", "Qdrant Cloud", "MiniLM embeds"] },
];

const FLOW = [
  { icon: "🧑", label: "User", sub: "4 roles" },
  { icon: "⚡", label: "FastAPI", sub: "JWT auth" },
  { icon: "🧠", label: "LangGraph", sub: "supervisor" },
  { icon: "🤖", label: "Agents", sub: "8 workers" },
  { icon: "🔎", label: "RAG", sub: "Qdrant" },
  { icon: "💬", label: "LLM", sub: "Groq→Gemini" },
];

/* ── Small building blocks ──────────────────────────────────────────────────── */
function Section({ kicker, title, children }) {
  return (
    <section className="mt-14">
      <p className="text-xs font-semibold uppercase tracking-widest text-neon-cyan/80">{kicker}</p>
      <h2 className="text-2xl font-bold tracking-tight mt-1 mb-5">{title}</h2>
      {children}
    </section>
  );
}

export default function Architecture() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-white/10 bg-ink-950/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid place-items-center h-8 w-8 rounded-xl bg-brand-grad text-white shadow-glow">🎓</span>
            <span className="font-bold tracking-tight">Smart<span className="grad-text">Coaching</span></span>
          </Link>
          <Link href="/" className="btn-ghost text-sm">← Back to app</Link>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-5 pb-24">
        {/* Hero */}
        <div className="pt-12 pb-2 bg-grid bg-[length:22px_22px] rounded-3xl">
          <span className="badge-brand">System Architecture</span>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mt-4 max-w-3xl">
            How the <span className="grad-text">Smart Coaching Platform</span> is built
          </h1>
          <p className="muted mt-4 max-w-2xl text-lg">
            An agentic, multi-tenant tutoring system on a 100% free stack — LangGraph orchestration,
            a 6-pattern RAG pipeline, and 8 specialized AI agents.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-8">
            {STATS.map((s) => (
              <div key={s.l} className="card p-5 text-center card-hover">
                <div className="text-3xl font-extrabold grad-text">{s.v}</div>
                <div className="muted text-xs mt-1">{s.l}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Request flow */}
        <Section kicker="End to end" title="Request flow">
          <div className="card p-6">
            <div className="flex flex-wrap items-stretch gap-2 justify-between">
              {FLOW.map((n, i) => (
                <div key={n.label} className="flex items-center gap-2 flex-1 min-w-[120px]">
                  <div className="card-hover w-full rounded-xl border border-white/10 bg-ink-900/60 p-3 text-center">
                    <div className="text-2xl">{n.icon}</div>
                    <div className="font-semibold text-sm mt-1">{n.label}</div>
                    <div className="muted text-[11px]">{n.sub}</div>
                  </div>
                  {i < FLOW.length - 1 && <span className="text-brand text-xl hidden md:inline">→</span>}
                </div>
              ))}
            </div>
            <p className="muted text-sm mt-5 border-t border-white/10 pt-4">
              After a test submit, the graph <span className="text-neon-violet">fans out in parallel</span> to
              Progress&nbsp;Tracker, Rank&nbsp;Predictor &amp; Flashcard generator, then joins at an aggregator.
              Test generation runs a <span className="text-neon-cyan">reviewer loop</span> (≤3×) and pauses at a
              <span className="text-neon-green"> human-in-the-loop</span> teacher approval.
            </p>
          </div>
        </Section>

        {/* User roles */}
        <Section kicker="Who uses it" title="Four user roles">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {ROLES.map((r) => (
              <div key={r.name} className="card card-hover p-5">
                <div className="text-3xl">{r.icon}</div>
                <h3 className={`font-bold mt-3 text-${r.color}`}>{r.name}</h3>
                <ul className="mt-3 space-y-1.5">
                  {r.points.map((p) => (
                    <li key={p} className="muted text-sm flex gap-2">
                      <span className={`text-${r.color}`}>•</span>{p}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>

        {/* Agents */}
        <Section kicker="The brains" title="Eight AI agents">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {AGENTS.map((a, i) => (
              <div key={a.n} className="card card-hover p-5 relative overflow-hidden">
                <span className="absolute -right-3 -top-3 text-6xl font-black text-white/5 select-none">{i + 1}</span>
                <h3 className="font-bold text-sm">{a.n}</h3>
                <p className="muted text-sm mt-2">{a.d}</p>
                <span className="badge-brand mt-3">{a.t}</span>
              </div>
            ))}
          </div>
        </Section>

        {/* RAG pipeline */}
        <Section kicker="Retrieval" title="6-pattern RAG pipeline">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {RAG.map((p) => (
              <div key={p.n} className="card card-hover p-5">
                <div className="badge-cyan">{p.n}</div>
                <p className="muted text-sm mt-3">{p.d}</p>
              </div>
            ))}
          </div>
          <p className="muted text-sm mt-4">
            Cached with <span className="text-neon-cyan font-mono">@lru_cache</span> · vectors in Qdrant ·
            embeddings via local <span className="font-mono">all-MiniLM-L6-v2</span> (384-dim, CPU, free).
          </p>
        </Section>

        {/* Tech stack */}
        <Section kicker="Built on" title="Tech stack — 100% free">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STACK.map((s) => (
              <div key={s.layer} className="card card-hover p-5">
                <h3 className={`font-bold text-${s.color}`}>{s.layer}</h3>
                <ul className="mt-3 space-y-1.5">
                  {s.items.map((it) => (
                    <li key={it} className="muted text-sm flex items-center gap-2">
                      <span className={`h-1.5 w-1.5 rounded-full bg-${s.color}`} />
                      {it}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>

        <div className="mt-16 card p-8 text-center bg-brand-soft">
          <h2 className="text-2xl font-bold">Ready to see it live?</h2>
          <p className="muted mt-2">Log in as a student, teacher, parent, or admin.</p>
          <Link href="/" className="btn-primary mt-5">Open the app →</Link>
        </div>
      </div>
    </div>
  );
}
