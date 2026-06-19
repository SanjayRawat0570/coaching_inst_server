// Small shared presentational helpers used across role dashboards.

export function EmptyState({ icon, title, hint, action }) {
  return (
    <div className="empty-state">
      {icon && <span className="icon">{icon}</span>}
      <p className="font-semibold">{title}</p>
      {hint && <p className="muted text-sm mt-1 max-w-sm">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// A few stacked shimmer bars; `lines` controls how many.
export function Skeleton({ className = "" }) {
  return <div className={`skeleton ${className}`} />;
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="card p-5 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`h-3 ${i % 2 ? "w-2/3" : "w-full"}`} />
      ))}
    </div>
  );
}

// Coloured percentage pill for a test result (green ≥60, amber ≥35, else red).
export function ScorePill({ percent }) {
  if (percent == null) return <span className="muted">—</span>;
  const tone =
    percent >= 60
      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 border-emerald-500/30"
      : percent >= 35
      ? "bg-amber-400/10 text-amber-600 dark:text-amber-300 border-amber-400/30"
      : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30";
  return <span className={`badge border ${tone}`}>{percent}%</span>;
}

// A compact table of recent evaluated tests, shared across dashboards.
// Pass showStudent to include a student-name column (admin view).
export function ResultsTable({ rows = [], showStudent = false }) {
  const fmt = (v) => (v ? new Date(v).toLocaleDateString() : "—");
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
            {showStudent && <th className="py-2 pr-3 font-medium">Student</th>}
            <th className="py-2 pr-3 font-medium">Subject</th>
            <th className="py-2 pr-3 font-medium">Score</th>
            <th className="py-2 pr-3 font-medium">%</th>
            <th className="py-2 font-medium">Submitted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-slate-100 dark:border-white/5">
              {showStudent && <td className="py-2 pr-3 font-medium">{r.student_name}</td>}
              <td className="py-2 pr-3">{r.subject || "Mixed"}</td>
              <td className="py-2 pr-3 tabular-nums">
                {r.score ?? "—"}
                {r.total_marks ? ` / ${r.total_marks}` : ""}
              </td>
              <td className="py-2 pr-3"><ScorePill percent={r.percent} /></td>
              <td className="py-2 muted">{fmt(r.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Stat tile: icon node in a tile, big value, label, optional sub line.
export function Stat({ icon, label, value, accent = "grad-text", sub }) {
  return (
    <div className="card card-hover p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="stat-label">{label}</p>
          <p className={`stat-value mt-1.5 ${accent}`}>{value}</p>
        </div>
        {icon && <span className="icon-tile h-10 w-10 shrink-0">{icon}</span>}
      </div>
      {sub && <p className="muted text-xs mt-2">{sub}</p>}
    </div>
  );
}
