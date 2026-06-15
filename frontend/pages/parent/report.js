import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";

export default function ParentReport() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        setData(await api("/parent/report"));
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <Shell requireRole="parent" title="Weekly Progress Report">
      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : !data ? (
        <p className="text-slate-400">No report available yet.</p>
      ) : (
        <div className="space-y-4 max-w-2xl">
          <div className="bg-white border rounded-xl p-5">
            <p className="text-sm text-slate-500">Child</p>
            <p className="text-xl font-semibold">{data.student_name || "—"}</p>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <Stat label="Tests this week" value={data.summary?.tests_taken ?? 0} />
            <Stat label="Avg score" value={data.summary?.avg_pct != null ? `${data.summary.avg_pct}%` : "—"} />
            <Stat label="Doubts asked" value={data.summary?.doubts ?? 0} />
          </div>

          <div className="bg-white border rounded-xl p-5">
            <h2 className="font-semibold mb-2">This week&apos;s note</h2>
            <p className="text-slate-700 whitespace-pre-wrap leading-relaxed">
              {data.latest_report || "Your first weekly report will arrive on Sunday."}
            </p>
          </div>

          {data.summary?.weak_concepts?.length > 0 && (
            <div className="bg-white border rounded-xl p-5">
              <h2 className="font-semibold mb-2">Focus areas</h2>
              <div className="flex flex-wrap gap-2">
                {data.summary.weak_concepts.map((c, i) => (
                  <span key={i} className="bg-red-50 text-red-700 px-3 py-1 rounded-full text-sm">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Shell>
  );
}

function Stat({ label, value }) {
  return (
    <div className="bg-white border rounded-xl p-4 text-center">
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}
