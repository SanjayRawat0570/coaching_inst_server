import { useEffect, useState } from "react";
import { useRouter } from "next/router";
import Shell from "../../components/Shell";
import { EmptyState, SkeletonCard } from "../../components/ui";
import Icon from "../../components/Icon";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";


export default function ReviewPage() {
  const router = useRouter();
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // {id, questions}
  const [busy, setBusy] = useState(false);
  const [dueDates, setDueDates] = useState({}); // F7: test.id -> due date

  // ── Generate-test form ──────────────────────────────────────────────────────
  const [gen, setGen] = useState({ student_email: "", subject: "", num_questions: 10, question_type: "mcq" });
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState("");
  const [classBusy, setClassBusy] = useState(false);

  async function load() {
    setLoading(true);
    const {
      data: { user },
    } = await supabase.auth.getUser();
    const institute_id = user?.user_metadata?.institute_id || "";
    try {
      const data = await api(`/teacher/tests/pending?institute_id=${institute_id}`);
      setPending(data.tests || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function generateClass() {
    setClassBusy(true);
    setGenMsg("Generating one personalized test per student — this can take a moment…");
    const {
      data: { user },
    } = await supabase.auth.getUser();
    const institute_id = user?.user_metadata?.institute_id || "";
    try {
      const res = await api("/teacher/tests/generate-class", {
        method: "POST",
        body: {
          institute_id,
          subject: gen.subject || null,
          num_questions: Number(gen.num_questions) || 10,
        },
      });
      setGenMsg(`Generated ${res.generated}/${res.students} student tests — review and approve below.`);
      await load();
    } catch (err) {
      setGenMsg(`Error: ${err.message}`);
    } finally {
      setClassBusy(false);
    }
  }

  async function generate(e) {
    e.preventDefault();
    const email = gen.student_email.trim();
    if (!email) {
      setGenMsg("Enter the student's email first.");
      return;
    }
    setGenerating(true);
    setGenMsg("Generating — the AI is drafting and self-reviewing questions…");
    const {
      data: { user },
    } = await supabase.auth.getUser();
    const institute_id = user?.user_metadata?.institute_id || "";
    try {
      const res = await api("/test/generate", {
        method: "POST",
        body: {
          student_id: email, // backend resolves the email to the student
          institute_id,
          subject: gen.subject || null,
          num_questions: Number(gen.num_questions) || 10,
          question_type: gen.question_type,
        },
      });
      const n = (res.questions || []).length;
      const diff = res.difficulty_level
        ? ` · difficulty ${res.difficulty_level}/5 (auto-set from last score)`
        : "";
      setGenMsg(`Generated ${n} question${n === 1 ? "" : "s"}${diff} — review and approve below.`);
      setGen((g) => ({ ...g, student_email: "" }));
      await load();
    } catch (err) {
      setGenMsg(`Error: ${err.message}`);
    } finally {
      setGenerating(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  // Prefill the student's email when arriving from the dashboard roster
  // (/teacher/review?student=email).
  useEffect(() => {
    if (!router.isReady) return;
    const s = router.query.student;
    if (typeof s === "string" && s) {
      setGen((g) => ({ ...g, student_email: s }));
    }
  }, [router.isReady, router.query.student]);

  async function decide(test, approved) {
    setBusy(true);
    try {
      await api("/test/approve", {
        method: "POST",
        body: {
          test_id: test.id,
          approved,
          edited_questions: editing?.id === test.id ? editing.questions : null,
          due_date: approved ? (dueDates[test.id] || null) : null,
        },
      });
      setPending((p) => p.filter((t) => t.id !== test.id));
      setEditing(null);
    } catch (e) {
      alert(e.message);
    } finally {
      setBusy(false);
    }
  }

  function editQuestion(testId, questions, qi, field, value) {
    const copy = questions.map((q) => ({ ...q }));
    copy[qi][field] = value;
    setEditing({ id: testId, questions: copy });
  }

  return (
    <Shell
      requireRole="teacher"
      title="Review & Approve Tests"
      subtitle="Generate AI tests, edit questions, and approve before they reach students"
    >
      {/* Generate a personalized test for a student */}
      <form
        onSubmit={generate}
        className="card p-5 mb-6 flex flex-wrap items-end gap-3"
      >
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs muted mb-1">Student email</label>
          <input
            type="email"
            className="input text-sm"
            placeholder="student@gmail.com"
            value={gen.student_email}
            onChange={(e) => setGen({ ...gen, student_email: e.target.value })}
          />
        </div>
        <div className="min-w-[200px]">
          <label className="block text-xs muted mb-1">Subject</label>
          <input
            type="text"
            autoComplete="off"
            className="input text-sm"
            placeholder="Type any subject (blank = mixed)"
            value={gen.subject}
            onChange={(e) => setGen({ ...gen, subject: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs muted mb-1">Type</label>
          <select
            className="input text-sm"
            value={gen.question_type}
            onChange={(e) => setGen({ ...gen, question_type: e.target.value })}
          >
            <option value="mcq">MCQ</option>
            <option value="theory">Theoretical</option>
          </select>
        </div>
        <div>
          <label className="block text-xs muted mb-1">Questions</label>
          <input
            type="number"
            min={1}
            max={30}
            className="input w-20 text-sm"
            value={gen.num_questions}
            onChange={(e) => setGen({ ...gen, num_questions: e.target.value })}
          />
        </div>
        <button
          type="submit"
          disabled={generating}
          className="btn-primary px-5"
        >
          {generating ? "Generating…" : "Generate test"}
        </button>
        {/* F13 — generate one personalized test per student in the class */}
        <button
          type="button"
          onClick={generateClass}
          disabled={classBusy}
          className="btn-ghost px-4"
          title="Generate a weakness-targeted test for every student (subject + count above)"
        >
          {classBusy ? "Generating class…" : "Generate for whole class"}
        </button>
        {genMsg && <p className="w-full text-sm muted">{genMsg}</p>}
      </form>

      {loading ? (
        <div className="space-y-6">
          <SkeletonCard lines={4} />
          <SkeletonCard lines={4} />
        </div>
      ) : pending.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={<Icon name="celebrate" size={26} />}
            title="Nothing awaiting approval"
            hint="Generate a personalised test above and it'll appear here for review."
          />
        </div>
      ) : (
        <div className="space-y-6">
          {pending.map((test) => {
            const questions =
              editing?.id === test.id ? editing.questions : test.questions || [];
            return (
              <div key={test.id} className="card p-5">
                <div className="flex justify-between items-center mb-3">
                  <h2 className="font-semibold">
                    {test.subject || "Mixed"} · {questions.length} questions
                  </h2>
                  <div className="flex items-center gap-2">
                    <label className="text-xs muted flex items-center gap-1.5">
                      Due
                      <input
                        type="date"
                        value={dueDates[test.id] || ""}
                        onChange={(e) => setDueDates((d) => ({ ...d, [test.id]: e.target.value }))}
                        className="input py-1 px-2 text-sm"
                        title="When the student must take it by (defaults to 3 days)"
                      />
                    </label>
                    <button
                      disabled={busy}
                      onClick={() => decide(test, false)}
                      className="btn-danger"
                    >
                      Reject
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => decide(test, true)}
                      className="btn-success"
                    >
                      Approve & send
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {questions.map((q, qi) => {
                    const isTheory = q.type === "theory" || (!q.options && q.model_answer !== undefined);
                    return (
                    <div key={qi} className="panel p-3">
                      <div className="flex justify-between items-center text-xs muted mb-1">
                        <span>Q{qi + 1} · {q.concept}</span>
                        <span className="flex items-center gap-2">
                          <span className={isTheory ? "badge-brand" : "badge-cyan"}>
                            {isTheory ? "Theory" : "MCQ"}
                          </span>
                          {q.difficulty}
                        </span>
                      </div>
                      <textarea
                        className="input text-sm"
                        value={q.question}
                        onChange={(e) =>
                          editQuestion(test.id, questions, qi, "question", e.target.value)
                        }
                      />
                      <div className="flex items-end gap-3 mt-2">
                        <div>
                          <label className="block text-xs muted mb-1">Marks</label>
                          <input
                            type="number"
                            min={1}
                            step={1}
                            className="input w-20 text-sm"
                            value={q.marks ?? (isTheory ? 5 : 4)}
                            onChange={(e) =>
                              editQuestion(test.id, questions, qi, "marks",
                                e.target.value === "" ? "" : Number(e.target.value))
                            }
                          />
                        </div>
                        {!isTheory && (
                          <div>
                            <label className="block text-xs muted mb-1">Negative</label>
                            <input
                              type="number"
                              min={0}
                              step={1}
                              className="input w-20 text-sm"
                              value={q.negative ?? 1}
                              onChange={(e) =>
                                editQuestion(test.id, questions, qi, "negative",
                                  e.target.value === "" ? "" : Number(e.target.value))
                              }
                            />
                          </div>
                        )}
                      </div>
                      {isTheory ? (
                        <div className="mt-2">
                          <label className="block text-xs muted mb-1">Model answer / marking scheme</label>
                          <textarea
                            className="input text-sm"
                            rows={3}
                            value={q.model_answer || ""}
                            onChange={(e) =>
                              editQuestion(test.id, questions, qi, "model_answer", e.target.value)
                            }
                          />
                        </div>
                      ) : (
                        <div className="grid md:grid-cols-2 gap-2 mt-2">
                          {(q.options || []).map((opt, oi) => (
                            <div
                              key={oi}
                              className={
                                "text-sm px-2 py-1 rounded-lg border " +
                                (oi === q.answer_index
                                  ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-700 dark:text-emerald-200"
                                  : "bg-slate-50 border-slate-200 dark:bg-ink-900/60 dark:border-white/10")
                              }
                            >
                              {String.fromCharCode(65 + oi)}. {opt}
                              {oi === q.answer_index && <span className="ml-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">correct</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Shell>
  );
}
