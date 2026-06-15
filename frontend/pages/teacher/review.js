import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";

export default function ReviewPage() {
  const [pending, setPending] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // {id, questions}
  const [busy, setBusy] = useState(false);

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
      {loading ? (
        <p className="text-slate-400">Loading…</p>
      ) : pending.length === 0 ? (
        <p className="text-slate-400">No tests awaiting approval. 🎉</p>
      ) : (
        <div className="space-y-6">
          {pending.map((test) => {
            const questions =
              editing?.id === test.id ? editing.questions : test.questions || [];
            return (
              <div key={test.id} className="bg-white border rounded-xl p-5">
                <div className="flex justify-between items-center mb-3">
                  <h2 className="font-semibold">
                    {test.subject || "Mixed"} · {questions.length} questions
                  </h2>
                  <div className="flex gap-2">
                    <button
                      disabled={busy}
                      onClick={() => decide(test, false)}
                      className="px-4 py-2 rounded-lg border text-red-600"
                    >
                      Reject
                    </button>
                    <button
                      disabled={busy}
                      onClick={() => decide(test, true)}
                      className="px-4 py-2 rounded-lg bg-green-600 text-white"
                    >
                      Approve & send
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  {questions.map((q, qi) => (
                    <div key={qi} className="border rounded-lg p-3">
                      <div className="flex justify-between text-xs text-slate-400 mb-1">
                        <span>Q{qi + 1} · {q.concept}</span>
                        <span>{q.difficulty}</span>
                      </div>
                      <textarea
                        className="w-full border rounded px-2 py-1 text-sm"
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
                              "text-sm px-2 py-1 rounded " +
                              (oi === q.answer_index
                                ? "bg-green-50 border border-green-300"
                                : "bg-slate-50")
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
