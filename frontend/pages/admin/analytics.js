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
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
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
                  <li key={i} className="flex justify-between border-b border-white/10 pb-1.5">
                    <span className="muted">{s.label}</span>
                    <span className="font-medium">{s.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

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
