import Link from "next/link";
import ThemeToggle from "../components/ThemeToggle";
import {
  GraduationCap, Users, Mail, Building2, ArrowRight, ArrowLeft,
  MessageCircle, FileText, CheckCircle2, AlertTriangle, RefreshCw,
  Search, UserCheck, Share2, Cpu, Database, Clock, Server, Workflow,
  TrendingUp, Layers,
} from "lucide-react";

/* ── Palette (matches the app's clean indigo theme) ─────────────────────────── */
const C = {
  brand: "#4f46e5",   // indigo — request flow
  loop: "#6366f1",    // lighter indigo — reviewer loop
  sched: "#f59e0b",   // amber — scheduled jobs
  ok: "#10b981",      // emerald — approval / grading
  risk: "#ef4444",    // rose — at-risk
  slate: "#64748b",   // data
};

/* ── Content (reflects the current working app) ─────────────────────────────── */
const STATS = [
  { v: "10", l: "AI agents" },
  { v: "6", l: "RAG patterns" },
  { v: "4", l: "User roles" },
  { v: "₹0", l: "Monthly cost" },
];

const ROLES = [
  { icon: GraduationCap, name: "Student", color: C.brand, points: ["24/7 doubts — text / voice / photo", "Takes assigned MCQ & theory tests", "Mastery map, streak, XP, flashcards"] },
  { icon: Users, name: "Teacher", color: C.ok, points: ["Class KPIs, at-risk alerts, heatmap", "Student roster + submitted results", "Generates, edits marks & approves tests"] },
  { icon: Mail, name: "Parent", color: C.sched, points: ["Weekly progress summary per child", "Scores, doubts asked, focus areas", "Recent test results — automatic"] },
  { icon: Building2, name: "Institute Admin", color: C.loop, points: ["Active students & engagement rate", "Weekly engagement + account counts", "Student records & all test results"] },
];

const AGENTS = [
  { n: "Doubt Agent", d: "Answers text / voice / photo doubts from RAG (NCERT + notes)." },
  { n: "Test Generator", d: "Builds MCQ or theory questions targeting weak concepts." },
  { n: "Reviewer Agent", d: "Quality gate — loops the generator up to 3× before approval." },
  { n: "Answer Evaluator", d: "MCQ scoring + AI grading of written answers + handwriting vision." },
  { n: "Progress Tracker", d: "Updates the concept-level weakness map after each test." },
  { n: "Rank Predictor", d: "Estimates All-India Rank after every test." },
  { n: "Flashcard Agent", d: "Creates SM-2 spaced-repetition cards from weak concepts." },
  { n: "At-Risk Detector", d: "Nightly engagement scoring — flags likely dropouts early." },
  { n: "Parent Reporter", d: "Builds each parent's weekly progress summary." },
  { n: "Study Plan Agent", d: "Refreshes student study plans weekly." },
];

const RAG = [
  { n: "1 · Agentic", d: "LLM plans 2–4 targeted sub-queries." },
  { n: "2 · CRAG gate", d: "Scores relevance; weak results trigger a fallback." },
  { n: "3 · HyDE", d: "Hypothetical answer → embed → search." },
  { n: "4 · RAPTOR", d: "Picks chunk vs chapter-summary level." },
  { n: "5 · Web fallback", d: "Search over .edu / NCERT domains when needed." },
  { n: "6 · CrossEncoder", d: "Re-ranks results by student level." },
];

const STACK = [
  { layer: "Frontend", color: C.brand, items: ["Next.js 14", "Tailwind CSS", "Recharts", "Supabase JS"] },
  { layer: "Backend", color: C.loop, items: ["FastAPI", "LangGraph", "APScheduler", "BackgroundTasks"] },
  { layer: "LLMs (free)", color: C.ok, items: ["Groq Llama-3.3-70B", "Gemini 2.5 Flash", "OpenRouter", "Gemini Vision"] },
  { layer: "Data & Vectors", color: C.sched, items: ["Supabase Postgres", "pgvector", "Qdrant Cloud", "MiniLM embeds"] },
];

/* ── Workflow diagram ───────────────────────────────────────────────────────── */
const NODE_W = 158;
const NODE_H = 58;

