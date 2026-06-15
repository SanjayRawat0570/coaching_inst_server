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
            <p className="text-slate-400">
              No tests ready yet. Your teacher will assign one.
            </p>
          )}
          {tests.map((t) => (
            <div
              key={t.id}
              className="bg-white border rounded-xl p-4 flex items-center justify-between"
            >
              <div>
                <p className="font-medium">{t.subject || "Mixed"} test</p>
                <p className="text-sm text-slate-500">
                  {(t.questions || []).length} questions · negative marking on
                </p>
              </div>
              <button
                onClick={() => begin(t)}
                className="bg-brand hover:bg-brand-dark text-white px-4 py-2 rounded-lg"
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
          <div className="flex items-center justify-between mb-4 sticky top-14 bg-slate-50 py-2">
            <span className="text-sm text-slate-500">
              {Object.keys(answers).length}/{active.questions.length} answered
            </span>
            <span
              className={
                "font-mono text-lg " + (timeLeft < 60 ? "text-red-600" : "text-slate-700")
              }
            >
              ⏱ {mmss}
            </span>
          </div>

          <div className="space-y-5">
            {active.questions.map((q, i) => (
              <div key={i} className="bg-white border rounded-xl p-4">
                <div className="flex justify-between text-xs text-slate-400 mb-1">
                  <span>Q{i + 1} · {q.concept}</span>
                  <span>+{q.marks ?? 4} / −{q.negative ?? 1}</span>
                </div>
                <p className="font-medium mb-3">{q.question}</p>
                <div className="grid gap-2">
                  {(q.options || []).map((opt, oi) => (
                    <label
                      key={oi}
                      className={
                        "border rounded-lg px-3 py-2 cursor-pointer " +
                        (answers[i] === oi ? "border-brand bg-indigo-50" : "border-slate-200")
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
            className="mt-6 bg-green-600 hover:bg-green-700 text-white px-6 py-2 rounded-lg disabled:opacity-60"
          >
            {submitting ? "Submitting…" : "Submit test"}
          </button>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-white border rounded-xl p-6 max-w-md">
          <h2 className="text-xl font-semibold mb-2">Result</h2>
          <p className="text-3xl font-bold text-brand">
            {result.score} <span className="text-base text-slate-400">/ {result.evaluation?.total_marks}</span>
          </p>
          {result.air_rank && (
            <p className="mt-3 text-sm">
              📊 Predicted rank: <span className="font-medium">{result.air_rank}</span>
            </p>
          )}
          <button
            onClick={() => {
              setActive(null);
              setResult(null);
            }}
            className="mt-4 text-brand hover:underline"
          >
            Back to tests
          </button>
        </div>
      )}
    </Shell>
  );
}
