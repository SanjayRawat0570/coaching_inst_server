import { useState } from "react";
import Link from "next/link";
import dynamic from "next/dynamic";
import Shell from "../../components/Shell";
import { EmptyState, Stat, SkeletonCard, ErrorState, Skeleton } from "../../components/ui";
import Icon from "../../components/Icon";
import ActivityHeatmap from "../../components/ActivityHeatmap";
import { useToast } from "../../components/Toast";
import { api, errorDetail } from "../../lib/api";
import { useApi } from "../../lib/hooks";
import { useAuth } from "../../lib/useAuth";

// Recharts loads only for the chart, after the dashboard is on screen.
const TrendChart = dynamic(() => import("../../components/charts/TrendChart"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full" />,
});

function heatColor(score) {
  if (score >= 0.8) return "bg-emerald-500";
  if (score >= 0.5) return "bg-amber-400";
  if (score > 0) return "bg-rose-400";
  return "bg-slate-300 dark:bg-white/10";
}

export default function TeacherDashboard() {
  const toast = useToast();
  const { instituteId: instId } = useAuth();
  const q = `institute_id=${instId}`;
  // Independent cached requests — one failing never blanks the rest of the dashboard.
  const overviewQ = useApi(`/teacher/overview?${q}`);
  const submissionsQ = useApi(`/teacher/submissions?${q}`);
  const studentsQ = useApi(`/teacher/students?${q}`);
  const clustersQ = useApi(`/teacher/doubt-clusters?${q}`);
  const heatQ = useApi(`/teacher/activity-heatmap?${q}`);
  const insightsQ = useApi(`/teacher/rag-insights`);
  const [monthlyStudent, setMonthlyStudent] = useState(""); // "" = whole class
  const monthlyQ = useApi(`/teacher/monthly-scores?${q}&student_id=${monthlyStudent}`);
  const [clustersBusy, setClustersBusy] = useState(false);

  const overview = overviewQ.data || { heatmap: [], alerts: [], top_doubts: [] };
  const submissions = submissionsQ.data?.submissions || [];
  const students = studentsQ.data?.students || [];
  const clusters = clustersQ.data?.clusters || [];
  const heat = heatQ.data || { hours: [], total: 0, days: 14 };
  const monthly = monthlyQ.data?.monthly || [];
  const insights = insightsQ.data || { content_gaps: [], answer_quality: null };
  const loading = !overviewQ.data && !overviewQ.error;

  // F15: the monthly line for the class or a chosen student (its own cached request).
  function loadMonthly(studentId) {
    setMonthlyStudent(studentId);
  }

  async function rebuildClusters() {
    setClustersBusy(true);
    try {
      await api("/teacher/doubt-clusters/build", { method: "POST" });
      await clustersQ.mutate();
      toast("Doubt clusters updated.");
    } catch (e) {
      toast(errorDetail(e) || "Couldn't recompute clusters. Please try again.", "error");
    } finally {
      setClustersBusy(false);
    }
  }

  // Optimistic: the alert disappears at once and comes back if the update fails.
  async function markRead(alertId) {
    const before = overviewQ.data;
    overviewQ.mutate({ ...overview, alerts: overview.alerts.filter((a) => a.id !== alertId) },
                     { revalidate: false });
    try {
      await api("/teacher/alerts/read", { method: "POST", body: { alert_id: alertId } });
    } catch (e) {
      overviewQ.mutate(before, { revalidate: false });
      toast("Couldn't mark that alert as read. Please try again.", "error");
    }
  }

  // Content gaps have their own card below; this list is for at-risk students.
  const alerts = (overview.alerts || []).filter((a) => a.alert_type !== "content_gap");
  const gaps = insights.content_gaps || [];
  const quality = insights.answer_quality;
  const heatmap = overview.heatmap || [];
  const topDoubts = overview.top_doubts || [];
  const weakest = heatmap.length ? heatmap[0] : null; // sorted ascending by avg_score
  const avgMastery = heatmap.length
    ? Math.round((heatmap.reduce((s, c) => s + (c.avg_score || 0), 0) / heatmap.length) * 100)
    : null;

  return (
    <Shell requireRole="teacher" title="Class Dashboard" subtitle="Live overview of your class">
      {overviewQ.error && !overviewQ.data ? (
        <ErrorState message="Couldn't load the class overview." onRetry={() => overviewQ.mutate()} />
      ) : loading ? (
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
            {/* Content gaps — doubts the institute's material didn't cover */}
            <section className="card p-5">
              <div className="flex items-center justify-between gap-3 mb-3">
                <h2 className="h-section flex items-center gap-2">
                  <Icon name="target" size={16} className="text-amber-500" /> Content gaps
                  {gaps.length > 0 && <span className="badge-amber">{gaps.length}</span>}
                </h2>
                <Link href="/teacher/materials" className="btn-ghost text-xs px-3 py-1.5">
                  Upload material
                </Link>
              </div>
              <p className="text-xs muted mb-3">Doubts from the last 14 days that your uploaded notes didn&apos;t clearly cover.</p>
              {gaps.length === 0 ? (
                <EmptyState icon={<Icon name="check" size={26} className="text-emerald-500" />} title="No gaps found" hint="Every recent doubt was covered by your study material." />
              ) : (
                <ul className="space-y-2 text-sm">
                  {gaps.map((g, i) => (
                    <li key={i} className="panel p-3 flex items-start justify-between gap-3">
                      <span className="text-slate-700 dark:text-slate-200">{g.question}</span>
                      <span className="badge-amber shrink-0">{g.count}×</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Answer quality — student ratings + coverage of AI answers */}
            <section className="card p-5">
              <h2 className="h-section mb-3 flex items-center gap-2">
                <Icon name="mastery" size={16} /> Answer quality · last 7 days
              </h2>
              {!quality ? (
                <EmptyState icon={<Icon name="mastery" size={26} />} title="No data yet" hint="Once students ask doubts and rate answers, quality shows up here." />
              ) : (
                <div className="grid grid-cols-3 gap-3">
                  <Stat icon={<Icon name="check" />} label="Rated helpful" value={quality.helpful_pct != null ? `${quality.helpful_pct}%` : "—"} accent="text-emerald-500 dark:text-emerald-400" />
                  <Stat icon={<Icon name="concepts" />} label="Covered by notes" value={quality.answerable_pct != null ? `${quality.answerable_pct}%` : "—"} />
                  <Stat icon={<Icon name="doubt" />} label="Doubts (rated)" value={`${quality.doubts} (${quality.rated})`} />
                </div>
              )}
            </section>
          </div>

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
                    className="text-xs text-brand dark:text-violet-400 hover:underline whitespace-nowrap ml-3"
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
              <TrendChart data={monthly} xKey="month" yKey="avg_pct" percent
                          label={monthlyStudent ? "Score" : "Avg score"} />
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
                    {c.subject && <p className="text-xs text-brand dark:text-violet-400 mt-0.5">{c.subject}</p>}
                    {c.source?.source && (
                      <Link href="/teacher/materials" className="text-xs muted hover:underline mt-0.5 block" title="Covered in your study material">
                        Notes: {c.source.source}
                        {c.source.page != null && c.source.page !== "" ? ` · p. ${c.source.page}` : ""}
                      </Link>
                    )}
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
