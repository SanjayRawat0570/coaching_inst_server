// Small shared presentational helpers used across role dashboards.

export function EmptyState({ icon = "✨", title, hint, action }) {
  return (
    <div className="empty-state">
      <span className="icon">{icon}</span>
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

// Stat tile: icon, label, big value, optional accent class for the value.
export function Stat({ icon, label, value, accent = "grad-text", sub }) {
  return (
    <div className="card card-hover p-5">
      {icon && <span className="text-xl">{icon}</span>}
      <p className={`stat-value mt-2 ${accent}`}>{value}</p>
      <p className="stat-label mt-1">{label}</p>
      {sub && <p className="muted text-xs mt-1">{sub}</p>}
    </div>
  );
}
