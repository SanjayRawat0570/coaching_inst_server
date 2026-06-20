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
import Icon from "../../components/Icon";
import { ResultsTable } from "../../components/ui";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";

export default function AdminAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [logs, setLogs] = useState([]);
  const [actions, setActions] = useState([]);
  const [auditAction, setAuditAction] = useState("");
  const [auditQ, setAuditQ] = useState("");

  async function loadAudit() {
    try {
      const res = await api(
        `/admin/audit-logs?action=${encodeURIComponent(auditAction)}&q=${encodeURIComponent(auditQ)}`
      );
      setLogs(res.logs || []);
      setActions(res.actions || []);
    } catch (e) {
      console.error("audit logs failed", e);
    }
  }

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

  // F18: (re)load audit logs when the action filter changes.
  useEffect(() => { loadAudit(); }, [auditAction]);

  return (
    <Shell requireRole="admin" title="Institute Analytics">
      {loading ? (
        <p className="muted">Loading…</p>
      ) : !data ? (
        <p className="muted">No analytics available.</p>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Active students" value={data.active_students ?? 0} icon={<Icon name="students" />} />
            <Stat label="At-risk now" value={data.at_risk_count ?? 0} accent="text-rose-500 dark:text-neon-rose" icon={<Icon name="alert" />} />
            <Stat label="Tests this week" value={data.tests_week ?? 0} icon={<Icon name="tests" />} />
            <Stat
              label="Engagement rate"
              value={data.engagement_rate != null ? `${data.engagement_rate}%` : "—"}
              accent="text-emerald-500 dark:text-emerald-400"
              icon={<Icon name="mastery" />}
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
                  <Line type="monotone" dataKey="active" stroke="#4f46e5" strokeWidth={2} dot={{ fill: "#4f46e5" }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Account totals across all roles */}
          {data.counts && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Stat label="Students" value={data.counts.students ?? 0} icon={<Icon name="students" />} />
              <Stat label="Teachers" value={data.counts.teachers ?? 0} icon={<Icon name="teachers" />} />
              <Stat label="Parents" value={data.counts.parents ?? 0} icon={<Icon name="parents" />} />
              <Stat label="Admins" value={data.counts.admins ?? 0} icon={<Icon name="admins" />} />
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
                      <Td>{s.streak_days ?? 0}<span className="muted"> day{(s.streak_days ?? 0) === 1 ? "" : "s"}</span></Td>
                      <Td>{fmtDate(s.last_active)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Recent test results across the institute */}
          <div className="card p-5">
            <h2 className="font-semibold mb-3 flex items-center gap-2">
              <Icon name="tests" size={16} /> Recent test results
              {data.recent_results?.length > 0 && <span className="badge-brand">{data.recent_results.length}</span>}
            </h2>
            {(!data.recent_results || data.recent_results.length === 0) ? (
              <p className="muted text-sm">No graded tests yet. Results appear here once students submit tests.</p>
            ) : (
              <ResultsTable rows={data.recent_results} showStudent />
            )}
          </div>

          {/* Teacher & parent accounts */}
          <div className="grid md:grid-cols-2 gap-6">
            <AccountList title="Teachers" iconName="teachers" rows={data.teachers} />
            <AccountList title="Parents" iconName="parents" rows={data.parents} />
          </div>

          {/* F18 — audit trail */}
          <div className="card p-5 overflow-x-auto">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <h2 className="font-semibold flex items-center gap-2">
                <Icon name="alert" size={16} /> Audit log
                {logs.length > 0 && <span className="badge-brand">{logs.length}</span>}
              </h2>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className="input text-sm py-1.5 max-w-[200px]"
                  value={auditAction}
                  onChange={(e) => setAuditAction(e.target.value)}
                >
                  <option value="">All actions</option>
                  {actions.map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
                <input
                  className="input text-sm py-1.5 max-w-[220px]"
                  placeholder="Search email / detail…"
                  value={auditQ}
                  onChange={(e) => setAuditQ(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && loadAudit()}
                />
                <button className="btn-ghost text-sm px-3 py-1.5" onClick={loadAudit}>Search</button>
              </div>
            </div>
            {logs.length === 0 ? (
              <p className="muted text-sm">No audit events yet. Test, badge and goal actions will appear here.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
                    <Th>Time</Th><Th>Actor</Th><Th>Role</Th><Th>Action</Th><Th>Entity</Th><Th>Detail</Th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id} className="border-b border-slate-100 dark:border-white/5">
                      <Td className="muted">{fmtDateTime(l.created_at)}</Td>
                      <Td>{l.actor_email || "—"}</Td>
                      <Td>{l.role || "—"}</Td>
                      <Td><span className="badge-brand">{l.action}</span></Td>
                      <Td className="muted truncate max-w-[160px]">{l.entity || "—"}</Td>
                      <Td className="muted truncate max-w-[280px]">{l.detail ? JSON.stringify(l.detail) : "—"}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Platform architecture (also available as a full page at /architecture) */}
          <Link href="/architecture" className="card card-hover p-5 flex items-center justify-between gap-4 bg-brand/[0.04] dark:bg-brand/[0.07] border-brand/20">
            <div className="flex items-center gap-3 min-w-0">
              <span className="icon-tile h-11 w-11 shrink-0"><Icon name="architecture" size={20} /></span>
              <div className="min-w-0">
                <h2 className="font-semibold">Platform architecture</h2>
                <p className="muted text-sm mt-0.5">
                  8 AI agents · 6-pattern RAG · LangGraph orchestration · 100% free stack
                </p>
              </div>
            </div>
            <span className="btn-ghost text-sm whitespace-nowrap shrink-0">View map <Icon name="arrowRight" size={15} /></span>
          </Link>
        </div>
      )}
    </Shell>
  );
}

function Stat({ label, value, accent = "", icon }) {
  return (
    <div className="card card-hover p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="stat-label">{label}</p>
          <p className={`stat-value mt-1.5 ${accent || "grad-text"}`}>{value}</p>
        </div>
        {icon && <span className="icon-tile h-10 w-10 shrink-0">{icon}</span>}
      </div>
    </div>
  );
}

function Th({ children }) {
  return <th className="py-2 pr-4 font-medium whitespace-nowrap">{children}</th>;
}

function Td({ children, className = "" }) {
  return <td className={`py-2 pr-4 whitespace-nowrap ${className}`}>{children}</td>;
}

function AccountList({ title, rows, iconName }) {
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3 flex items-center gap-2">
        {iconName && <Icon name={iconName} size={16} />}
        {title} <span className="muted font-normal">({rows?.length ?? 0})</span>
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

function fmtDateTime(v) {
  if (!v) return "—";
  const d = new Date(v);
  return isNaN(d) ? "—" : d.toLocaleString();
}
