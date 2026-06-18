import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { EmptyState, Stat, SkeletonCard } from "../../components/ui";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";

function heatColor(score) {
  if (score >= 0.8) return "bg-green-500";
  if (score >= 0.5) return "bg-amber-400";
  if (score > 0) return "bg-red-400";
  return "bg-slate-200";
}

export default function TeacherDashboard() {
  const [overview, setOverview] = useState({ heatmap: [], alerts: [], top_doubts: [] });
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      const institute_id = user?.user_metadata?.institute_id || "";
      // Independent calls — one failing must not blank the rest of the dashboard.
      const [ov, subs] = await Promise.allSettled([
        api(`/teacher/overview?institute_id=${institute_id}`),
        api(`/teacher/submissions?institute_id=${institute_id}`),
      ]);
      if (ov.status === "fulfilled") setOverview(ov.value);
      else console.error("overview failed", ov.reason);
      if (subs.status === "fulfilled") setSubmissions(subs.value.submissions || []);
      else console.error("submissions failed", subs.reason);
      setLoading(false);
    })();
  }, []);

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
            <Stat icon="🚨" label="At-risk students" value={alerts.length} accent="text-rose-500 dark:text-neon-rose" />
            <Stat icon="🧩" label="Concepts tracked" value={heatmap.length} />
            <Stat icon="📊" label="Avg class mastery" value={avgMastery != null ? `${avgMastery}%` : "—"} />
            <Stat icon="💬" label="Hot doubts" value={topDoubts.length} />
          </div>

          {weakest && (
            <div className="card p-4 flex items-center gap-3 bg-brand-soft">
              <span className="text-xl">🎯</span>
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
              🚨 At-risk students
              {alerts.length > 0 && <span className="badge bg-neon-rose/10 text-rose-600 dark:text-neon-rose border border-neon-rose/30">{alerts.length}</span>}
            </h2>
            {alerts.length === 0 && (
              <EmptyState icon="✅" title="No alerts right now" hint="Every student is engaged. We'll flag anyone who falls behind." />
            )}
            <div className="space-y-2">
              {alerts.map((a) => (
                <div
                  key={a.id}
                  className="flex items-start justify-between rounded-xl border border-neon-rose/20 bg-neon-rose/5 p-3"
                >
                  <div>
                    <p className="text-sm font-medium text-neon-rose">
                      Risk {a.risk_score}/100 · {a.alert_type}
                    </p>
                    <p className="text-sm text-slate-600 dark:text-slate-300">{a.message}</p>
                    <p className="text-xs muted mt-1">{a.suggested_action}</p>
                  </div>
                  <button
                    onClick={() => markRead(a.id)}
                    className="text-xs text-neon-violet hover:underline whitespace-nowrap ml-3"
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
              <EmptyState icon="💬" title="No doubts logged yet" hint="Questions your students ask the AI tutor will surface here." />
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

          {/* Class concept heatmap — full width */}
          <section className="card p-5">
            <h2 className="h-section mb-3">Class concept heatmap</h2>
            {heatmap.length === 0 ? (
              <EmptyState icon="🧩" title="No data yet" hint="Once students take tests, per-concept class mastery appears here." />
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

          {/* Submitted tests — results students have completed */}
          <section className="card p-5">
            <h2 className="h-section mb-3 flex items-center gap-2">
              📝 Submitted tests
              {submissions.length > 0 && <span className="badge-brand">{submissions.length}</span>}
            </h2>
            {submissions.length === 0 ? (
              <EmptyState
                icon="📝"
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
