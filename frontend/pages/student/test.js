import { useEffect, useMemo, useState } from "react";
import Shell from "../../components/Shell";
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

  return (
    <Shell requireRole="student" title="Tests">
      {/* Test picker */}
      {!active && (
        <div className="space-y-3">
          {tests.length === 0 && (
            <p className="muted">
              No tests ready yet. Your teacher will assign one.
            </p>
          )}
          {tests.map((t) => (
            <div
              key={t.id}
              className="card card-hover p-4 flex items-center justify-between"
            >
              <div>
                <p className="font-medium">{t.subject || "Mixed"} test</p>
                <p className="text-sm muted">
                  {(t.questions || []).length} questions · negative marking on
                </p>
              </div>
              <button
                onClick={() => begin(t)}
                className="btn-primary"
              >
                Start
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Active test */}
      {active && !result && (
        <div>
          <div className="flex items-center justify-between mb-4 sticky top-16 z-10 bg-ink-900/80 backdrop-blur border border-white/10 rounded-xl px-4 py-2">
            <span className="text-sm muted">
              {Object.keys(answers).length}/{active.questions.length} answered
            </span>
            <span
              className={
                "font-mono text-lg " + (timeLeft < 60 ? "text-neon-rose" : "text-slate-200")
              }
            >
              ⏱ {mmss}
            </span>
          </div>

          <div className="space-y-5">
            {active.questions.map((q, i) => (
              <div key={i} className="card p-4">
                <div className="flex justify-between text-xs muted mb-1">
                  <span>Q{i + 1} · {q.concept}</span>
                  <span>+{q.marks ?? 4} / −{q.negative ?? 1}</span>
                </div>
                <p className="font-medium mb-3">{q.question}</p>
                <div className="grid gap-2">
                  {(q.options || []).map((opt, oi) => (
                    <label
                      key={oi}
                      className={
                        "border rounded-lg px-3 py-2 cursor-pointer transition " +
                        (answers[i] === oi
                          ? "border-brand bg-brand/15 text-white"
                          : "border-white/10 hover:bg-white/5")
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
              </div>
            ))}
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
        <div className="card p-6 max-w-md shadow-glow">
          <h2 className="text-xl font-semibold mb-2">Result</h2>
          <p className="text-4xl font-extrabold grad-text">
            {result.score} <span className="text-base muted">/ {result.evaluation?.total_marks}</span>
          </p>
          {result.air_rank && (
            <p className="mt-3 text-sm">
              📊 Predicted rank: <span className="font-medium text-neon-cyan">{result.air_rank}</span>
            </p>
          )}
          <button
            onClick={() => {
              setActive(null);
              setResult(null);
            }}
            className="mt-4 text-neon-violet hover:underline"
          >
            Back to tests
          </button>
        </div>
      )}
    </Shell>
  );
}
