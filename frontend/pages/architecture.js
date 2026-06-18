import Link from "next/link";
import ThemeToggle from "../components/ThemeToggle";

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

/* ── Workflow graph (connected-node "aero" diagram) ─────────────────────────── */
const NODE_W = 158;
const NODE_H = 58;

// Each node positioned in a lane (column) by top-left x/y in SVG space.
const NODES = {
  user:      { x: 16,   y: 286, icon: "🧑", label: "User",            sub: "4 roles",            accent: "#22d3ee" },
  api:       { x: 206,  y: 286, icon: "⚡", label: "FastAPI Gateway",  sub: "JWT auth",           accent: "#7c5cff" },
  sup:       { x: 406,  y: 150, icon: "🧠", label: "LangGraph",        sub: "supervisor · routes", accent: "#a78bfa" },
  scheduler: { x: 406,  y: 446, icon: "⏰", label: "Scheduler",        sub: "nightly · Sunday",   accent: "#fbbf24" },

  doubt:     { x: 646,  y: 40,  icon: "💬", label: "Doubt Agent",      sub: "text/voice/photo",   accent: "#22d3ee" },
  testgen:   { x: 646,  y: 146, icon: "📝", label: "Test Generator",   sub: "weak-concept aimed", accent: "#7c5cff" },
  eval:      { x: 646,  y: 300, icon: "✅", label: "Answer Evaluator", sub: "on test submit",     accent: "#34d399" },
  atrisk:    { x: 646,  y: 424, icon: "🚨", label: "At-Risk Detector", sub: "dropout scorer",     accent: "#fb7185" },
  parent:    { x: 646,  y: 524, icon: "📨", label: "Parent Reporter",  sub: "LLM-written",        accent: "#fbbf24" },

  rag:       { x: 886,  y: 40,  icon: "🔎", label: "RAG Pipeline",     sub: "6 patterns · Qdrant", accent: "#22d3ee" },
  reviewer:  { x: 886,  y: 146, icon: "🔁", label: "Reviewer Loop",    sub: "quality gate",       accent: "#a78bfa" },
  hitl:      { x: 886,  y: 232, icon: "🧑‍🏫", label: "Teacher Approval", sub: "human-in-the-loop",  accent: "#34d399" },
  fanout:    { x: 886,  y: 318, icon: "🗂️", label: "Parallel fan-out", sub: "Progress·Rank·Cards", accent: "#34d399" },

  llm:       { x: 1066, y: 70,  icon: "🤖", label: "LLM",             sub: "Groq → Gemini",      accent: "#fb7185" },
  db:        { x: 1066, y: 430, icon: "💾", label: "Supabase",        sub: "Postgres · pgvector", accent: "#fbbf24" },
};

// Lane captions across the top.
const LANES = [
  { x: 16,   label: "Client" },
  { x: 206,  label: "Gateway" },
  { x: 406,  label: "Orchestration" },
  { x: 646,  label: "AI Agents" },
  { x: 886,  label: "Services" },
  { x: 1066, label: "LLM & Data" },
];

// f/t = node ids, fs/ts = anchor side (l/r/t/b). flow = animated packet.
const EDGES = [
  { f: "user", fs: "r", t: "api", ts: "l", flow: true },
  { f: "api", fs: "r", t: "sup", ts: "l", flow: true },
  { f: "sup", fs: "r", t: "doubt", ts: "l", flow: true },
  { f: "sup", fs: "r", t: "testgen", ts: "l" },
  { f: "sup", fs: "r", t: "eval", ts: "l" },
  { f: "doubt", fs: "r", t: "rag", ts: "l", flow: true },
  { f: "rag", fs: "r", t: "llm", ts: "l", flow: true },
  { f: "testgen", fs: "r", t: "reviewer", ts: "l" },
  { f: "reviewer", fs: "t", t: "testgen", ts: "t", kind: "loop", color: "#a78bfa", marker: "arrowViolet", dash: true, label: "≤3×" },
  { f: "reviewer", fs: "b", t: "hitl", ts: "t", kind: "v" },
  { f: "hitl", fs: "r", t: "db", ts: "l", color: "#34d399", marker: "arrowGreen", label: "approved" },
  { f: "eval", fs: "r", t: "fanout", ts: "l" },
  { f: "fanout", fs: "r", t: "db", ts: "l" },
  { f: "scheduler", fs: "r", t: "atrisk", ts: "l", color: "#fbbf24", marker: "arrowAmber", dash: true },
  { f: "scheduler", fs: "r", t: "parent", ts: "l", color: "#fbbf24", marker: "arrowAmber", dash: true },
  { f: "atrisk", fs: "r", t: "db", ts: "l" },
  { f: "parent", fs: "r", t: "db", ts: "l" },
];

