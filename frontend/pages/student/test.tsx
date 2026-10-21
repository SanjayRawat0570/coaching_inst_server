import { useCallback, useEffect, useRef, useState } from "react";
import useSWR from "swr";
import Shell from "../../components/Shell";
import { EmptyState, ErrorState, SkeletonCard } from "../../components/ui";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { supabase } from "../../lib/supabase";
import { errorDetail, pollJob, runJob } from "../../lib/api";
import { useAuth } from "../../lib/useAuth";
import { swrConfig } from "../../lib/swrConfig";

const DURATION_SEC = 20 * 60; // 20 minutes
const SAVE_EVERY_MS = 3000;

// What's kept on this device while a test is in progress, so a refresh or a
// dropped connection never loses work: answers, when it started, and the grading
// job once submitted (so a retry waits for that job instead of submitting twice).
type Saved = { answers: Record<number, any>; startedAt: number; jobId?: string };
const storeKey = (testId: string) => `test-progress:${testId}`;

function readSaved(testId: string): Saved | null {
  try {
    return JSON.parse(localStorage.getItem(storeKey(testId)) || "null");
  } catch {
    return null;
  }
}

function writeSaved(testId: string, saved: Saved) {
  try {
    localStorage.setItem(storeKey(testId), JSON.stringify(saved));
  } catch {
    // storage full / blocked: the test still works, just without autosave
  }
}

function clearSaved(testId: string) {
  try {
    localStorage.removeItem(storeKey(testId));
  } catch {
    // ignore
  }
}

async function readyTests() {
  // RLS limits this to the student's own rows.
  const { data, error } = await supabase
    .from("tests")
    .select("id, subject, questions, status, created_at")
    .eq("status", "ready")
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return data || [];
}

