import { useState } from "react";
import Link from "next/link";
import ThemeToggle from "../components/ThemeToggle";
import {
  MessageCircle, Target, FileText, AlertTriangle, TrendingUp, Layers,
  Mail, LayoutDashboard, GraduationCap, Users, ArrowRight, Check,
  ShieldCheck, Sparkles, Menu, X,
} from "lucide-react";

const NAV = [
  { href: "#features", label: "Features" },
  { href: "#who", label: "Who it's for" },
  { href: "#how", label: "How it works" },
  { href: "/architecture", label: "Architecture" },
];

const STATS = [
  { value: "8", label: "AI agents, always on" },
  { value: "₹0", label: "Infrastructure cost" },
  { value: "7 days", label: "Earlier dropout warning" },
  { value: "24/7", label: "Doubt resolution" },
];

const FEATURES = [
  { icon: MessageCircle, title: "24/7 Doubt Agent", text: "Grounded answers from NCERT and your institute's own notes — by text, voice or photo." },
  { icon: Target, title: "Concept Weakness Map", text: "Granular per-student mastery — 'integration by parts', not just 'Calculus'." },
  { icon: FileText, title: "Personalised Tests", text: "AI drafts and self-reviews questions aimed precisely at each student's gaps." },
  { icon: AlertTriangle, title: "At-Risk Detection", text: "Nightly engagement scoring flags a likely dropout up to seven days early." },
  { icon: TrendingUp, title: "AIR Rank Tracking", text: "A predicted All-India Rank that updates with every test a student attempts." },
  { icon: Layers, title: "Spaced Revision", text: "Auto-generated flashcards resurface a concept right before it fades." },
  { icon: Mail, title: "Weekly Parent Reports", text: "A plain-language WhatsApp and email summary every Sunday, written by AI." },
  { icon: LayoutDashboard, title: "Teacher Dashboard", text: "A live class heatmap, the hottest doubts, and at-risk alerts in one view." },
];

const ROLES = [
  {
    icon: GraduationCap,
    title: "Students",
    points: ["Ask doubts anytime — type, speak or snap a photo", "Practice tests tuned to weak spots", "Track streaks, XP and predicted rank"],
  },
  {
    icon: Users,
    title: "Teachers",
    points: ["See the whole class's mastery at a glance", "Generate and approve tests in seconds", "Get alerted before a student drops off"],
  },
  {
    icon: Mail,
    title: "Parents",
    points: ["A plain-language weekly progress note", "Scores, doubts and focus areas", "Delivered automatically, every Sunday"],
  },
];

const STEPS = [
  { n: "1", title: "Set up your institute", text: "Create an account and add your students in minutes — there's no infrastructure to manage." },
  { n: "2", title: "The agents get to work", text: "Eight specialised agents handle doubts, tests, tracking and reports around the clock." },
  { n: "3", title: "Everyone stays ahead", text: "Students improve, teachers focus where it counts, and parents stay informed automatically." },
];

