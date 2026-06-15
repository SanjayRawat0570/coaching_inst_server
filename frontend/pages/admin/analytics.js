import { useEffect, useState } from "react";
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
        <p className="text-slate-400">Loading…</p>
      ) : !data ? (
        <p className="text-slate-400">No analytics available.</p>
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

          <div className="bg-white border rounded-xl p-5">
            <h2 className="font-semibold mb-3">Weekly engagement</h2>
            {(!data.engagement || data.engagement.length === 0) ? (
              <p className="text-slate-400 text-sm">Not enough data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={data.engagement}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="active" stroke="#4f46e5" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {data.revenue_signals?.length > 0 && (
            <div className="bg-white border rounded-xl p-5">
              <h2 className="font-semibold mb-3">Revenue signals</h2>
              <ul className="space-y-2 text-sm">
                {data.revenue_signals.map((s, i) => (
                  <li key={i} className="flex justify-between border-b pb-1">
                    <span>{s.label}</span>
                    <span className="font-medium">{s.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}

function Stat({ label, value, accent = "" }) {
  return (
    <div className="bg-white border rounded-xl p-5 text-center">
      <p className={`text-3xl font-bold ${accent}`}>{value}</p>
      <p className="text-xs text-slate-500 mt-1">{label}</p>
    </div>
  );
}
