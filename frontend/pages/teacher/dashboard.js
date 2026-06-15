import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
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
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      const institute_id = user?.user_metadata?.institute_id || "";
      try {
        const data = await api(`/teacher/overview?institute_id=${institute_id}`);
        setOverview(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function markRead(alertId) {
    await api("/teacher/alerts/read", { method: "POST", body: { alert_id: alertId } });
    setOverview((o) => ({ ...o, alerts: o.alerts.filter((a) => a.id !== alertId) }));
  }

  return (
    <Shell requireRole="teacher" title="Class Dashboard">
      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : (
        <div className="space-y-6">
          {/* At-risk alerts */}
          <section className="bg-white border rounded-xl p-5">
            <h2 className="font-semibold mb-3">
              🚨 At-risk students ({overview.alerts?.length || 0})
            </h2>
            {(!overview.alerts || overview.alerts.length === 0) && (
              <p className="text-slate-400 text-sm">No alerts right now.</p>
            )}
            <div className="space-y-2">
              {(overview.alerts || []).map((a) => (
                <div
                  key={a.id}
                  className="flex items-start justify-between border rounded-lg p-3"
                >
                  <div>
                    <p className="text-sm font-medium">
                      Risk {a.risk_score}/100 · {a.alert_type}
                    </p>
                    <p className="text-sm text-slate-600">{a.message}</p>
                    <p className="text-xs text-slate-400 mt-1">{a.suggested_action}</p>
                  </div>
                  <button
                    onClick={() => markRead(a.id)}
                    className="text-xs text-brand hover:underline whitespace-nowrap ml-3"
                  >
                    Mark read
                  </button>
                </div>
              ))}
            </div>
          </section>

          {/* Class concept heatmap */}
          <section className="bg-white border rounded-xl p-5">
            <h2 className="font-semibold mb-3">Class concept heatmap</h2>
            {(!overview.heatmap || overview.heatmap.length === 0) ? (
              <p className="text-slate-400 text-sm">No data yet.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {overview.heatmap.map((c, i) => (
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

          {/* Top doubts */}
          <section className="bg-white border rounded-xl p-5">
            <h2 className="font-semibold mb-3">Most asked doubts this week</h2>
            {(!overview.top_doubts || overview.top_doubts.length === 0) ? (
              <p className="text-slate-400 text-sm">No doubts logged yet.</p>
            ) : (
              <ul className="list-disc pl-5 space-y-1 text-sm text-slate-700">
                {overview.top_doubts.map((d, i) => (
                  <li key={i}>
                    {d.question} <span className="text-slate-400">({d.count}×)</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </Shell>
  );
}
