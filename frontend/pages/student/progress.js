import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import Shell from "../../components/Shell";
import { EmptyState, Stat, SkeletonCard } from "../../components/ui";
import { api } from "../../lib/api";

function scoreColor(score) {
  if (score >= 0.8) return "#16a34a"; // strong
  if (score >= 0.5) return "#f59e0b"; // medium
  return "#dc2626"; // weak
}

export default function ProgressPage() {
  const [data, setData] = useState({ weakness_map: [], profile: {} });
  const [cards, setCards] = useState([]);
  const [revealed, setRevealed] = useState({});
  const [loading, setLoading] = useState(true);
  const [examEdit, setExamEdit] = useState(false);
  const [examInput, setExamInput] = useState("");
  const [savingExam, setSavingExam] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [progress, due] = await Promise.all([
        api("/progress"),
        api("/flashcards/due"),
      ]);
      setData(progress);
      setCards(due.cards || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function review(cardId, quality) {
    await api("/flashcards/review", { method: "POST", body: { card_id: cardId, quality } });
    setCards((c) => c.filter((x) => x.id !== cardId));
  }

  async function saveExam() {
    setSavingExam(true);
    try {
      const exam = examInput.trim();
      await api("/profile", { method: "POST", body: { target_exam: exam } });
      setData((d) => ({ ...d, profile: { ...d.profile, target_exam: exam || null } }));
      setExamEdit(false);
    } catch (e) {
      console.error(e);
    } finally {
      setSavingExam(false);
    }
  }

  const chart = (data.weakness_map || []).map((w) => ({
    name: w.concept,
    score: Math.round((w.score || 0) * 100),
    raw: w.score || 0,
  }));

  return (
    <Shell
      requireRole="student"
      title="My Progress"
      subtitle="Track your streak, mastery, and what to revise next"
    >
      {loading ? (
        <div className="grid md:grid-cols-3 gap-4">
          <SkeletonCard lines={1} />
          <SkeletonCard lines={1} />
          <SkeletonCard lines={1} />
          <div className="md:col-span-3">
            <SkeletonCard lines={5} />
          </div>
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {/* Stat cards */}
          <Stat icon="🔥" label="Day streak" value={`${data.profile?.streak_days ?? 0}`} sub="Keep it alive — study daily" />
          <Stat icon="⭐" label="XP points" value={data.profile?.xp_points ?? 0} />
          {/* Target exam — editable */}
          <div className="card card-hover p-5">
            <span className="text-xl">🎯</span>
            {examEdit ? (
              <div className="mt-2 flex flex-col gap-2">
                <input
                  className="input"
                  placeholder="e.g. JEE Advanced, NEET"
                  value={examInput}
                  onChange={(e) => setExamInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveExam()}
                  autoFocus
                />
                <div className="flex gap-2">
                  <button className="btn-primary flex-1 py-1 text-sm" onClick={saveExam} disabled={savingExam}>
                    {savingExam ? "Saving…" : "Save"}
                  </button>
                  <button className="btn-ghost flex-1 py-1 text-sm" onClick={() => setExamEdit(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <p className="stat-value mt-2 text-slate-900 dark:text-white">
                  {data.profile?.target_exam || "—"}
                </p>
                <p className="stat-label mt-1">Target exam</p>
                <button
                  className="text-neon-violet text-xs mt-1 hover:underline"
                  onClick={() => {
                    setExamInput(data.profile?.target_exam || "");
                    setExamEdit(true);
                  }}
                >
                  {data.profile?.target_exam ? "Change" : "Set target exam"}
                </button>
              </>
            )}
          </div>

          {/* Weakness chart */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3">Concept mastery (%)</h2>
            {chart.length === 0 ? (
              <EmptyState
                icon="📊"
                title="No mastery data yet"
                hint="Take a test and your per-concept weakness map will appear here."
              />
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(220, chart.length * 34)}>
                <BarChart data={chart} layout="vertical" margin={{ left: 40 }}>
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12, fill: "#94a3b8" }} />
                  <Tooltip
                    contentStyle={{ background: "#0b1120", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#e2e8f0" }}
                    cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  />
                  <Bar dataKey="score" radius={[0, 6, 6, 0]}>
                    {chart.map((entry, i) => (
                      <Cell key={i} fill={scoreColor(entry.raw)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Flashcards due */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3 flex items-center gap-2">
              Flashcards due today
              <span className="badge-cyan">{cards.length}</span>
            </h2>
            {cards.length === 0 ? (
              <EmptyState icon="🎉" title="All caught up!" hint="No flashcards are due right now — nice work." />
            ) : (
              <div className="grid md:grid-cols-2 gap-3">
                {cards.map((c) => (
                  <div key={c.id} className="panel p-4">
                    <p className="text-xs muted mb-1">{c.concept}</p>
                    <p className="font-medium">{c.question}</p>
                    {revealed[c.id] ? (
                      <>
                        <p className="mt-2 text-slate-600 dark:text-slate-300">{c.answer}</p>
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => review(c.id, 1)}
                            className="flex-1 bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-500/30 rounded-lg py-1 text-sm hover:bg-rose-500/25"
                          >
                            Forgot
                          </button>
                          <button
                            onClick={() => review(c.id, 3)}
                            className="flex-1 bg-amber-400/15 text-amber-600 dark:text-amber-300 border border-amber-400/30 rounded-lg py-1 text-sm hover:bg-amber-400/25"
                          >
                            Hard
                          </button>
                          <button
                            onClick={() => review(c.id, 5)}
                            className="flex-1 bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border border-emerald-500/30 rounded-lg py-1 text-sm hover:bg-emerald-500/25"
                          >
                            Easy
                          </button>
                        </div>
                      </>
                    ) : (
                      <button
                        onClick={() => setRevealed({ ...revealed, [c.id]: true })}
                        className="mt-2 text-neon-violet text-sm hover:underline"
                      >
                        Show answer
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Shell>
  );
}