const LEGEND = [
  { c: "#7c5cff", label: "Request flow", dash: false },
  { c: "#a78bfa", label: "Reviewer loop (≤3×)", dash: true },
  { c: "#fbbf24", label: "Scheduled (cron)", dash: true },
  { c: "#34d399", label: "Human approval", dash: false },
];

/* ── Small building blocks ──────────────────────────────────────────────────── */
function Section({ kicker, title, children }) {
  return (
    <section className="mt-14">
      <p className="text-xs font-semibold uppercase tracking-widest text-cyan-600 dark:text-neon-cyan/80">{kicker}</p>
      <h2 className="text-2xl font-bold tracking-tight mt-1 mb-5">{title}</h2>
      {children}
    </section>
  );
}

/* ── Connected-node workflow diagram ────────────────────────────────────────── */
function anchor(id, side) {
  const n = NODES[id];
  const cx = n.x + NODE_W / 2;
  const cy = n.y + NODE_H / 2;
  if (side === "r") return [n.x + NODE_W, cy];
  if (side === "l") return [n.x, cy];
  if (side === "t") return [cx, n.y];
  return [cx, n.y + NODE_H]; // "b"
}

function edgePath(e) {
  const [x1, y1] = anchor(e.f, e.fs);
  const [x2, y2] = anchor(e.t, e.ts);
  if (e.kind === "loop") {
    const lift = 44;
    return `M${x1},${y1} C${x1},${y1 - lift} ${x2},${y2 - lift} ${x2},${y2}`;
  }
  if (e.kind === "v") {
    const dy = Math.abs(y2 - y1) / 2;
    return `M${x1},${y1} C${x1},${y1 + dy} ${x2},${y2 - dy} ${x2},${y2}`;
  }
  const dx = Math.max(40, Math.abs(x2 - x1) / 2);
  return `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`;
}

function edgeLabelPos(e) {
  const [x1, y1] = anchor(e.f, e.fs);
  const [x2, y2] = anchor(e.t, e.ts);
  if (e.kind === "loop") return [(x1 + x2) / 2, Math.min(y1, y2) - 50];
  return [(x1 + x2) / 2, (y1 + y2) / 2 - 6];
}

function Marker({ id, color }) {
  return (
    <marker id={id} markerWidth="9" markerHeight="9" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse">
      <path d="M0,0 L8,4 L0,8 Z" fill={color} />
    </marker>
  );
}

