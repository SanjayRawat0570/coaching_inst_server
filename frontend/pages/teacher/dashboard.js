import { useEffect, useState } from "react";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import Shell from "../../components/Shell";
import { EmptyState, Stat, SkeletonCard } from "../../components/ui";
import Icon from "../../components/Icon";
import ActivityHeatmap from "../../components/ActivityHeatmap";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";

function heatColor(score) {
  if (score >= 0.8) return "bg-emerald-500";
  if (score >= 0.5) return "bg-amber-400";
  if (score > 0) return "bg-rose-400";
  return "bg-slate-300 dark:bg-white/10";
}

export default function TeacherDashboard() {
  const [overview, setOverview] = useState({ heatmap: [], alerts: [], top_doubts: [] });
  const [submissions, setSubmissions] = useState([]);
  const [students, setStudents] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [clustersBusy, setClustersBusy] = useState(false);
  const [heat, setHeat] = useState({ hours: [], total: 0, days: 14 });
  const [monthly, setMonthly] = useState([]);
  const [monthlyStudent, setMonthlyStudent] = useState(""); // "" = whole class
  const [instId, setInstId] = useState("");
  const [loading, setLoading] = useState(true);

  // F15: (re)load the monthly line for the class or a chosen student.
  async function loadMonthly(studentId) {
    setMonthlyStudent(studentId);
    try {
      const res = await api(`/teacher/monthly-scores?institute_id=${instId}&student_id=${studentId}`);
      setMonthly(res.monthly || []);
    } catch (e) {
      console.error("monthly scores failed", e);
      setMonthly([]);
    }
  }

  useEffect(() => {
    (async () => {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      const institute_id = user?.user_metadata?.institute_id || "";
      setInstId(institute_id);
      // Independent calls — one failing must not blank the rest of the dashboard.
      const [ov, subs, studs, cl, hm, ms] = await Promise.allSettled([
        api(`/teacher/overview?institute_id=${institute_id}`),
        api(`/teacher/submissions?institute_id=${institute_id}`),
        api(`/teacher/students?institute_id=${institute_id}`),
        api(`/teacher/doubt-clusters?institute_id=${institute_id}`),
        api(`/teacher/activity-heatmap?institute_id=${institute_id}`),
        api(`/teacher/monthly-scores?institute_id=${institute_id}`),
      ]);
      if (ov.status === "fulfilled") setOverview(ov.value);
      else console.error("overview failed", ov.reason);
      if (subs.status === "fulfilled") setSubmissions(subs.value.submissions || []);
      else console.error("submissions failed", subs.reason);
      if (studs.status === "fulfilled") setStudents(studs.value.students || []);
      else console.error("students failed", studs.reason);
      if (cl.status === "fulfilled") setClusters(cl.value.clusters || []);
      else console.error("clusters failed", cl.reason);
      if (hm.status === "fulfilled") setHeat(hm.value);
      else console.error("activity heatmap failed", hm.reason);
      if (ms.status === "fulfilled") setMonthly(ms.value.monthly || []);
      else console.error("monthly scores failed", ms.reason);
      setLoading(false);
    })();
  }, []);

  async function rebuildClusters() {
    setClustersBusy(true);
    try {
      await api("/teacher/doubt-clusters/build", { method: "POST" });
      const cl = await api(`/teacher/doubt-clusters?institute_id=${instId}`);
      setClusters(cl.clusters || []);
    } catch (e) {
      console.error(e);
    } finally {
      setClustersBusy(false);
    }
  }

  async function markRead(alertId) {
    await api("/teacher/alerts/read", { method: "POST", body: { alert_id: alertId } });
    setOverview((o) => ({ ...o, alerts: o.alerts.filter((a) => a.id !== alertId) }));
  }

  const alerts = overview.alerts || [];
  const heatmap = overview.heatmap || [];
  const topDoubts = overview.top_doubts || [];
  const weakest = heatmap.length ? heatmap[0] : null; // sorted ascending by avg_score
  const avgMastery = heatmap.length
    ? Math.round((heatmap.reduce((s, c) => s + (c.avg_score || 0), 0) / heatmap.length) * 100)
    : null;

  return (
    <Shell requireRole="teacher" title="Class Dashboard" subtitle="Live overview of your class">
      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <SkeletonCard lines={1} />
            <SkeletonCard lines={1} />
            <SkeletonCard lines={1} />
            <SkeletonCard lines={1} />
          </div>
          <div className="grid lg:grid-cols-2 gap-6">
            <SkeletonCard lines={4} />
            <SkeletonCard lines={4} />
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Stat icon={<Icon name="alert" />} label="At-risk students" value={alerts.length} accent="text-rose-500 dark:text-neon-rose" />
            <Stat icon={<Icon name="concepts" />} label="Concepts tracked" value={heatmap.length} />
            <Stat icon={<Icon name="mastery" />} label="Avg class mastery" value={avgMastery != null ? `${avgMastery}%` : "—"} />
            <Stat icon={<Icon name="doubt" />} label="Hot doubts" value={topDoubts.length} />
          </div>

          {weakest && (
            <div className="card p-4 flex items-center gap-3 bg-brand/[0.04] dark:bg-brand/[0.07] border-brand/20">
              <span className="icon-tile h-10 w-10 shrink-0"><Icon name="target" /></span>
              <p className="text-sm">
                Weakest class concept:{" "}
                <span className="font-semibold">{weakest.concept}</span>{" "}
                <span className="muted">({Math.round((weakest.avg_score || 0) * 100)}% avg mastery) — consider a focused session.</span>
              </p>
            </div>
          )}

          <div className="grid lg:grid-cols-2 gap-6 items-start">
          {/* At-risk alerts */}
          <section className="card p-5">
            <h2 className="h-section mb-3 flex items-center gap-2">
              <Icon name="alert" size={16} className="text-rose-500 dark:text-neon-rose" /> At-risk students
              {alerts.length > 0 && <span className="badge bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30">{alerts.length}</span>}
            </h2>
            {alerts.length === 0 && (
              <EmptyState icon={<Icon name="check" size={26} className="text-emerald-500" />} title="No alerts right now" hint="Every student is engaged. We'll flag anyone who falls behind." />
            )}
            <div className="space-y-2">
              {alerts.map((a) => (
                <div
                  key={a.id}
                  className="flex items-start justify-between rounded-xl border border-rose-500/20 bg-rose-500/5 p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-rose-600 dark:text-rose-400">
                      Risk {a.risk_score}/100 · {a.alert_type}
                    </p>
                    <p className="text-sm text-slate-600 dark:text-slate-300">{a.message}</p>
                    <p className="text-xs muted mt-1">{a.suggested_action}</p>
                  </div>
                  <button
                    onClick={() => markRead(a.id)}
                    className="text-xs text-brand dark:text-indigo-400 hover:underline whitespace-nowrap ml-3"
                  >
                    Mark read
                  </button>
                </div>
              ))}
            </div>
          </section>

          {/* Top doubts */}
          <section className="card p-5">
            <h2 className="h-section mb-3">Most asked doubts this week</h2>
            {topDoubts.length === 0 ? (
              <EmptyState icon={<Icon name="doubt" size={26} />} title="No doubts logged yet" hint="Questions your students ask the AI tutor will surface here." />
            ) : (
              <ul className="space-y-2 text-sm">
                {topDoubts.map((d, i) => (
                  <li key={i} className="panel p-3 flex items-start justify-between gap-3">
                    <span className="text-slate-700 dark:text-slate-200">{d.question}</span>
                    <span className="badge-brand shrink-0">{d.count}×</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          </div>

          {/* F6 — 24-hour activity heatmap for the class */}
          <section className="card p-5">
            <ActivityHeatmap hours={heat.hours} total={heat.total} days={heat.days} />
          </section>

          {/* F15 — month-vs-month scores (class or a single student) */}
          <section className="card p-5">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="h-section flex items-center gap-2">
                <Icon name="analytics" size={16} /> Scores · month over month
              </h2>
              <select
                className="input text-sm max-w-[220px]"
                value={monthlyStudent}
                onChange={(e) => loadMonthly(e.target.value)}
              >
                <option value="">All students (class avg)</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.name || s.email}</option>
                ))}
              </select>
            </div>
            {monthly.length === 0 ? (
              <EmptyState
                icon={<Icon name="analytics" size={26} />}
                title="No monthly data yet"
                hint="Once graded tests exist, average scores per month appear here."
              />
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={monthly} margin={{ left: -10, right: 10, top: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
                  <XAxis dataKey="month" tick={{ fontSize: 12, fill: "#94a3b8" }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "#94a3b8" }} />
                  <Tooltip
                    contentStyle={{ background: "#0b1120", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#e2e8f0" }}
                    formatter={(v) => [`${v}%`, monthlyStudent ? "Score" : "Avg score"]}
                  />
                  <Line type="monotone" dataKey="avg_pct" stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </section>

          {/* Top doubt clusters — grouped similar questions (computed nightly) */}
          <section className="card p-5">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="h-section flex items-center gap-2">
                <Icon name="network" size={16} /> Top doubt clusters
                {clusters.length > 0 && <span className="badge-brand">{clusters.length}</span>}
              </h2>
              <button onClick={rebuildClusters} disabled={clustersBusy} className="btn-ghost text-xs px-3 py-1.5">
                {clustersBusy ? "Clustering…" : "Recompute now"}
              </button>
            </div>
            {clusters.length === 0 ? (
              <EmptyState
                icon={<Icon name="network" size={26} />}
                title="No clusters yet"
                hint="Similar student doubts are grouped nightly. Use “Recompute now” once a few doubts exist."
              />
            ) : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {clusters.map((c) => (
                  <div key={c.id} className="panel p-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm font-semibold">{c.label}</p>
                      <span className="badge-brand shrink-0">{c.size}×</span>
                    </div>
                    {c.subject && <p className="text-xs text-brand dark:text-indigo-400 mt-0.5">{c.subject}</p>}
                    <ul className="mt-2 space-y-1">
                      {(c.samples || []).map((s, j) => (
                        <li key={j} className="muted text-xs flex gap-1.5"><span>•</span><span className="line-clamp-2">{s}</span></li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Class concept heatmap — full width */}
          <section className="card p-5">
            <h2 className="h-section mb-3">Class concept heatmap</h2>
            {heatmap.length === 0 ? (
              <EmptyState icon={<Icon name="concepts" size={26} />} title="No data yet" hint="Once students take tests, per-concept class mastery appears here." />
            ) : (
              <div className="flex flex-wrap gap-2">
                {heatmap.map((c, i) => (
                  <div
                    key={i}
                    className={`px-3 py-2 rounded-lg text-white text-sm ${heatColor(c.avg_score)}`}
                    title={`avg mastery ${Math.round((c.avg_score || 0) * 100)}%`}
                  >
                    {c.concept} · {Math.round((c.avg_score || 0) * 100)}%
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Students roster — pick one to generate a personalised test */}
          <section className="card p-5">
            <h2 className="h-section mb-3 flex items-center gap-2">
              <Icon name="student" size={16} /> Students
              {students.length > 0 && <span className="badge-brand">{students.length}</span>}
            </h2>
            {students.length === 0 ? (
              <EmptyState
                icon={<Icon name="student" size={26} />}
                title="No students yet"
                hint="Students appear here after they sign up and log in for the first time."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
                      <th className="py-2 pr-3 font-medium">Name</th>
                      <th className="py-2 pr-3 font-medium">Email</th>
                      <th className="py-2 pr-3 font-medium">Target exam</th>
                      <th className="py-2 font-medium text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((s) => (
                      <tr key={s.id} className="border-b border-slate-100 dark:border-white/5">
                        <td className="py-2 pr-3 font-medium">{s.name || "—"}</td>
                        <td className="py-2 pr-3 muted">{s.email || "—"}</td>
                        <td className="py-2 pr-3">{s.target_exam || "—"}</td>
                        <td className="py-2 text-right">
                          {s.email ? (
                            <Link
                              href={`/teacher/review?student=${encodeURIComponent(s.email)}`}
                              className="btn-ghost text-xs px-3 py-1.5"
                            >
                              <Icon name="tests" size={14} /> Generate test
                            </Link>
                          ) : (
                            <span className="muted text-xs">no email</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Submitted tests — results students have completed */}
          <section className="card p-5">
            <h2 className="h-section mb-3 flex items-center gap-2">
              <Icon name="tests" size={16} /> Submitted tests
              {submissions.length > 0 && <span className="badge-brand">{submissions.length}</span>}
            </h2>
            {submissions.length === 0 ? (
              <EmptyState
                icon={<Icon name="tests" size={26} />}
                title="No submissions yet"
                hint="Once students submit their tests, their scores show up here."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
                      <th className="py-2 pr-3 font-medium">Student</th>
                      <th className="py-2 pr-3 font-medium">Subject</th>
                      <th className="py-2 pr-3 font-medium">Score</th>
                      <th className="py-2 pr-3 font-medium">%</th>
                      <th className="py-2 font-medium">Submitted</th>
                    </tr>
                  </thead>
                  <tbody>
                    {submissions.map((s) => (
                      <tr key={s.id} className="border-b border-slate-100 dark:border-white/5">
                        <td className="py-2 pr-3 font-medium">{s.student_name}</td>
                        <td className="py-2 pr-3">{s.subject || "Mixed"}</td>
                        <td className="py-2 pr-3 tabular-nums">
                          {s.score ?? "—"}
                          {s.total_marks ? ` / ${s.total_marks}` : ""}
                        </td>
                        <td className="py-2 pr-3">
                          {s.percent != null ? (
                            <span
                              className={
                                "badge " +
                                (s.percent >= 60
                                  ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border border-emerald-500/30"
                                  : s.percent >= 35
                                  ? "bg-amber-400/10 text-amber-600 dark:text-amber-300 border border-amber-400/30"
                                  : "bg-rose-500/10 text-rose-600 dark:text-neon-rose border border-rose-500/30")
                              }
                            >
                              {s.percent}%
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="py-2 muted">
                          {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </Shell>
  );
}
