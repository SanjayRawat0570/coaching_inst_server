import { useState } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { supabase } from "../lib/supabase";
import { api } from "../lib/api";

const ROLE_HOME = {
  student: "/student/doubt",
  teacher: "/teacher/dashboard",
  parent: "/parent/report",
  admin: "/admin/analytics",
};

const FEATURES = [
  { icon: "💬", title: "24/7 Doubt Agent", text: "RAG answers from NCERT + your institute notes — text, voice or photo." },
  { icon: "🎯", title: "Concept Weakness Map", text: "Granular per-student mastery — 'integration by parts', not just 'Calculus'." },
  { icon: "🚨", title: "At-Risk Detection", text: "Nightly engagement scoring flags dropout 7 days early." },
  { icon: "📨", title: "Weekly Parent Reports", text: "Auto WhatsApp + email summary every Sunday, written by AI." },
];

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "student", institute_id: "" });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const redirectByRole = (role) => router.replace(ROLE_HOME[role] || "/student/doubt");

  async function ensureStudentProfile(user) {
    if (!user || user.user_metadata?.role !== "student") return;
    const { error } = await supabase.from("students").upsert(
      {
        auth_id: user.id,
        name: user.user_metadata?.name || user.email,
        email: user.email,
        institute_id: user.user_metadata?.institute_id || null,
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
      {/* Top bar */}
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="grid place-items-center h-8 w-8 rounded-xl bg-brand-grad text-white shadow-glow">🎓</span>
          <span className="font-bold tracking-tight">
            Smart<span className="grad-text">Coaching</span>
          </span>
        </div>
        <Link href="/architecture" className="btn-ghost text-sm">
          🧠 Architecture
        </Link>
      </div>

      <div className="max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center pt-8 pb-20">
        {/* Left: pitch */}
        <div>
          <span className="badge-brand mb-5">AI-powered · JEE / NEET · ₹0 infra</span>
          <h1 className="text-4xl md:text-5xl font-extrabold leading-tight tracking-tight">
            One teacher can't teach 50 students individually.
            <span className="grad-text"> Eight AI agents can.</span>
          </h1>
          <p className="muted mt-5 text-lg max-w-xl">
            A coaching platform where AI handles every student personally — 24/7 doubts,
            weakness-targeted tests, AIR rank tracking, and automatic parent reports.
          </p>

          <div className="grid sm:grid-cols-2 gap-3 mt-8">
            {FEATURES.map((f) => (
              <div key={f.title} className="card card-hover p-4">
                <div className="text-2xl">{f.icon}</div>
                <p className="font-semibold mt-2">{f.title}</p>
                <p className="muted text-sm mt-1">{f.text}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Right: auth */}
        <div className="lg:justify-self-end w-full max-w-md">
          <div className="card p-8 shadow-glow">
            <div className="flex gap-2 mb-6 p-1 rounded-xl bg-ink-900/80 border border-white/10">
              {["login", "signup"].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setMode(m); setError(""); setInfo(""); }}
                  className={
                    "flex-1 rounded-lg py-2 text-sm font-medium transition " +
                    (mode === m ? "bg-brand-grad text-white shadow-glow" : "text-slate-400 hover:text-white")
                  }
                >
                  {m === "login" ? "Log in" : "Sign up"}
                </button>
              ))}
            </div>

            <form onSubmit={submit} className="space-y-3">
              {mode === "signup" && (
                <>
                  <input className="input" placeholder="Full name" value={form.name} onChange={update("name")} required />
                  <select className="input" value={form.role} onChange={update("role")}>
                    <option value="student">Student</option>
                    <option value="teacher">Teacher</option>
                    <option value="parent">Parent</option>
                    <option value="admin">Institute Admin</option>
                  </select>
                  <input className="input" placeholder="Institute ID (optional)" value={form.institute_id} onChange={update("institute_id")} />
                </>
              )}
              <input type="email" className="input" placeholder="Email" value={form.email} onChange={update("email")} required />
              <input type="password" className="input" placeholder="Password (min 6 characters)" value={form.password} onChange={update("password")} minLength={6} required />

              {error && <p className="text-sm text-neon-rose">{error}</p>}
              {info && <p className="text-sm text-emerald-300">{info}</p>}

              <button type="submit" disabled={busy} className="btn-primary w-full">
                {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
              </button>
            </form>

            <p className="muted text-xs text-center mt-4">
              No email confirmation needed — accounts are ready instantly.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