function WorkflowDiagram() {
  return (
    <div className="card p-4 sm:p-6">
      <div className="overflow-x-auto">
        <svg viewBox="0 0 1240 600" className="w-full min-w-[920px]" role="img" aria-label="System workflow diagram">
          <defs>
            <linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#7c5cff" />
              <stop offset="100%" stopColor="#22d3ee" />
            </linearGradient>
            <filter id="dotGlow" x="-200%" y="-200%" width="500%" height="500%">
              <feGaussianBlur stdDeviation="2.5" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <Marker id="arrow" color="#7c5cff" />
            <Marker id="arrowViolet" color="#a78bfa" />
            <Marker id="arrowAmber" color="#fbbf24" />
            <Marker id="arrowGreen" color="#34d399" />
          </defs>

          {/* Lane captions */}
          {LANES.map((l) => (
            <text
              key={l.label}
              x={l.x + NODE_W / 2}
              y={18}
              textAnchor="middle"
              className="fill-slate-400 dark:fill-slate-500"
              style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase" }}
            >
              {l.label.toUpperCase()}
            </text>
          ))}

          {/* Edges */}
          {EDGES.map((e, i) => {
            const d = edgePath(e);
            const stroke = e.color || "url(#edge)";
            const marker = e.marker || "arrow";
            return (
              <g key={i}>
                <path
                  id={`edge-${i}`}
                  d={d}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={2}
                  strokeOpacity={0.85}
                  strokeDasharray={e.dash ? "6 5" : undefined}
                  markerEnd={`url(#${marker})`}
                />
                {e.flow && (
                  <circle r="3.5" fill="#22d3ee" filter="url(#dotGlow)">
                    <animateMotion dur="2.4s" begin={`${i * 0.35}s`} repeatCount="indefinite">
                      <mpath href={`#edge-${i}`} xlinkHref={`#edge-${i}`} />
                    </animateMotion>
                  </circle>
                )}
                {e.label && (() => {
                  const [lx, ly] = edgeLabelPos(e);
                  return (
                    <text
                      x={lx}
                      y={ly}
                      textAnchor="middle"
                      className="fill-slate-500 dark:fill-slate-300"
                      style={{ fontSize: 10, fontWeight: 600, paintOrder: "stroke" }}
                      stroke="rgba(255,255,255,0)"
                    >
                      {e.label}
                    </text>
                  );
                })()}
              </g>
            );
          })}

          {/* Nodes (HTML via foreignObject for crisp theming) */}
          {Object.entries(NODES).map(([id, n]) => (
            <foreignObject key={id} x={n.x} y={n.y} width={NODE_W} height={NODE_H}>
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                className="h-full w-full rounded-2xl border border-slate-200 dark:border-white/10 bg-white/90 dark:bg-ink-800/85 shadow-sm flex items-center gap-2.5 px-2.5 overflow-hidden"
                style={{ borderLeft: `3px solid ${n.accent}`, backdropFilter: "blur(6px)" }}
              >
                <span
                  className="grid place-items-center h-8 w-8 rounded-lg text-base shrink-0"
                  style={{ background: `${n.accent}22` }}
                >
                  {n.icon}
                </span>
                <span className="min-w-0">
                  <span className="block text-[12px] font-semibold leading-tight truncate text-slate-800 dark:text-slate-100">
                    {n.label}
                  </span>
                  <span className="block text-[10px] leading-tight truncate text-slate-500 dark:text-slate-400">
                    {n.sub}
                  </span>
                </span>
              </div>
            </foreignObject>
          ))}
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-4 pt-4 border-t border-slate-200 dark:border-white/10">
        {LEGEND.map((l) => (
          <span key={l.label} className="flex items-center gap-2 text-xs muted">
            <svg width="26" height="8">
              <line
                x1="0"
                y1="4"
                x2="26"
                y2="4"
                stroke={l.c}
                strokeWidth="2.5"
                strokeDasharray={l.dash ? "5 4" : undefined}
              />
            </svg>
            {l.label}
          </span>
        ))}
        <span className="flex items-center gap-2 text-xs muted">
          <span className="h-2 w-2 rounded-full bg-neon-cyan shadow-glow-cyan" /> live data packet
        </span>
      </div>
    </div>
  );
}

export default function Architecture() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/80 dark:border-white/10 dark:bg-ink-950/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid place-items-center h-8 w-8 rounded-xl bg-brand-grad text-white shadow-glow">🎓</span>
            <span className="font-bold tracking-tight">Smart<span className="grad-text">Coaching</span></span>
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/" className="btn-ghost text-sm">← Back to app</Link>
            <ThemeToggle />
          </div>
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

        {/* Request flow — connected-node workflow */}
        <Section kicker="End to end" title="System workflow">
          <WorkflowDiagram />
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
                <span className="absolute -right-3 -top-3 text-6xl font-black text-slate-900/5 dark:text-white/5 select-none">{i + 1}</span>
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
