import Icon from "./Icon";
import { ErrorState, Skeleton } from "./ui";
import { useApi } from "../lib/hooks";

const JOB_NAMES = {
  at_risk_nightly: "At-risk check (nightly)",
  inactivity_alerts_nightly: "Inactivity alerts (nightly)",
  doubt_clusters_nightly: "Doubt clusters (nightly)",
  parent_reports_weekly: "Parent reports (Sunday)",
  study_plans_weekly: "Study plans (Monday)",
  flashcard_reminders: "Flashcard reminders (5 min)",
};

function Dot({ ok }: { ok: boolean | null }) {
  const tone = ok == null ? "bg-slate-400" : ok ? "bg-emerald-500" : "bg-rose-500";
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${tone}`} aria-hidden />;
}

function Check({ label, ok, note }: { label: string; ok: boolean | null; note?: string }) {
  return (
    <div className="panel p-3 flex items-center gap-2.5">
      <Dot ok={ok} />
      <div className="min-w-0">
        <p className="text-sm font-medium">{label}</p>
        <p className="muted text-xs">{note ?? (ok == null ? "not configured" : ok ? "OK" : "down")}</p>
      </div>
    </div>
  );
}

const ago = (iso?: string | null) => {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 0) return `in ${Math.round(-s / 60)} min`;
  if (s < 90) return `${s}s ago`;
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};

const uptime = (s: number) =>
  s < 3600 ? `${Math.round(s / 60)} min` : s < 172800 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} days`;

/** Admin "System health": backend uptime, /ready checks, RAG server, scheduled jobs,
 * and the last hour's requests (this backend process). Refreshes every 30 s. */
export default function SystemHealth() {
  const q = useApi("/admin/system-health", { refreshInterval: 30000 });
  const h = q.data;
  return (
    <div className="card p-5">
      <h2 className="font-semibold mb-3 flex items-center gap-2">
        <Icon name="analytics" size={16} /> System health
        {h && (
          <span className={h.ready ? "badge-green" : "badge-amber"}>{h.ready ? "ready" : "starting / degraded"}</span>
        )}
      </h2>
      {q.error && !h ? (
        <ErrorState compact message="Couldn't reach the health check." onRetry={() => q.mutate()} />
      ) : !h ? (
        <Skeleton className="h-28 w-full" />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Check label="Backend" ok note={`up ${uptime(h.uptime_s)}`} />
            <Check label="Database (Supabase)" ok={h.checks.supabase} />
            <Check label="RAG server" ok={h.checks.rag_server} />
            <Check label="Embedding model" ok={h.checks.embedder_loaded}
                   note={h.checks.embedder_loaded ? "loaded" : "loading…"} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="panel p-3"><p className="muted text-xs">Requests (1 h)</p><p className="font-semibold tabular-nums">{h.requests.requests}</p></div>
            <div className="panel p-3"><p className="muted text-xs">Errors (5xx)</p><p className={`font-semibold tabular-nums ${h.requests.errors_5xx ? "text-rose-600 dark:text-rose-400" : ""}`}>{h.requests.errors_5xx}</p></div>
            <div className="panel p-3"><p className="muted text-xs">Slow (&gt; 2 s)</p><p className="font-semibold tabular-nums">{h.requests.slow}</p></div>
            <div className="panel p-3"><p className="muted text-xs">p50 / p95</p><p className="font-semibold tabular-nums">{h.requests.p50_ms ?? "—"} / {h.requests.p95_ms ?? "—"} ms</p></div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
                  <th className="py-2 pr-3 font-medium">Scheduled job</th>
                  <th className="py-2 pr-3 font-medium">Last run</th>
                  <th className="py-2 pr-3 font-medium">Took</th>
                  <th className="py-2 font-medium">Next</th>
                </tr>
              </thead>
              <tbody>
                {!h.scheduler.running && (
                  <tr><td colSpan={4} className="py-2 muted">The scheduler isn't running on this backend.</td></tr>
                )}
                {h.scheduler.jobs.map((j) => (
                  <tr key={j.id} className="border-b border-slate-100 dark:border-white/5">
                    <td className="py-2 pr-3">{JOB_NAMES[j.id] || j.id}</td>
                    <td className="py-2 pr-3">
                      {j.last_run ? (
                        <span className="inline-flex items-center gap-1.5">
                          <Dot ok={j.last_run.status === "failed" ? false : true} />
                          {ago(j.last_run.started_at)}
                          {j.last_run.status !== "ok" && <span className="muted">({j.last_run.status})</span>}
                        </span>
                      ) : (
                        <span className="muted">not yet</span>
                      )}
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{j.last_run ? `${j.last_run.duration_s} s` : "—"}</td>
                    <td className="py-2 muted">{ago(j.next_run)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted text-xs">Numbers are for the backend instance that answered.</p>
        </div>
      )}
    </div>
  );
}