const NODES = {
  user:      { x: 16,   y: 286, Icon: Users,        label: "User",            sub: "4 roles",            accent: C.brand },
  api:       { x: 206,  y: 286, Icon: Server,       label: "FastAPI",         sub: "Supabase Auth · JWT", accent: C.brand },
  sup:       { x: 406,  y: 150, Icon: Workflow,     label: "LangGraph",       sub: "supervisor · routes", accent: C.loop },
  scheduler: { x: 406,  y: 446, Icon: Clock,        label: "Scheduler",       sub: "nightly · weekly",   accent: C.sched },

  doubt:     { x: 646,  y: 40,  Icon: MessageCircle, label: "Doubt Agent",     sub: "text / voice / photo", accent: C.brand },
  testgen:   { x: 646,  y: 146, Icon: FileText,      label: "Test Generator",  sub: "MCQ / theory",        accent: C.brand },
  eval:      { x: 646,  y: 300, Icon: CheckCircle2,  label: "Answer Evaluator", sub: "MCQ + theory grading", accent: C.ok },
  atrisk:    { x: 646,  y: 424, Icon: AlertTriangle, label: "At-Risk Detector", sub: "dropout scorer",      accent: C.risk },
  parent:    { x: 646,  y: 524, Icon: Mail,          label: "Parent Reporter",  sub: "weekly summary",      accent: C.sched },

  rag:       { x: 886,  y: 40,  Icon: Search,       label: "RAG Pipeline",    sub: "6 patterns · Qdrant", accent: C.loop },
  reviewer:  { x: 886,  y: 146, Icon: RefreshCw,    label: "Reviewer Loop",   sub: "quality gate ≤3×",   accent: C.loop },
  hitl:      { x: 886,  y: 232, Icon: UserCheck,    label: "Teacher Approval", sub: "set marks · approve", accent: C.ok },
  fanout:    { x: 886,  y: 318, Icon: Share2,       label: "Post-test fan-out", sub: "progress · rank · cards", accent: C.ok },

  llm:       { x: 1066, y: 70,  Icon: Cpu,          label: "LLM",             sub: "Groq → Gemini",      accent: C.brand },
  db:        { x: 1066, y: 430, Icon: Database,     label: "Supabase",        sub: "Postgres · pgvector", accent: C.slate },
};

const LANES = [
  { x: 16,   label: "Client" },
  { x: 206,  label: "Gateway" },
  { x: 406,  label: "Orchestration" },
  { x: 646,  label: "AI Agents" },
  { x: 886,  label: "Services" },
  { x: 1066, label: "LLM & Data" },
];

const EDGES = [
  { f: "user", fs: "r", t: "api", ts: "l", flow: true },
  { f: "api", fs: "r", t: "sup", ts: "l", flow: true },
  { f: "sup", fs: "r", t: "doubt", ts: "l", flow: true },
  { f: "sup", fs: "r", t: "testgen", ts: "l" },
  { f: "sup", fs: "r", t: "eval", ts: "l" },
  { f: "doubt", fs: "r", t: "rag", ts: "l", flow: true },
  { f: "rag", fs: "r", t: "llm", ts: "l", flow: true },
  { f: "testgen", fs: "r", t: "reviewer", ts: "l" },
  { f: "reviewer", fs: "t", t: "testgen", ts: "t", kind: "loop", color: C.loop, marker: "arrowLoop", dash: true, label: "≤3×" },
  { f: "reviewer", fs: "b", t: "hitl", ts: "t", kind: "v" },
  { f: "hitl", fs: "r", t: "db", ts: "l", color: C.ok, marker: "arrowOk", label: "ready" },
  { f: "eval", fs: "r", t: "fanout", ts: "l" },
  { f: "fanout", fs: "r", t: "db", ts: "l" },
  { f: "scheduler", fs: "r", t: "atrisk", ts: "l", color: C.sched, marker: "arrowSched", dash: true },
  { f: "scheduler", fs: "r", t: "parent", ts: "l", color: C.sched, marker: "arrowSched", dash: true },
  { f: "atrisk", fs: "r", t: "db", ts: "l" },
  { f: "parent", fs: "r", t: "db", ts: "l" },
];

