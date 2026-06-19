import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { EmptyState, SkeletonCard, Stat, ResultsTable } from "../../components/ui";
import Icon from "../../components/Icon";
import ActivityHeatmap from "../../components/ActivityHeatmap";
import { api } from "../../lib/api";

export default function ParentReport() {
  const [data, setData] = useState(null);
  const [heat, setHeat] = useState({ hours: [], total: 0, days: 14 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [report, hm] = await Promise.allSettled([
          api("/parent/report"),
          api("/parent/activity-heatmap"),
        ]);
        if (report.status === "fulfilled") setData(report.value);
        else console.error(report.reason);
        if (hm.status === "fulfilled") setHeat(hm.value);
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
            icon={<Icon name="report" size={26} />}
            title="No child linked to your account yet"
            hint="When your child signs up, they enter your email — then their progress shows here automatically."
          />
        </div>
      ) : (
        <div className="space-y-10 max-w-2xl">
          {/* F6 — when your child studies (24-hour heatmap) */}
          <div className="card p-5">
            <ActivityHeatmap hours={heat.hours} total={heat.total} days={heat.days} />
          </div>
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

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Stat icon={<Icon name="tests" />} label="Tests this week" value={child.summary?.tests_taken ?? 0} />
        <Stat
          icon={<Icon name="target" />}
          label="Avg score"
          value={child.summary?.avg_pct != null ? `${child.summary.avg_pct}%` : "—"}
        />
        <Stat icon={<Icon name="doubt" />} label="Doubts asked" value={child.summary?.doubts ?? 0} />
        <Stat icon={<Icon name="streak" />} label="Day streak" value={child.summary?.streak_days ?? 0} accent="text-amber-500 dark:text-neon-amber" />
      </div>

      {/* F9 — goal: target college + rank, with a progress bar */}
      <GoalCard child={child} />

      <div className="card p-6">
        <h2 className="h-section mb-3 flex items-center gap-2">
          <Icon name="architecture" size={16} /> This week&apos;s note
        </h2>
        <p className="text-slate-600 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
          {child.latest_report || "Your first weekly report will arrive on Sunday."}
        </p>
      </div>

      <div className="card p-6">
        <h2 className="h-section mb-3 flex items-center gap-2">
          <Icon name="tests" size={16} /> Recent test results
        </h2>
        {(!child.recent_tests || child.recent_tests.length === 0) ? (
          <p className="muted text-sm">No graded tests yet. Results appear here once your child submits a test.</p>
        ) : (
          <ResultsTable rows={child.recent_tests} />
        )}
      </div>

      {child.summary?.weak_concepts?.length > 0 && (
        <div className="card p-6">
          <h2 className="h-section mb-3 flex items-center gap-2">
            <Icon name="target" size={16} /> Focus areas
          </h2>
          <div className="flex flex-wrap gap-2">
            {child.summary.weak_concepts.map((c, i) => (
              <span
                key={i}
                className="badge bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/30"
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

function GoalCard({ child }) {
  const [college, setCollege] = useState(child.target_college || "");
  const [rank, setRank] = useState(child.target_rank || "");
  const [progress, setProgress] = useState(child.goal_progress);
  const [editing, setEditing] = useState(!child.target_rank);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const res = await api("/parent/goal", {
        method: "POST",
        body: {
          student_id: child.student_id,
          target_college: college.trim() || null,
          target_rank: rank ? Number(rank) : null,
        },
      });
      setProgress(res.goal_progress);
      setEditing(false);
    } catch (e) {
      alert(e.message);
    } finally {
      setSaving(false);
    }
  }

  const pct = progress ?? 0;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="h-section flex items-center gap-2">
          <Icon name="trophy" size={16} /> Goal
        </h2>
        {!editing && (
          <button onClick={() => setEditing(true)} className="text-brand dark:text-indigo-400 text-xs font-medium hover:underline">
            Edit goal
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <div>
            <label className="stat-label">Target college</label>
            <input className="input mt-1" placeholder="e.g. IIT Bombay" value={college} onChange={(e) => setCollege(e.target.value)} />
          </div>
          <div>
            <label className="stat-label">Target AIR (rank)</label>
            <input className="input mt-1" type="number" min="1" placeholder="e.g. 5000" value={rank} onChange={(e) => setRank(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <button className="btn-primary flex-1 py-1.5 text-sm" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save goal"}
            </button>
            {child.target_rank ? (
              <button className="btn-ghost flex-1 py-1.5 text-sm" onClick={() => setEditing(false)}>Cancel</button>
            ) : null}
          </div>
        </div>
      ) : (
        <>
          <div className="flex items-end justify-between gap-3 mb-2">
            <div>
              <p className="text-xl font-bold tracking-tight">{college || "—"}</p>
              <p className="muted text-sm">Target AIR {rank ? Number(rank).toLocaleString() : "—"}</p>
            </div>
            <p className="text-2xl font-bold text-brand dark:text-indigo-400 tabular-nums">{pct}%</p>
          </div>
          <div className="h-3 rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
            <div className="h-full rounded-full bg-brand-grad transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="muted text-xs mt-2">
            {child.predicted_rank
              ? `Current predicted ${child.predicted_rank}. ${pct >= 100 ? "On track to beat the goal! 🎉" : "Progress toward the target rank."}`
              : "Take a test so we can predict a rank and track progress."}
          </p>
        </>
      )}
    </div>
  );
}
