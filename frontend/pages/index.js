import { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { supabase } from "../lib/supabase";
import { api } from "../lib/api";
import ThemeToggle from "../components/ThemeToggle";

const ROLE_HOME = {
  student: "/student/doubt",
  teacher: "/teacher/dashboard",
  parent: "/parent/report",
  admin: "/admin/analytics",
};

const FEATURES = [
  { icon: "💬", title: "24/7 Doubt Agent", text: "RAG answers from NCERT + your institute notes — text, voice or photo." },
  { icon: "🎯", title: "Concept Weakness Map", text: "Granular per-student mastery — 'integration by parts', not just 'Calculus'." },
  { icon: "📝", title: "Personalised Tests", text: "AI drafts and self-reviews questions targeted at each student's gaps." },
  { icon: "🚨", title: "At-Risk Detection", text: "Nightly engagement scoring flags dropout 7 days early." },
  { icon: "📈", title: "AIR Rank Tracking", text: "Predicted All-India Rank that updates with every test attempt." },
  { icon: "🧠", title: "Spaced Revision", text: "Auto-generated flashcards resurface concepts right before they fade." },
  { icon: "📨", title: "Weekly Parent Reports", text: "Auto WhatsApp + email summary every Sunday, written by AI." },
  { icon: "🗺️", title: "Teacher Dashboard", text: "Live class heatmap, hot doubts, and at-risk alerts in one view." },
];

const ROLES = [
  {
    icon: "🎓",
    badge: "badge-cyan",
    title: "For Students",
    points: ["Ask doubts anytime — type, speak or snap a photo", "Practice tests tuned to your weak spots", "Track streaks, XP and predicted rank"],
  },
  {
    icon: "🧑‍🏫",
    badge: "badge-green",
    title: "For Teachers",
    points: ["See the whole class's mastery at a glance", "Generate & approve tests in seconds", "Get alerted before a student drops off"],
  },
  {
    icon: "👪",
    badge: "badge-amber",
    title: "For Parents",
    points: ["A plain-language weekly progress note", "Scores, doubts and focus areas", "Delivered automatically every Sunday"],
  },
];

const STEPS = [
  { n: "1", title: "Sign up your institute", text: "Create an account and add your students in minutes — no infra to manage." },
  { n: "2", title: "AI gets to work", text: "Eight agents handle doubts, tests, tracking and reports around the clock." },
  { n: "3", title: "Everyone stays ahead", text: "Students improve, teachers focus where it matters, parents stay informed." },
];

const STATS = [
  { value: "8", label: "AI agents working 24/7" },
  { value: "₹0", label: "Infrastructure cost" },
  { value: "7 days", label: "Earlier dropout warning" },
  { value: "100%", label: "Reports auto-generated" },
];

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "student", institute_id: "", parent_email: "" });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPw, setShowPw] = useState(false);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const redirectByRole = (role) => router.replace(ROLE_HOME[role] || "/student/doubt");

  function goToAuth(nextMode) {
    if (nextMode) setMode(nextMode);
    if (typeof document !== "undefined") {
      document.getElementById("get-started")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  async function ensureStudentProfile(user) {
    if (!user || user.user_metadata?.role !== "student") return;
    const { error } = await supabase.from("students").upsert(
      {
        auth_id: user.id,
        name: user.user_metadata?.name || user.email,
        email: user.email,
        institute_id: user.user_metadata?.institute_id || null,
        parent_email: user.user_metadata?.parent_email || null,
      },
      { onConflict: "auth_id" }
    );
    if (error) console.error("profile upsert failed:", error.message);
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      if (mode === "signup") {
        await api("/auth/signup", {
          method: "POST",
          body: {
            email: form.email,
            password: form.password,
            role: form.role,
            name: form.name,
            institute_id: form.institute_id || null,
            parent_email: form.role === "student" ? form.parent_email || null : null,
          },
        });
        const { data, error } = await supabase.auth.signInWithPassword({
          email: form.email,
          password: form.password,
        });
        if (error) throw error;
        redirectByRole(data.user?.user_metadata?.role);
      } else {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: form.email,
          password: form.password,
        });
        if (error) throw error;
        await ensureStudentProfile(data.user);
        redirectByRole(data.user?.user_metadata?.role);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      {/* ── Navbar ───────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-slate-200/70 dark:border-white/10 bg-white/70 dark:bg-ink-950/70 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid place-items-center h-8 w-8 rounded-xl bg-brand-grad text-white shadow-glow">🎓</span>
            <span className="font-bold tracking-tight text-lg">
              Smart<span className="grad-text">Coaching</span>
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-7 text-sm muted">
            <a href="#features" className="hover:text-brand transition">Features</a>
            <a href="#who" className="hover:text-brand transition">Who it's for</a>
            <a href="#how" className="hover:text-brand transition">How it works</a>
            <Link href="/architecture" className="hover:text-brand transition">Architecture</Link>
          </nav>

          <div className="flex items-center gap-2">
            <button onClick={() => goToAuth("login")} className="btn-ghost text-sm hidden sm:inline-flex">Log in</button>
            <button onClick={() => goToAuth("signup")} className="btn-primary text-sm">Get started</button>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <section className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center pt-12 lg:pt-20 pb-16">
        <div>
          <span className="badge-brand mb-5">AI-powered · JEE / NEET · ₹0 infra</span>
          <h1 className="text-4xl md:text-6xl font-extrabold leading-[1.05] tracking-tight">
            One teacher can't teach 50 students individually.
            <span className="grad-text"> Eight AI agents can.</span>
          </h1>
          <p className="muted mt-6 text-lg max-w-xl">
            A coaching platform where AI handles every student personally — 24/7 doubts,
            weakness-targeted tests, AIR rank tracking, and automatic parent reports.
          </p>

          <div className="flex flex-wrap items-center gap-3 mt-8">
            <button onClick={() => goToAuth("signup")} className="btn-primary px-6 py-3 text-base">
              Get started free →
            </button>
            <a href="#features" className="btn-ghost px-6 py-3 text-base">
              See features
            </a>
          </div>

          <div className="flex items-center gap-5 mt-8 text-sm muted">
            <span className="flex items-center gap-2">✅ No credit card</span>
            <span className="flex items-center gap-2">⚡ Instant accounts</span>
          </div>
        </div>

        {/* Auth card */}
        <div id="get-started" className="lg:justify-self-end w-full max-w-md scroll-mt-24">
          <div className="card p-7 sm:p-8 shadow-glow">
            {/* Heading */}
            <div className="text-center mb-6">
              <span className="grid place-items-center h-12 w-12 mx-auto rounded-2xl bg-brand-grad text-white text-xl shadow-glow mb-3">
                {mode === "login" ? "👋" : "🚀"}
              </span>
              <h2 className="text-xl font-bold tracking-tight">
                {mode === "login" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="muted text-sm mt-1">
                {mode === "login"
                  ? "Log in to continue to your dashboard"
                  : "Start teaching every student personally"}
              </p>
            </div>

            {/* Segmented toggle */}
            <div className="flex gap-1 mb-5 p-1 rounded-xl panel">
              {["login", "signup"].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setMode(m); setError(""); setInfo(""); }}
                  className={
                    "flex-1 rounded-lg py-2 text-sm font-semibold transition " +
                    (mode === m
                      ? "bg-brand-grad text-white shadow-glow"
                      : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white")
                  }
                >
                  {m === "login" ? "Log in" : "Sign up"}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="space-y-3.5">
              {mode === "signup" && (
                <>
                  <Field label="Full name" icon="🧑">
                    <input className="input pl-10" placeholder="e.g. Aarav Sharma" value={form.name} onChange={update("name")} required />
                  </Field>
                  <Field label="I am a…" icon="🎭">
                    <select className="input pl-10 appearance-none" value={form.role} onChange={update("role")}>
                      <option value="student">Student</option>
                      <option value="teacher">Teacher</option>
                      <option value="parent">Parent</option>
                      <option value="admin">Institute Admin</option>
                    </select>
                  </Field>
                  <Field label="Institute ID" icon="🏫" hint="optional">
                    <input className="input pl-10" placeholder="Leave blank if unsure" value={form.institute_id} onChange={update("institute_id")} />
                  </Field>
                  {form.role === "student" && (
                    <Field label="Parent's email" icon="👪" hint="links to parent account">
                      <input type="email" className="input pl-10" placeholder="parent@example.com" value={form.parent_email} onChange={update("parent_email")} required />
                    </Field>
                  )}
                </>
              )}

              <Field label="Email" icon="✉️">
                <input type="email" className="input pl-10" placeholder="you@example.com" value={form.email} onChange={update("email")} required />
              </Field>

              <Field label="Password" icon="🔒">
                <input
                  type={showPw ? "text" : "password"}
                  className="input pl-10 pr-12"
                  placeholder="Min 6 characters"
                  value={form.password}
                  onChange={update("password")}
                  minLength={6}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-sm muted hover:text-brand transition"
                  tabIndex={-1}
                  aria-label={showPw ? "Hide password" : "Show password"}
                >
                  {showPw ? "🙈" : "👁️"}
                </button>
              </Field>

              {error && (
                <p className="flex items-start gap-2 text-sm text-rose-600 dark:text-neon-rose bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">
                  <span>⚠️</span> {error}
                </p>
              )}
              {info && <p className="text-sm text-emerald-600 dark:text-emerald-300">{info}</p>}

              <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
                {busy ? "Please wait…" : mode === "login" ? "Log in →" : "Create account →"}
              </button>
            </form>

            <div className="flex items-center justify-center gap-2 mt-5 text-xs muted">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-glow" />
              No email confirmation needed — accounts are ready instantly
            </div>
          </div>
        </div>
      </section>

      {/* ── Stats band ───────────────────────────────────────────── */}
      <section className="border-y border-slate-200/70 dark:border-white/10 bg-white/50 dark:bg-white/[0.02]">
        <div className="max-w-7xl mx-auto px-6 py-10 grid grid-cols-2 lg:grid-cols-4 gap-8 text-center">
          {STATS.map((s) => (
            <div key={s.label}>
              <p className="text-3xl md:text-4xl font-extrabold grad-text">{s.value}</p>
              <p className="muted text-sm mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────── */}
      <section id="features" className="max-w-7xl mx-auto px-6 py-20 scroll-mt-20">
        <div className="text-center max-w-2xl mx-auto">
          <span className="badge-brand mb-4">Features</span>
          <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight">
            Eight agents. One <span className="grad-text">complete</span> platform.
          </h2>
          <p className="muted mt-4 text-lg">
            Everything a coaching institute needs to teach every student personally — without hiring an army.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-12">
          {FEATURES.map((f) => (
            <div key={f.title} className="card card-hover p-5">
              <span className="grid place-items-center h-11 w-11 rounded-xl bg-brand-soft text-2xl">{f.icon}</span>
              <p className="font-semibold mt-4">{f.title}</p>
              <p className="muted text-sm mt-1.5 leading-relaxed">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Who it's for ─────────────────────────────────────────── */}
      <section id="who" className="bg-white/50 dark:bg-white/[0.02] border-y border-slate-200/70 dark:border-white/10 scroll-mt-20">
        <div className="max-w-7xl mx-auto px-6 py-20">
          <div className="text-center max-w-2xl mx-auto">
            <span className="badge-cyan mb-4">Who it's for</span>
            <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight">Built for everyone in the journey</h2>
            <p className="muted mt-4 text-lg">Students, teachers and parents each get a focused experience.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-5 mt-12">
            {ROLES.map((r) => (
              <div key={r.title} className="card card-hover p-6">
                <div className="flex items-center gap-3">
                  <span className="grid place-items-center h-12 w-12 rounded-2xl bg-brand-grad text-white text-xl shadow-glow">{r.icon}</span>
                  <span className={r.badge}>{r.title}</span>
                </div>
                <ul className="mt-5 space-y-3">
                  {r.points.map((p) => (
                    <li key={p} className="flex items-start gap-2 text-sm">
                      <span className="text-emerald-500 mt-0.5">✓</span>
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
      <section id="how" className="max-w-7xl mx-auto px-6 py-20 scroll-mt-20">
        <div className="text-center max-w-2xl mx-auto">
          <span className="badge-amber mb-4">How it works</span>
          <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight">Up and running in three steps</h2>
        </div>

        <div className="grid md:grid-cols-3 gap-5 mt-12">
          {STEPS.map((s) => (
            <div key={s.n} className="card p-6 relative overflow-hidden">
              <span className="absolute -top-3 -right-2 text-7xl font-extrabold text-brand/10 dark:text-white/5 select-none">{s.n}</span>
              <span className="grid place-items-center h-10 w-10 rounded-xl bg-brand-grad text-white font-bold shadow-glow">{s.n}</span>
              <p className="font-semibold mt-4 text-lg">{s.title}</p>
              <p className="muted text-sm mt-1.5 leading-relaxed">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA band ─────────────────────────────────────────────── */}
      <section className="max-w-7xl mx-auto px-6 pb-20">
        <div className="rounded-3xl bg-brand-grad p-10 md:p-14 text-center text-white shadow-glow relative overflow-hidden">
          <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight">Ready to teach every student personally?</h2>
          <p className="mt-4 text-white/90 text-lg max-w-xl mx-auto">
            Spin up your institute in minutes. No infrastructure, no credit card.
          </p>
          <button
            onClick={() => goToAuth("signup")}
            className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white text-brand font-semibold px-7 py-3 text-base shadow hover:brightness-95 transition"
          >
            Get started free →
          </button>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────── */}
      <footer className="border-t border-slate-200/70 dark:border-white/10">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="grid place-items-center h-7 w-7 rounded-lg bg-brand-grad text-white text-sm">🎓</span>
            <span className="font-semibold">
              Smart<span className="grad-text">Coaching</span>
            </span>
          </div>
          <div className="flex items-center gap-6 text-sm muted">
            <a href="#features" className="hover:text-brand transition">Features</a>
            <a href="#who" className="hover:text-brand transition">Who it's for</a>
            <Link href="/architecture" className="hover:text-brand transition">Architecture</Link>
          </div>
          <p className="muted text-xs">© {new Date().getFullYear()} SmartCoaching. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}

// Labelled form field with a leading emoji icon. Children are the control
// (input/select) which gets pl-10 to clear the icon.
function Field({ label, icon, hint, children }) {
  return (
    <label className="block">
      <span className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{label}</span>
        {hint && <span className="text-[11px] muted">{hint}</span>}
      </span>
      <span className="relative block">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm pointer-events-none opacity-80">{icon}</span>
        {children}
      </span>
    </label>
  );
}
