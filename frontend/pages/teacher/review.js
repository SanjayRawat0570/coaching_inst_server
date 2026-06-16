import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";

const SUBJECTS = ["Physics", "Chemistry", "Mathematics", "Biology"];

export default function ReviewPage() {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // {id, questions}
  const [busy, setBusy] = useState(false);

  // ── Generate-test form ──────────────────────────────────────────────────────
  const [gen, setGen] = useState({ student_id: "", subject: "", num_questions: 10 });
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState("");

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

  async function generate(e) {
    e.preventDefault();
    if (!gen.student_id.trim()) {
      setGenMsg("Enter a student ID first.");
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
          student_id: gen.student_id.trim(),
          institute_id,
          subject: gen.subject || null,
          num_questions: Number(gen.num_questions) || 10,
        },
      });
      const n = (res.questions || []).length;
      setGenMsg(`✅ Generated ${n} question${n === 1 ? "" : "s"} — review and approve below.`);
      setGen((g) => ({ ...g, student_id: "" }));
      await load();
    } catch (err) {
      setGenMsg(`⚠️ ${err.message}`);
    } finally {
      setGenerating(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function decide(test, approved) {
    setBusy(true);
    try {
      await api("/test/approve", {
        method: "POST",
        body: {
          test_id: test.id,
          approved,
          edited_questions: editing?.id === test.id ? editing.questions : null,
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
    <Shell requireRole="teacher" title="Review & Approve Tests">
      {/* Generate a personalized test for a student */}
      <form
        onSubmit={generate}
        className="card p-5 mb-6 flex flex-wrap items-end gap-3"
      >
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs muted mb-1">Student ID</label>
          <input
            className="input text-sm"
            placeholder="students.id (UUID)"
            value={gen.student_id}
            onChange={(e) => setGen({ ...gen, student_id: e.target.value })}
          />
        </div>
        <div>
          <label className="block text-xs muted mb-1">Subject</label>
          <select
            className="input text-sm"
            value={gen.subject}
            onChange={(e) => setGen({ ...gen, subject: e.target.value })}
          >
            <option value="">Mixed</option>
            {SUBJECTS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
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
        {genMsg && <p className="w-full text-sm muted">{genMsg}</p>}
      </form>

      {loading ? (
        <p className="muted">Loading…</p>
      ) : pending.length === 0 ? (
        <p className="muted">No tests awaiting approval. 🎉</p>
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
                  <div className="flex gap-2">
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
                  {questions.map((q, qi) => (
                    <div key={qi} className="rounded-xl border border-white/10 bg-ink-900/50 p-3">
                      <div className="flex justify-between text-xs muted mb-1">
                        <span>Q{qi + 1} · {q.concept}</span>
                        <span>{q.difficulty}</span>
                      </div>
                      <textarea
                        className="input text-sm"
                        value={q.question}
                        onChange={(e) =>
                          editQuestion(test.id, questions, qi, "question", e.target.value)
                        }
                      />
                      <div className="grid md:grid-cols-2 gap-2 mt-2">
                        {(q.options || []).map((opt, oi) => (
                          <div
                            key={oi}
                            className={
                              "text-sm px-2 py-1 rounded-lg border " +
                              (oi === q.answer_index
                                ? "bg-emerald-500/15 border-emerald-500/40 text-emerald-200"
                                : "bg-ink-900/60 border-white/10")
                            }
                          >
                            {String.fromCharCode(65 + oi)}. {opt}
                            {oi === q.answer_index && " ✓"}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Shell>
  );
}