export default function Home() {
  const [menu, setMenu] = useState(false);

  return (
    <div className="min-h-screen">
      {/* ── Navbar ───────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b hairline bg-white/80 dark:bg-ink-950/70 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid place-items-center h-8 w-8 rounded-lg bg-brand text-white"><GraduationCap size={17} /></span>
            <span className="font-semibold tracking-tight text-[15px]">
              Smart<span className="text-brand dark:text-indigo-400">Coaching</span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-7 text-sm muted">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} className="hover:text-slate-900 dark:hover:text-white transition">{n.label}</a>
            ))}
          </nav>

          <div className="flex items-center gap-1.5">
            <Link href="/login" className="btn-ghost text-sm hidden sm:inline-flex">Log in</Link>
            <Link href="/login?mode=signup" className="btn-primary text-sm">Get started</Link>
            <ThemeToggle />
            <button onClick={() => setMenu((v) => !v)} className="btn-ghost px-2 md:hidden" aria-label="Menu">
              {menu ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>

        {menu && (
          <div className="md:hidden border-t hairline bg-white dark:bg-ink-950 px-6 py-3 space-y-1">
            {NAV.map((n) => (
              <a key={n.href} href={n.href} onClick={() => setMenu(false)} className="block py-2 text-sm muted">{n.label}</a>
            ))}
          </div>
        )}
      </header>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <section className="hero-bg border-b hairline">
        <div className="max-w-6xl mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center pt-14 lg:pt-20 pb-16">
          <div>
            <span className="badge-brand mb-5">
              <Sparkles size={13} /> AI-powered · JEE / NEET · ₹0 infrastructure
            </span>
            <h1 className="text-4xl md:text-5xl font-bold leading-[1.1] tracking-tight">
              One teacher can't coach 50 students personally.
              <span className="text-brand dark:text-indigo-400"> Eight AI agents can.</span>
            </h1>
            <p className="muted mt-6 text-lg max-w-xl">
              SmartCoaching gives every student a personal AI tutor — 24/7 doubt solving,
              weakness-targeted tests, live rank tracking and automatic parent reports —
              all in one platform built for coaching institutes.
            </p>

            <div className="flex flex-wrap items-center gap-3 mt-8">
              <Link href="/login?mode=signup" className="btn-primary px-6 py-3 text-base">
                Get started free <ArrowRight size={18} />
              </Link>
              <a href="#features" className="btn-ghost px-6 py-3 text-base">Explore features</a>
            </div>

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-7 text-sm muted">
              <span className="flex items-center gap-2"><Check size={15} className="text-emerald-600" /> No credit card required</span>
              <span className="flex items-center gap-2"><ShieldCheck size={15} className="text-brand" /> Accounts ready instantly</span>
            </div>
          </div>

          {/* Product preview */}
          <div className="lg:justify-self-end w-full max-w-md">
            <DashboardPreview />
          </div>
        </div>
      </section>

      {/* ── Stats band ───────────────────────────────────────────── */}
      <section className="border-b hairline bg-white/60 dark:bg-white/[0.02]">
        <div className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-2 lg:grid-cols-4 gap-8 text-center">
          {STATS.map((s) => (
            <div key={s.label}>
              <p className="text-3xl font-bold tracking-tight text-brand dark:text-indigo-400">{s.value}</p>
              <p className="muted text-sm mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────── */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-20 scroll-mt-20">
        <div className="max-w-2xl">
          <span className="badge-brand mb-4">Features</span>
          <h2 className="text-3xl font-bold tracking-tight">Eight specialised agents, one platform</h2>
          <p className="muted mt-4 text-lg">
            Everything a coaching institute needs to teach every student personally — without hiring an army.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-12">
          {FEATURES.map((f) => (
            <div key={f.title} className="card card-hover p-5">
              <span className="icon-tile h-11 w-11"><f.icon size={20} strokeWidth={2} /></span>
              <p className="font-semibold mt-4">{f.title}</p>
              <p className="muted text-sm mt-1.5 leading-relaxed">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Who it's for ─────────────────────────────────────────── */}
      <section id="who" className="bg-white/60 dark:bg-white/[0.02] border-y hairline scroll-mt-20">
        <div className="max-w-6xl mx-auto px-6 py-20">
          <div className="max-w-2xl">
            <span className="badge-brand mb-4">Who it's for</span>
            <h2 className="text-3xl font-bold tracking-tight">Built for everyone in the journey</h2>
            <p className="muted mt-4 text-lg">Students, teachers and parents each get a focused, purpose-built experience.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-5 mt-12">
            {ROLES.map((r) => (
              <div key={r.title} className="card card-hover p-6">
                <div className="flex items-center gap-3">
                  <span className="icon-tile h-11 w-11"><r.icon size={20} strokeWidth={2} /></span>
                  <span className="font-semibold">{r.title}</span>
                </div>
                <ul className="mt-5 space-y-3">
                  {r.points.map((p) => (
                    <li key={p} className="flex items-start gap-2.5 text-sm">
                      <Check size={16} className="text-brand dark:text-indigo-400 mt-0.5 shrink-0" />
                      <span className="text-slate-600 dark:text-slate-300">{p}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────── */}
      <section id="how" className="max-w-6xl mx-auto px-6 py-20 scroll-mt-20">
        <div className="max-w-2xl">
          <span className="badge-brand mb-4">How it works</span>
          <h2 className="text-3xl font-bold tracking-tight">Up and running in three steps</h2>
        </div>

        <div className="grid md:grid-cols-3 gap-5 mt-12">
          {STEPS.map((s) => (
            <div key={s.n} className="card p-6">
              <span className="grid place-items-center h-10 w-10 rounded-xl bg-brand text-white font-semibold">{s.n}</span>
              <p className="font-semibold mt-4 text-lg">{s.title}</p>
              <p className="muted text-sm mt-1.5 leading-relaxed">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA band ─────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pb-20">
        <div className="rounded-3xl bg-brand p-10 md:p-14 text-center text-white">
          <h2 className="text-3xl font-bold tracking-tight">Ready to teach every student personally?</h2>
          <p className="mt-4 text-white/85 text-lg max-w-xl mx-auto">
            Spin up your institute in minutes. No infrastructure, no credit card, no setup fees.
          </p>
          <Link
            href="/login?mode=signup"
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white text-brand font-semibold px-7 py-3 text-base shadow hover:bg-slate-50 transition"
          >
            Get started free <ArrowRight size={18} />
          </Link>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────── */}
      <footer className="border-t hairline">
        <div className="max-w-6xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="grid place-items-center h-7 w-7 rounded-lg bg-brand text-white"><GraduationCap size={15} /></span>
            <span className="font-semibold">Smart<span className="text-brand dark:text-indigo-400">Coaching</span></span>
          </div>
          <div className="flex items-center gap-6 text-sm muted">
            <a href="#features" className="hover:text-brand transition">Features</a>
            <a href="#who" className="hover:text-brand transition">Who it's for</a>
            <Link href="/architecture" className="hover:text-brand transition">Architecture</Link>
            <Link href="/login" className="hover:text-brand transition">Log in</Link>
          </div>
          <p className="muted text-xs">© {new Date().getFullYear()} SmartCoaching</p>
        </div>
      </footer>
    </div>
  );
}

// A small, static mock of the student dashboard — gives the hero a premium
// product feel and shows at a glance what the platform actually does.
function DashboardPreview() {
  const tiles = [
    { label: "Mastery", value: "78%", icon: Target },
    { label: "Predicted AIR", value: "4,210", icon: TrendingUp },
    { label: "Day streak", value: "12", icon: Sparkles },
  ];
  const agents = [
    { name: "Doubt Agent", note: "answered 3 questions", color: "bg-emerald-500" },
    { name: "Test Generator", note: "2 tests ready to review", color: "bg-brand" },
    { name: "At-Risk Detector", note: "all students on track", color: "bg-amber-500" },
  ];
  return (
    <div className="card p-4 shadow-soft-lg">
      {/* window chrome */}
      <div className="flex items-center gap-1.5 px-1 pb-3 border-b hairline">
        <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
        <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
        <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
        <span className="ml-2 text-xs muted">Student dashboard</span>
      </div>

      <div className="grid grid-cols-3 gap-2.5 mt-3">
        {tiles.map((t) => (
          <div key={t.label} className="panel p-2.5">
            <t.icon size={15} className="text-brand dark:text-indigo-400" />
            <p className="text-lg font-bold tracking-tight mt-1.5 tabular-nums">{t.value}</p>
            <p className="text-[10px] uppercase tracking-wider muted">{t.label}</p>
          </div>
        ))}
      </div>

      <p className="text-[11px] font-semibold uppercase tracking-wider muted mt-4 mb-2">Agent activity</p>
      <div className="space-y-2">
        {agents.map((a) => (
          <div key={a.name} className="panel flex items-center gap-3 p-2.5">
            <span className={`h-2 w-2 rounded-full ${a.color}`} />
            <span className="text-sm font-medium">{a.name}</span>
            <span className="text-xs muted ml-auto">{a.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
