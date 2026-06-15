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
          <div className="bg-white border rounded-xl p-5">
            <p className="text-sm text-slate-500">🔥 Streak</p>
            <p className="text-3xl font-bold">{data.profile?.streak_days ?? 0} days</p>
          </div>
          <div className="bg-white border rounded-xl p-5">
            <p className="text-sm text-slate-500">⭐ XP</p>
            <p className="text-3xl font-bold">{data.profile?.xp_points ?? 0}</p>
          </div>
          <div className="bg-white border rounded-xl p-5">
            <p className="text-sm text-slate-500">🎯 Target</p>
            <p className="text-3xl font-bold">{data.profile?.target_exam || "—"}</p>
          </div>

          {/* Weakness chart */}
          <div className="bg-white border rounded-xl p-5 md:col-span-3">
            <h2 className="font-semibold mb-3">Concept mastery (%)</h2>
            {chart.length === 0 ? (
              <p className="text-slate-400 text-sm">
                Take a test to start building your weakness map.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(220, chart.length * 34)}>
                <BarChart data={chart} layout="vertical" margin={{ left: 40 }}>
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12 }} />
                  <Tooltip />
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
          <div className="bg-white border rounded-xl p-5 md:col-span-3">
            <h2 className="font-semibold mb-3">
              Flashcards due today ({cards.length})
            </h2>
            {cards.length === 0 ? (
              <p className="text-slate-400 text-sm">Nothing due — nice work! 🎉</p>
            ) : (
              <div className="grid md:grid-cols-2 gap-3">
                {cards.map((c) => (
                  <div key={c.id} className="border rounded-lg p-4">
                    <p className="text-xs text-slate-400 mb-1">{c.concept}</p>
                    <p className="font-medium">{c.question}</p>
                    {revealed[c.id] ? (
                      <>
                        <p className="mt-2 text-slate-700">{c.answer}</p>
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => review(c.id, 1)}
                            className="flex-1 bg-red-100 text-red-700 rounded py-1 text-sm"
                          >
                            Forgot
                          </button>
                          <button
                            onClick={() => review(c.id, 3)}
                            className="flex-1 bg-amber-100 text-amber-700 rounded py-1 text-sm"
                          >
                            Hard
                          </button>
                          <button
                            onClick={() => review(c.id, 5)}
                            className="flex-1 bg-green-100 text-green-700 rounded py-1 text-sm"
                          >
                            Easy
                          </button>
                        </div>
                      </>
                    ) : (
                      <button
                        onClick={() => setRevealed({ ...revealed, [c.id]: true })}
                        className="mt-2 text-brand text-sm hover:underline"
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