const fmt = (sec: number) =>
  `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;

export default function TestPage() {
  const toast = useToast();
  const { ready, user } = useAuth();
  const testsQ = useSWR(ready && user ? "tests:ready" : null, readyTests, swrConfig);
  const tests = testsQ.data || [];

  const [active, setActive] = useState(null); // {id, questions}
  const [answers, setAnswers] = useState<Record<number, any>>({});
  const [startedAt, setStartedAt] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [grading, setGrading] = useState("");
  const [savedAt, setSavedAt] = useState(0);
  const autoSubmitted = useRef(false);
  const finished = useRef(new Set<string>()); // graded tests: never autosave them again
  const latest = useRef({ answers, startedAt });
  latest.current = { answers, startedAt };

  // The timer is worked out from the start time, so it stays right even when the
  // tab sleeps or the page is reloaded (counting ticks would drift).
  const timeLeft = active ? Math.max(0, DURATION_SEC - Math.floor((now - startedAt) / 1000)) : DURATION_SEC;
  const dirty = !!active && !result;

  useEffect(() => {
    if (!dirty) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [dirty]);

  // Autosave every few seconds (and on every page hide).
  useEffect(() => {
    if (!dirty) return;
    const save = () => {
      if (finished.current.has(active.id)) return;
      const prev = readSaved(active.id);
      writeSaved(active.id, { ...latest.current, jobId: prev?.jobId });
      setSavedAt(Date.now());
    };
    const t = setInterval(save, SAVE_EVERY_MS);
    window.addEventListener("pagehide", save);
    return () => {
      clearInterval(t);
      window.removeEventListener("pagehide", save);
      save();
    };
  }, [dirty, active]);

  // Warn before leaving mid-test (answers are saved, but the timer keeps running).
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function begin(test) {
    const saved = readSaved(test.id);
    setActive(test);
    setAnswers(saved?.answers || {});
    setStartedAt(saved?.startedAt || Date.now());
    setNow(Date.now());
    setResult(null);
    setSubmitError("");
    autoSubmitted.current = false;
    if (saved) toast("Picked up where you left off — your answers were saved on this device.", "info");
    if (!saved) writeSaved(test.id, { answers: {}, startedAt: Date.now() });
    if (saved?.jobId) resumeGrading(test, saved.jobId);
  }

  const finish = useCallback((test, res) => {
    finished.current.add(test.id);
    clearSaved(test.id);
    setResult(res);
    setGrading("");
    testsQ.mutate((list: any[]) => (list || []).filter((t) => t.id !== test.id), { revalidate: false });
  }, [testsQ]);

  const gradingLabel = (st: string) => (st === "running" ? "Grading your answers…" : "Queued for grading…");

  async function resumeGrading(test, jobId) {
    setSubmitting(true);
    setGrading("Grading your answers…");
    try {
      finish(test, await pollJob(jobId, { onStatus: (st) => setGrading(gradingLabel(st)) }));
    } catch (e) {
      setSubmitError(errorDetail(e) || "Grading didn't finish. Your answers are saved — try again.");
      const saved = readSaved(test.id);
      if (saved) writeSaved(test.id, { ...saved, jobId: undefined });
    } finally {
      setSubmitting(false);
    }
  }

  async function submit() {
    if (!active || submitting) return;
    setSubmitting(true);
    setSubmitError("");
    setGrading("Sending your answers…");
    const test = active;
    const ordered = (test.questions || []).map((_, i) => (answers[i] === undefined ? null : answers[i]));
    writeSaved(test.id, { answers, startedAt });
    // A dropped connection gets two quick retries before the student sees an error.
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const res = await runJob("/test/submit", {
          body: { test_id: test.id, answers: ordered },
          onStart: (jobId) => writeSaved(test.id, { answers, startedAt, jobId }),
          onStatus: (st) => setGrading(gradingLabel(st)),
        });
        finish(test, res);
        setSubmitting(false);
        return;
      } catch (e) {
        const saved = readSaved(test.id);
        if (saved?.jobId) { // submitted; only waiting failed — wait on that job
          setSubmitting(false);
          return resumeGrading(test, saved.jobId);
        }
        const detail = errorDetail(e);
        const retryable = !detail || /fetch|network|failed/i.test(detail);
        if (!retryable || attempt === 2) {
          setSubmitError(detail || "Couldn't submit. Your answers are saved — try again.");
          break;
        }
        await new Promise((r) => setTimeout(r, 1500 * (attempt + 1)));
      }
    }
    setGrading("");
    setSubmitting(false);
  }

  // Time's up: submit once.
  useEffect(() => {
    if (dirty && timeLeft === 0 && !autoSubmitted.current && !submitting) {
      autoSubmitted.current = true;
      submit();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, timeLeft]);

  const answered = active
    ? Object.values(answers).filter(
        (v) => typeof v === "number" || (typeof v === "string" && v.trim() !== ""),
      ).length
    : 0;
  const totalQ = active ? active.questions.length : 0;
  const progressPct = totalQ ? Math.round((answered / totalQ) * 100) : 0;

  return (
    <Shell requireRole="student" title="Tests" subtitle="Personalised practice assigned by your teacher">
      {/* Test picker */}
      {!active && (
        <div className="space-y-3">
          {testsQ.error && !testsQ.data ? (
            <ErrorState message="Couldn't load your tests." onRetry={() => testsQ.mutate()} />
          ) : !testsQ.data ? (
            <>
              <SkeletonCard lines={1} />
              <SkeletonCard lines={1} />
            </>
          ) : tests.length === 0 ? (
            <div className="card">
              <EmptyState
                icon={<Icon name="tests" size={26} />}
                title="No tests ready yet"
                hint="Your teacher will assign a personalised test soon. Check back later."
              />
            </div>
          ) : (
            tests.map((t) => {
              const inProgress = typeof window !== "undefined" && !!readSaved(t.id);
              return (
                <div key={t.id} className="card card-hover p-4 flex items-center justify-between gap-3">
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
                    {inProgress ? "Continue" : "Start"} <Icon name="arrowRight" size={16} />
                  </button>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Active test */}
      {active && !result && (
        <div>
          <div className="sticky top-16 z-10 panel backdrop-blur px-4 py-3 mb-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm muted">
                <span className="font-semibold text-slate-700 dark:text-slate-200">{answered}</span>/{totalQ} answered
                {savedAt > 0 && <span className="hidden sm:inline"> · saved on this device</span>}
              </span>
              <span
                role="timer"
                aria-label={`Time left ${fmt(timeLeft)}`}
                className={
                  "inline-flex items-center gap-1.5 font-mono text-lg tabular-nums " +
                  (timeLeft < 60 ? "text-rose-500 dark:text-neon-rose animate-pulse" : "text-slate-700 dark:text-slate-200")
                }
              >
                <Icon name="clock" size={16} /> {fmt(timeLeft)}
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-slate-200 dark:bg-white/10 overflow-hidden">
              <div className="h-full rounded-full bg-brand-grad transition-all duration-300" style={{ width: `${progressPct}%` }} />
            </div>
          </div>

          <div className="space-y-5">
            {active.questions.map((q, i) => {
              const isTheory = q.type === "theory" || (!q.options && q.model_answer !== undefined);
              return (
                <fieldset key={i} className="card p-4" disabled={submitting}>
                  <legend className="sr-only">Question {i + 1}</legend>
                  <div className="flex justify-between text-xs muted mb-1">
                    <span>Q{i + 1} · {q.concept}</span>
                    <span>{isTheory ? `+${q.marks ?? 5}` : `+${q.marks ?? 4} / −${q.negative ?? 1}`}</span>
                  </div>
                  <p className="font-medium mb-3">{q.question}</p>
                  {isTheory ? (
                    <textarea
                      aria-label={`Answer to question ${i + 1}`}
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
                            "border rounded-lg px-3 py-2 min-h-[44px] flex items-center cursor-pointer transition " +
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
                </fieldset>
              );
            })}
          </div>

          {submitError && (
            <div role="alert" className="panel mt-6 p-3 text-sm text-rose-600 dark:text-rose-300">
              {submitError}
            </div>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button onClick={submit} disabled={submitting} className="btn-success px-6">
              {submitting ? "Submitting…" : submitError ? "Try again" : "Submit test"}
            </button>
            {grading && <span className="muted text-sm" aria-live="polite">{grading}</span>}
          </div>
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
