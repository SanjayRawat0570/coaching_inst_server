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

  const chart = (data.weakness_map || []).map((w) => ({
    name: w.concept,
    score: Math.round((w.score || 0) * 100),
    raw: w.score || 0,
  }));

  return (
    <Shell requireRole="student" title="My Progress">
      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {/* Stat cards */}
          <div className="card p-5">
            <p className="text-sm muted">🔥 Streak</p>
            <p className="text-3xl font-bold grad-text">{data.profile?.streak_days ?? 0} days</p>
          </div>
          <div className="card p-5">
            <p className="text-sm muted">⭐ XP</p>
            <p className="text-3xl font-bold grad-text">{data.profile?.xp_points ?? 0}</p>
          </div>
          <div className="card p-5">
            <p className="text-sm muted">🎯 Target</p>
            <p className="text-3xl font-bold">{data.profile?.target_exam || "—"}</p>
          </div>

          {/* Weakness chart */}
          <div className="card p-5 md:col-span-3">
            <h2 className="font-semibold mb-3">Concept mastery (%)</h2>
            {chart.length === 0 ? (
              <p className="muted text-sm">
                Take a test to start building your weakness map.
              </p>
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
            <h2 className="font-semibold mb-3">
              Flashcards due today ({cards.length})
            </h2>
            {cards.length === 0 ? (
              <p className="muted text-sm">Nothing due — nice work! 🎉</p>
            ) : (
              <div className="grid md:grid-cols-2 gap-3">
                {cards.map((c) => (
                  <div key={c.id} className="rounded-xl border border-white/10 bg-ink-900/50 p-4">
                    <p className="text-xs muted mb-1">{c.concept}</p>
                    <p className="font-medium">{c.question}</p>
                    {revealed[c.id] ? (
                      <>
                        <p className="mt-2 text-slate-300">{c.answer}</p>
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => review(c.id, 1)}
                            className="flex-1 bg-rose-500/15 text-rose-300 border border-rose-500/30 rounded-lg py-1 text-sm hover:bg-rose-500/25"
                          >
                            Forgot
                          </button>
                          <button
                            onClick={() => review(c.id, 3)}
                            className="flex-1 bg-amber-400/15 text-amber-300 border border-amber-400/30 rounded-lg py-1 text-sm hover:bg-amber-400/25"
                          >
                            Hard
                          </button>
                          <button
                            onClick={() => review(c.id, 5)}
                            className="flex-1 bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 rounded-lg py-1 text-sm hover:bg-emerald-500/25"
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
