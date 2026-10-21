import { useEffect, useMemo, useState } from "react";
import Shell from "../../components/Shell";
import { EmptyState } from "../../components/ui";
import Icon from "../../components/Icon";
import { supabase } from "../../lib/supabase";
import { api } from "../../lib/api";

const DURATION_SEC = 20 * 60; // 20 minutes

export default function TestPage() {
  const [tests, setTests] = useState([]);
  const [active, setActive] = useState(null); // {id, questions}
  const [answers, setAnswers] = useState({}); // index -> chosen option index
  const [timeLeft, setTimeLeft] = useState(DURATION_SEC);
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  // Load this student's ready tests (RLS limits to own rows)
  useEffect(() => {
    (async () => {
      const { data } = await supabase
        .from("tests")
        .select("id, subject, questions, status, created_at")
        .eq("status", "ready")
        .order("created_at", { ascending: false });
      setTests(data || []);
    })();
  }, []);

  // Countdown
  useEffect(() => {
    if (!active || result) return;
    if (timeLeft <= 0) {
      submit();
      return;
    }
    const t = setTimeout(() => setTimeLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [active, timeLeft, result]);

  const mmss = useMemo(() => {
    const m = String(Math.floor(timeLeft / 60)).padStart(2, "0");
    const s = String(timeLeft % 60).padStart(2, "0");
    return `${m}:${s}`;
  }, [timeLeft]);

  function begin(test) {
    setActive(test);
    setAnswers({});
    setTimeLeft(DURATION_SEC);
    setResult(null);
  }

  async function submit() {
    if (!active || submitting) return;
    setSubmitting(true);
    const ordered = (active.questions || []).map((_, i) =>
      answers[i] === undefined ? null : answers[i]
    );
    try {
      const res = await api("/test/submit", {
        method: "POST",
        body: { test_id: active.id, answers: ordered },
      });
      setResult(res);
    } catch (e) {
      alert(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  const answered = active
    ? Object.values(answers).filter(
        (v) => typeof v === "number" || (typeof v === "string" && v.trim() !== "")
      ).length
    : 0;
  const totalQ = active ? active.questions.length : 0;
  const progressPct = totalQ ? Math.round((answered / totalQ) * 100) : 0;

  return (
    <Shell requireRole="student" title="Tests" subtitle="Personalised practice assigned by your teacher">
      {/* Test picker */}
      {!active && (
        <div className="space-y-3">
          {tests.length === 0 ? (
            <div className="card">
              <EmptyState
                icon={<Icon name="tests" size={26} />}
                title="No tests ready yet"
                hint="Your teacher will assign a personalised test soon. Check back later."
              />
            </div>
          ) : (
            tests.map((t) => (
              <div
                key={t.id}
                className="card card-hover p-4 flex items-center justify-between"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="icon-tile h-11 w-11 shrink-0"><Icon name="tests" size={20} /></span>
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{t.subject || "Mixed"} test</p>
                    <p className="text-sm muted">
                      {(t.questions || []).length} questions · 20 min · negative marking
                    </p>
                  </div>
                </div>
                <button onClick={() => begin(t)} className="btn-primary shrink-0">
                  Start <Icon name="arrowRight" size={16} />
                </button>
              </div>
            ))
          )}
        </div>
      )}

      {/* Active test */}
      {active && !result && (
        <div>
          <div className="sticky top-16 z-10 panel backdrop-blur px-4 py-3 mb-4">
            <div className="flex items-center justify-between">
              <span className="text-sm muted">
                <span className="font-semibold text-slate-700 dark:text-slate-200">{answered}</span>/{totalQ} answered
              </span>
              <span
                className={
                  "inline-flex items-center gap-1.5 font-mono text-lg tabular-nums " +
                  (timeLeft < 60 ? "text-rose-500 dark:text-neon-rose animate-pulse" : "text-slate-700 dark:text-slate-200")
                }
              >
                <Icon name="clock" size={16} /> {mmss}
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
              <div
                className="h-full rounded-full bg-brand-grad transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          <div className="space-y-5">
            {active.questions.map((q, i) => {
              const isTheory = q.type === "theory" || (!q.options && q.model_answer !== undefined);
              return (
              <div key={i} className="card p-4">
                <div className="flex justify-between text-xs muted mb-1">
                  <span>Q{i + 1} · {q.concept}</span>
                  <span>{isTheory ? `+${q.marks ?? 5}` : `+${q.marks ?? 4} / −${q.negative ?? 1}`}</span>
                </div>
                <p className="font-medium mb-3">{q.question}</p>
                {isTheory ? (
                  <textarea
                    className="input text-sm"
                    rows={5}
                    placeholder="Write your answer — show your steps and reasoning."
                    value={typeof answers[i] === "string" ? answers[i] : ""}
                    onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })}
                  />
                ) : (
                  <div className="grid gap-2">
                    {(q.options || []).map((opt, oi) => (
                      <label
                        key={oi}
                        className={
                          "border rounded-lg px-3 py-2 cursor-pointer transition " +
                          (answers[i] === oi
                            ? "border-brand bg-brand/15 text-brand dark:text-white font-medium"
                            : "border-slate-200 hover:bg-slate-100 dark:border-white/10 dark:hover:bg-white/5")
                        }
                      >
                        <input
                          type="radio"
                          name={`q${i}`}
                          className="mr-2"
                          checked={answers[i] === oi}
                          onChange={() => setAnswers({ ...answers, [i]: oi })}
                        />
                        {opt}
                      </label>
                    ))}
                  </div>
                )}
              </div>
              );
            })}
          </div>

          <button
            onClick={submit}
            disabled={submitting}
            className="btn-success mt-6 px-6"
          >
            {submitting ? "Submitting…" : "Submit test"}
          </button>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="card p-8 max-w-md mx-auto text-center shadow-soft-lg">
          <span className="grid place-items-center h-16 w-16 mx-auto rounded-2xl bg-brand-grad text-white mb-4 shadow-glow"><Icon name="trophy" size={30} className="text-white" /></span>
          <p className="stat-label">Your score</p>
          <p className="text-5xl font-extrabold grad-text mt-1">
            {result.score ?? 0}
            <span className="text-lg muted font-bold"> / {result.total_marks ?? result.evaluation?.total_marks ?? 0}</span>
          </p>
          {result.air_rank && (
            <div className="panel inline-flex items-center gap-2 mt-5 px-4 py-2 text-sm">
              <Icon name="analytics" size={15} className="text-cyan-600 dark:text-neon-cyan" /> Predicted rank:
              <span className="font-semibold text-cyan-600 dark:text-neon-cyan">{result.air_rank}</span>
            </div>
          )}
          <button
            onClick={() => {
              setActive(null);
              setResult(null);
            }}
            className="btn-ghost w-full mt-6"
          >
            <Icon name="arrowLeft" size={16} /> Back to tests
          </button>
        </div>
      )}
    </Shell>
  );
}
