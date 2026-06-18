import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { EmptyState, SkeletonCard, Stat } from "../../components/ui";
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

  // Backend returns a `children` array; fall back to the single-child shape.
  const children = data
    ? data.children?.length
      ? data.children
      : data.student_name
        ? [{ student_name: data.student_name, summary: data.summary, latest_report: data.latest_report }]
        : []
    : [];

  return (
    <Shell
      requireRole="parent"
      title="Weekly Progress Report"
      subtitle="A plain-language summary of how your child is doing"
    >
      {loading ? (
        <div className="space-y-4 max-w-2xl">
          <SkeletonCard lines={1} />
          <div className="grid grid-cols-3 gap-4">
            <SkeletonCard lines={1} />
            <SkeletonCard lines={1} />
            <SkeletonCard lines={1} />
          </div>
          <SkeletonCard lines={4} />
        </div>
      ) : !children.length ? (
        <div className="card">
          <EmptyState
            icon="📨"
            title="No child linked to your account yet"
            hint="When your child signs up, they enter your email — then their progress shows here automatically."
          />
        </div>
      ) : (
        <div className="space-y-10 max-w-2xl">
          {children.map((child, idx) => (
            <ChildReport key={idx} child={child} />
          ))}
        </div>
      )}
    </Shell>
  );
}

function ChildReport({ child }) {
  return (
    <div className="space-y-5">
      {/* Child header */}
      <div className="card p-5 flex items-center gap-4">
        <span className="grid place-items-center h-12 w-12 rounded-2xl bg-brand-grad text-white text-lg shadow-glow shrink-0">
          {String(child.student_name || "?").charAt(0).toUpperCase()}
        </span>
        <div className="min-w-0">
          <p className="stat-label">Child</p>
          <p className="text-xl font-bold tracking-tight truncate">
            {child.student_name || "—"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Stat icon="📝" label="Tests this week" value={child.summary?.tests_taken ?? 0} />
        <Stat
          icon="🎯"
          label="Avg score"
          value={child.summary?.avg_pct != null ? `${child.summary.avg_pct}%` : "—"}
        />
        <Stat icon="💬" label="Doubts asked" value={child.summary?.doubts ?? 0} />
      </div>

      <div className="card p-6">
        <h2 className="h-section mb-3 flex items-center gap-2">
          <span>🧠</span> This week&apos;s note
        </h2>
        <p className="text-slate-600 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
          {child.latest_report || "Your first weekly report will arrive on Sunday."}
        </p>
      </div>

      {child.summary?.weak_concepts?.length > 0 && (
        <div className="card p-6">
          <h2 className="h-section mb-3 flex items-center gap-2">
            <span>📌</span> Focus areas
          </h2>
          <div className="flex flex-wrap gap-2">
            {child.summary.weak_concepts.map((c, i) => (
              <span
                key={i}
                className="badge bg-neon-rose/10 text-rose-600 dark:text-neon-rose border border-neon-rose/30"
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
