import { useState, useEffect } from "react";
import { useRouter } from "next/router";
import Link from "next/link";
import { supabase } from "../lib/supabase";
import { api } from "../lib/api";
import ThemeToggle from "../components/ThemeToggle";
import {
  Mail, GraduationCap, Users, ArrowLeft,
  User, Building2, Lock, UserCog, Eye, EyeOff, AlertCircle,
} from "lucide-react";

const ROLE_HOME = {
  student: "/student/doubt",
  teacher: "/teacher/dashboard",
  parent: "/parent/report",
  admin: "/admin/analytics",
};

export default function Login() {
  const router = useRouter();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", name: "", role: "student", institute_id: "", parent_email: "" });
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [showPw, setShowPw] = useState(false);

  // Open in the mode the landing page sent us to (?mode=signup).
  useEffect(() => {
    if (!router.isReady) return;
    if (router.query.mode === "signup") setMode("signup");
  }, [router.isReady, router.query.mode]);

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
    <div className="min-h-screen flex flex-col">
      {/* ── Top bar ───────────────────────────────────────────────── */}
      <header className="border-b hairline">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <span className="grid place-items-center h-8 w-8 rounded-lg bg-brand text-white">
              <GraduationCap size={17} />
            </span>
            <span className="font-semibold tracking-tight text-[15px]">
              Smart<span className="text-brand dark:text-violet-400">Coaching</span>
            </span>
          </Link>
          <div className="flex items-center gap-1.5">
            <Link href="/" className="btn-ghost text-sm"><ArrowLeft size={15} /> Home</Link>
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* ── Auth card ─────────────────────────────────────────────── */}
      <main className="flex-1 flex items-center justify-center px-4 py-10 sm:py-16">
        <div className="w-full max-w-md">
          <div className="text-center mb-6">
            <h1 className="text-2xl font-semibold tracking-tight">
              {mode === "login" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="muted text-sm mt-2">
              {mode === "login"
                ? "Sign in to continue to your dashboard."
                : "Start teaching every student personally — set up in minutes."}
            </p>
          </div>

          <div className="card p-6 sm:p-7">
            {/* Segmented toggle */}
            <div className="flex gap-1 mb-5 p-1 rounded-xl panel">
              {["login", "signup"].map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => { setMode(m); setError(""); setInfo(""); }}
                  className={
                    "flex-1 rounded-lg py-2 text-sm font-medium transition " +
                    (mode === m
                      ? "bg-white text-slate-900 shadow-soft dark:bg-white/10 dark:text-white"
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
                  <Field label="Full name" icon={<User size={16} />}>
                    <input className="input pl-10" placeholder="e.g. Aarav Sharma" value={form.name} onChange={update("name")} required />
                  </Field>
                  <Field label="I am a…" icon={<UserCog size={16} />}>
                    <select className="input pl-10 appearance-none" value={form.role} onChange={update("role")}>
                      <option value="student">Student</option>
                      <option value="teacher">Teacher</option>
                      <option value="parent">Parent</option>
                      <option value="admin">Institute Admin</option>
                    </select>
                  </Field>
                  <Field label="Institute ID" icon={<Building2 size={16} />} hint="optional">
                    <input className="input pl-10" placeholder="Leave blank if unsure" value={form.institute_id} onChange={update("institute_id")} />
                  </Field>
                  {form.role === "student" && (
                    <Field label="Parent's email" icon={<Users size={16} />} hint="links to parent account">
                      <input type="email" className="input pl-10" placeholder="parent@example.com" value={form.parent_email} onChange={update("parent_email")} required />
                    </Field>
                  )}
                </>
              )}

              <Field label="Email" icon={<Mail size={16} />}>
                <input type="email" className="input pl-10" placeholder="you@example.com" value={form.email} onChange={update("email")} required />
              </Field>

              <Field label="Password" icon={<Lock size={16} />}>
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
                  className="absolute right-3 top-1/2 -translate-y-1/2 muted hover:text-brand transition"
                  tabIndex={-1}
                  aria-label={showPw ? "Hide password" : "Show password"}
                >
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </Field>

              {error && (
                <p className="flex items-start gap-2 text-sm text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg px-3 py-2">
                  <AlertCircle size={15} className="mt-0.5 shrink-0" /> {error}
                </p>
              )}
              {info && <p className="text-sm text-emerald-600 dark:text-emerald-300">{info}</p>}

              <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
                {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
              </button>
            </form>

            <p className="text-center text-xs muted mt-4">
              No email confirmation needed — accounts are ready instantly.
            </p>
          </div>

          <p className="text-center text-sm muted mt-5">
            {mode === "login" ? "New to SmartCoaching? " : "Already have an account? "}
            <button
              type="button"
              onClick={() => { setMode(mode === "login" ? "signup" : "login"); setError(""); }}
              className="font-medium text-brand dark:text-violet-400 hover:underline"
            >
              {mode === "login" ? "Create an account" : "Log in"}
            </button>
          </p>
        </div>
      </main>
    </div>
  );
}

// Labelled form field with a leading icon. Children are the control
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