const LEGEND = [
  { c: C.brand, label: "Request flow", dash: false },
  { c: C.loop, label: "Reviewer loop (≤3×)", dash: true },
  { c: C.sched, label: "Scheduled (cron)", dash: true },
  { c: C.ok, label: "Approval / grading", dash: false },
];

function Section({ kicker, title, children }) {
  return (
    <section className="mt-14">
      <p className="text-xs font-semibold uppercase tracking-widest text-brand dark:text-indigo-400">{kicker}</p>
      <h2 className="text-2xl font-bold tracking-tight mt-1 mb-5">{title}</h2>
      {children}
    </section>
  );
}

function anchor(id, side) {
  const n = NODES[id];
  const cx = n.x + NODE_W / 2;
  const cy = n.y + NODE_H / 2;
  if (side === "r") return [n.x + NODE_W, cy];
  if (side === "l") return [n.x, cy];
  if (side === "t") return [cx, n.y];
  return [cx, n.y + NODE_H];
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
            <filter id="dotGlow" x="-200%" y="-200%" width="500%" height="500%">
              <feGaussianBlur stdDeviation="2.2" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <Marker id="arrow" color={C.brand} />
            <Marker id="arrowLoop" color={C.loop} />
            <Marker id="arrowSched" color={C.sched} />
            <Marker id="arrowOk" color={C.ok} />
          </defs>

          {LANES.map((l) => (
            <text
              key={l.label}
              x={l.x + NODE_W / 2}
              y={18}
              textAnchor="middle"
              className="fill-slate-400 dark:fill-slate-500"
              style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.5 }}
            >
              {l.label.toUpperCase()}
            </text>
          ))}

          {EDGES.map((e, i) => {
            const d = edgePath(e);
            const stroke = e.color || C.brand;
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
                  <circle r="3.5" fill={C.brand} filter="url(#dotGlow)">
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
                      style={{ fontSize: 10, fontWeight: 600 }}
                    >
                      {e.label}
                    </text>
                  );
                })()}
              </g>
            );
          })}

          {Object.entries(NODES).map(([id, n]) => (
            <foreignObject key={id} x={n.x} y={n.y} width={NODE_W} height={NODE_H}>
              <div
                xmlns="http://www.w3.org/1999/xhtml"
                className="h-full w-full rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-ink-800/85 shadow-soft flex items-center gap-2.5 px-2.5 overflow-hidden"
                style={{ borderLeft: `3px solid ${n.accent}` }}
              >
                <span
                  className="grid place-items-center h-8 w-8 rounded-lg shrink-0"
                  style={{ background: `${n.accent}1f`, color: n.accent }}
                >
                  <n.Icon size={16} />
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

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-4 pt-4 border-t border-slate-200 dark:border-white/10">
        {LEGEND.map((l) => (
          <span key={l.label} className="flex items-center gap-2 text-xs muted">
            <svg width="26" height="8">
              <line x1="0" y1="4" x2="26" y2="4" stroke={l.c} strokeWidth="2.5" strokeDasharray={l.dash ? "5 4" : undefined} />
            </svg>
            {l.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function Architecture() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b hairline bg-white/80 dark:bg-ink-950/80 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid place-items-center h-8 w-8 rounded-lg bg-brand text-white"><GraduationCap size={17} /></span>
            <span className="font-semibold tracking-tight">Smart<span className="text-brand dark:text-indigo-400">Coaching</span></span>
          </Link>
          <div className="flex items-center gap-2">
            <Link href="/" className="btn-ghost text-sm"><ArrowLeft size={15} /> Back to app</Link>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-5 pb-24">
        {/* Hero */}
        <div className="pt-12 pb-2">
          <span className="badge-brand">System Architecture</span>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tight mt-4 max-w-3xl">
            How <span className="text-brand dark:text-indigo-400">SmartCoaching</span> is built
          </h1>
          <p className="muted mt-4 max-w-2xl text-lg">
            An agentic tutoring platform on a free stack — FastAPI + LangGraph orchestration,
            a 6-pattern RAG pipeline over Qdrant, and specialised AI agents per task.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-8">
            {STATS.map((s) => (
              <div key={s.l} className="card p-5 text-center card-hover">
                <div className="text-3xl font-bold text-brand dark:text-indigo-400">{s.v}</div>
                <div className="muted text-xs mt-1">{s.l}</div>
              </div>
            ))}
          </div>
        </div>

        <Section kicker="End to end" title="System workflow">
          <WorkflowDiagram />
        </Section>

        <Section kicker="Who uses it" title="Four user roles">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {ROLES.map((r) => (
              <div key={r.name} className="card card-hover p-5">
                <span className="grid place-items-center h-11 w-11 rounded-xl" style={{ background: `${r.color}1f`, color: r.color }}>
                  <r.icon size={20} />
                </span>
                <h3 className="font-semibold mt-3">{r.name}</h3>
                <ul className="mt-3 space-y-1.5">
                  {r.points.map((p) => (
                    <li key={p} className="muted text-sm flex gap-2">
                      <span style={{ color: r.color }}>•</span>{p}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>

        <Section kicker="The brains" title="Ten AI agents">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {AGENTS.map((a, i) => (
              <div key={a.n} className="card card-hover p-5 relative overflow-hidden">
                <span className="absolute -right-3 -top-3 text-6xl font-black text-slate-900/5 dark:text-white/5 select-none">{i + 1}</span>
                <h3 className="font-semibold text-sm">{a.n}</h3>
                <p className="muted text-sm mt-2">{a.d}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section kicker="How a test flows" title="Generate → review → grade → results">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              { i: FileText, t: "1 · Generate", d: "Teacher enters a student email, picks MCQ or theory; AI drafts weakness-targeted questions." },
              { i: RefreshCw, t: "2 · Self-review", d: "Reviewer agent loops the generator up to 3× until the set passes quality." },
              { i: UserCheck, t: "3 · Approve", d: "Teacher edits questions, sets marks per question, then approves — test goes 'ready'." },
              { i: CheckCircle2, t: "4 · Take & grade", d: "Student submits; MCQ scored with negative marking, theory graded by AI vs the model answer." },
              { i: Share2, t: "5 · Fan-out", d: "Progress map, rank prediction and flashcards update from the result." },
              { i: TrendingUp, t: "6 · Results", d: "Score shows on the student, teacher, parent and admin dashboards." },
            ].map((s) => (
              <div key={s.t} className="card p-5">
                <span className="icon-tile h-10 w-10"><s.i size={18} /></span>
                <h3 className="font-semibold text-sm mt-3">{s.t}</h3>
                <p className="muted text-sm mt-1.5">{s.d}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section kicker="Retrieval" title="6-pattern RAG pipeline">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {RAG.map((p) => (
              <div key={p.n} className="card card-hover p-5">
                <div className="badge-brand">{p.n}</div>
                <p className="muted text-sm mt-3">{p.d}</p>
              </div>
            ))}
          </div>
          <p className="muted text-sm mt-4">
            Cached with <span className="font-mono">@lru_cache</span> · vectors in Qdrant ·
            embeddings via local <span className="font-mono">all-MiniLM-L6-v2</span> (384-dim, CPU).
          </p>
        </Section>

        <Section kicker="Automatic" title="Scheduled jobs">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { i: AlertTriangle, t: "Nightly", d: "At-risk detector scores engagement and flags dropouts." },
              { i: Mail, t: "Weekly", d: "Parent reporter builds each parent's summary." },
              { i: Layers, t: "Weekly", d: "Study plan agent refreshes student plans." },
              { i: Clock, t: "Periodic", d: "Flashcard review reminders." },
            ].map((s) => (
              <div key={s.t + s.d} className="card p-5">
                <span className="icon-tile h-10 w-10"><s.i size={18} /></span>
                <h3 className="font-semibold text-sm mt-3">{s.t}</h3>
                <p className="muted text-sm mt-1.5">{s.d}</p>
              </div>
            ))}
          </div>
        </Section>

        <Section kicker="Built on" title="Tech stack — free">
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {STACK.map((s) => (
              <div key={s.layer} className="card card-hover p-5">
                <h3 className="font-semibold" style={{ color: s.color }}>{s.layer}</h3>
                <ul className="mt-3 space-y-1.5">
                  {s.items.map((it) => (
                    <li key={it} className="muted text-sm flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: s.color }} />
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
          <Link href="/login" className="btn-primary mt-5">Open the app <ArrowRight size={16} /></Link>
        </div>
      </div>
    </div>
  );
}
