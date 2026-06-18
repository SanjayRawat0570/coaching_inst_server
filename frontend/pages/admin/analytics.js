import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";

export default function AdminAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      const institute_id = user?.user_metadata?.institute_id || "";
      try {
        setData(await api(`/admin/analytics?institute_id=${institute_id}`));
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <Shell requireRole="admin" title="Institute Analytics">
      {loading ? (
        <p className="muted">Loading…</p>
      ) : !data ? (
        <p className="muted">No analytics available.</p>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Active students" value={data.active_students ?? 0} />
            <Stat label="At-risk now" value={data.at_risk_count ?? 0} accent="text-red-600" />
            <Stat label="Tests this week" value={data.tests_week ?? 0} />
            <Stat
              label="Renewal likelihood"
              value={data.renewal_pct != null ? `${data.renewal_pct}%` : "—"}
              accent="text-green-600"
            />
          </div>

          <div className="card p-5">
            <h2 className="font-semibold mb-3">Weekly engagement</h2>
            {(!data.engagement || data.engagement.length === 0) ? (
              <p className="muted text-sm">Not enough data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={data.engagement}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.2)" />
                  <XAxis dataKey="week" tick={{ fontSize: 12, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 12, fill: "#94a3b8" }} />
                  <Tooltip
                    contentStyle={{ background: "#0b1120", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#e2e8f0" }}
                    cursor={{ stroke: "rgba(255,255,255,0.1)" }}
                  />
                  <Line type="monotone" dataKey="active" stroke="#7c5cff" strokeWidth={2} dot={{ fill: "#22d3ee" }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {data.revenue_signals?.length > 0 && (
            <div className="card p-5">
              <h2 className="font-semibold mb-3">Revenue signals</h2>
              <ul className="space-y-2 text-sm">
                {data.revenue_signals.map((s, i) => (
                  <li key={i} className="flex justify-between border-b border-slate-200 dark:border-white/10 pb-1.5">
                    <span className="muted">{s.label}</span>
                    <span className="font-medium">{s.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Account totals across all roles */}
          {data.counts && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="🎓 Students" value={data.counts.students ?? 0} />
              <Stat label="🧑‍🏫 Teachers" value={data.counts.teachers ?? 0} />
              <Stat label="👪 Parents" value={data.counts.parents ?? 0} />
              <Stat label="🛡️ Admins" value={data.counts.admins ?? 0} />
            </div>
          )}

          {/* Full student records */}
          <div className="card p-5 overflow-x-auto">
            <h2 className="font-semibold mb-3">Students ({data.students?.length ?? 0})</h2>
            {(!data.students || data.students.length === 0) ? (
              <p className="muted text-sm">No student profiles yet.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
                    <Th>Name</Th><Th>Email</Th><Th>Parent email</Th><Th>Target</Th>
                    <Th>XP</Th><Th>Streak</Th><Th>Last active</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.students.map((s) => (
                    <tr key={s.id} className="border-b border-slate-100 dark:border-white/5">
                      <Td className="font-medium">{s.name || "—"}</Td>
                      <Td>{s.email || "—"}</Td>
                      <Td>{s.parent_email || "—"}</Td>
                      <Td>{s.target_exam || "—"}</Td>
                      <Td>{s.xp_points ?? 0}</Td>
                      <Td>{s.streak_days ?? 0}🔥</Td>
                      <Td>{fmtDate(s.last_active)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Teacher & parent accounts */}
          <div className="grid md:grid-cols-2 gap-6">
            <AccountList title="🧑‍🏫 Teachers" rows={data.teachers} />
            <AccountList title="👪 Parents" rows={data.parents} />
          </div>

          {/* Platform architecture (also available as a full page at /architecture) */}
          <Link href="/architecture" className="card card-hover p-5 flex items-center justify-between bg-brand-soft">
            <div>
              <h2 className="font-semibold">🧠 Platform architecture</h2>
              <p className="muted text-sm mt-1">
                8 AI agents · 6-pattern RAG · LangGraph orchestration · 100% free stack
              </p>
            </div>
            <span className="btn-ghost text-sm whitespace-nowrap">View map →</span>
          </Link>
        </div>
      )}
    </Shell>
  );
}

function Stat({ label, value, accent = "" }) {
  return (
    <div className="card card-hover p-5 text-center">
      <p className={`text-3xl font-bold ${accent || "grad-text"}`}>{value}</p>
      <p className="text-xs muted mt-1">{label}</p>
    </div>
  );
}

function Th({ children }) {
  return <th className="py-2 pr-4 font-medium whitespace-nowrap">{children}</th>;
}

function Td({ children, className = "" }) {
  return <td className={`py-2 pr-4 whitespace-nowrap ${className}`}>{children}</td>;
}

function AccountList({ title, rows }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3">
        {title} ({rows?.length ?? 0})
      </h2>
      {(!rows || rows.length === 0) ? (
        <p className="muted text-sm">No accounts yet.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-3 border-b border-slate-100 dark:border-white/5 pb-2">
              <div className="min-w-0">
                <p className="font-medium truncate">{r.name || "—"}</p>
                <p className="muted text-xs truncate">{r.email}</p>
              </div>
              <span className="muted text-xs whitespace-nowrap">{fmtDate(r.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function fmtDate(v) {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d) ? "—" : d.toLocaleDateString();
}
