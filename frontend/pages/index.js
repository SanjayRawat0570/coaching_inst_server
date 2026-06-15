import { useState } from "react";
import { useRouter } from "next/router";
import { supabase } from "../lib/supabase";

const ROLE_HOME = {
  student: "/student/doubt",
  teacher: "/teacher/dashboard",
  parent: "/parent/report",
  admin: "/admin/analytics",
};

export default function Home() {
  const router = useRouter();
  const [mode, setMode] = useState("login"); // login | signup
  const [form, setForm] = useState({
    email: "",
    password: "",
    name: "",
    role: "student",
    institute_id: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const redirectByRole = (role) => router.replace(ROLE_HOME[role] || "/student/doubt");

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          email: form.email,
          password: form.password,
          options: {
            data: {
              role: form.role,
              name: form.name,
              institute_id: form.institute_id,
            },
          },
        });
        if (error) throw error;
        // If email confirmation is off, a session exists immediately
        if (data.session) redirectByRole(form.role);
        else setError("Check your email to confirm your account, then log in.");
      } else {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: form.email,
          password: form.password,
        });
        if (error) throw error;
        redirectByRole(data.user?.user_metadata?.role);
      }
    } catch (err) {
      setError(err.message || "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Left: pitch */}
      <div className="hidden md:flex w-1/2 bg-brand text-white p-12 flex-col justify-center">
        <h1 className="text-4xl font-bold mb-4">🎓 Smart Coaching</h1>
        <p className="text-lg opacity-90 mb-6">
          AI agents that teach every JEE / NEET student individually — 24/7 doubts,
          personalized tests, AIR rank tracking, and weekly parent reports.
        </p>
        <ul className="space-y-2 opacity-90">
          <li>• Doubt agent answers from NCERT + your institute notes</li>
          <li>• Concept-level weakness map per student</li>
          <li>• At-risk detection 7 days before dropout</li>
          <li>• Sunday WhatsApp reports to parents</li>
        </ul>
      </div>

      {/* Right: auth */}
      <div className="w-full md:w-1/2 flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm space-y-4">
          <h2 className="text-2xl font-semibold">
            {mode === "login" ? "Log in" : "Create account"}
          </h2>

          {mode === "signup" && (
            <>
              <input
                className="w-full border rounded-lg px-3 py-2"
                placeholder="Full name"
                value={form.name}
                onChange={update("name")}
                required
              />
              <select
                className="w-full border rounded-lg px-3 py-2 bg-white"
                value={form.role}
                onChange={update("role")}
              >
                <option value="student">Student</option>
                <option value="teacher">Teacher</option>
                <option value="parent">Parent</option>
                <option value="admin">Institute Admin</option>
              </select>
              <input
                className="w-full border rounded-lg px-3 py-2"
                placeholder="Institute ID"
                value={form.institute_id}
                onChange={update("institute_id")}
              />
            </>
          )}

          <input
            type="email"
            className="w-full border rounded-lg px-3 py-2"
            placeholder="Email"
            value={form.email}
            onChange={update("email")}
            required
          />
          <input
            type="password"
            className="w-full border rounded-lg px-3 py-2"
            placeholder="Password"
            value={form.password}
            onChange={update("password")}
            required
          />

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="w-full bg-brand hover:bg-brand-dark text-white rounded-lg py-2 font-medium disabled:opacity-60"
          >
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Sign up"}
          </button>

          <p className="text-sm text-center text-slate-500">
            {mode === "login" ? "New here? " : "Already have an account? "}
            <button
              type="button"
              className="text-brand font-medium"
              onClick={() => {
                setError("");
                setMode(mode === "login" ? "signup" : "login");
              }}
            >
              {mode === "login" ? "Create an account" : "Log in"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
