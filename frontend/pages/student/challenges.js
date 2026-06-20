import { useEffect, useState } from "react";
import Shell from "../../components/Shell";
import { EmptyState, SkeletonCard } from "../../components/ui";
import Icon from "../../components/Icon";
import { api } from "../../lib/api";

export default function ChallengesPage() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ opponent_email: "", subject: "", num_questions: 5 });
  const [creating, setCreating] = useState(false);
  const [msg, setMsg] = useState("");

  // active attempt: { id, subject, questions, answers, result }
  const [active, setActive] = useState(null);
  const [answers, setAnswers] = useState({});
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await api("/challenges");
      setList(res.challenges || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  async function create(e) {
    e.preventDefault();
    setCreating(true);
    setMsg("");
    try {
      const res = await api("/challenge/create", {
        method: "POST",
        body: {
          opponent_email: form.opponent_email.trim(),
          subject: form.subject.trim() || null,
          num_questions: Number(form.num_questions) || 5,
        },
      });
      setMsg(`Challenge sent! ${res.questions_count} questions — now take it yourself below.`);
      setForm((f) => ({ ...f, opponent_email: "", subject: "" }));
      load();
    } catch (e) {
      setMsg(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function begin(challengeId) {
    try {
      const res = await api(`/challenge/${challengeId}/take`);
      setActive(res);
      setAnswers({});
    } catch (e) {
      alert(e.message);
    }
  }

  async function submit() {
    if (!active || submitting) return;
    setSubmitting(true);
    const ordered = (active.questions || []).map((_, i) =>
      answers[i] === undefined ? null : answers[i]
    );
    try {
      const res = await api("/challenge/submit", {
        method: "POST",
        body: { challenge_id: active.id, answers: ordered },
      });
      setActive({ ...active, result: res });
      load();
    } catch (e) {
      alert(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  // ── Taking a challenge ──────────────────────────────────────────────────────
  if (active && !active.result) {
    return (
      <Shell requireRole="student" title="Challenge" subtitle={`${active.subject || "Mixed"} · ${active.questions.length} questions`}>
        <div className="space-y-5">
          {active.questions.map((q, i) => (
            <div key={i} className="card p-4">
              <p className="text-xs muted mb-1">Q{i + 1} · {q.concept}</p>
              <p className="font-medium mb-3">{q.question}</p>
              <div className="grid gap-2">
                {(q.options || []).map((opt, oi) => (
                  <label key={oi} className={
                    "border rounded-lg px-3 py-2 cursor-pointer transition " +
                    (answers[i] === oi
                      ? "border-brand bg-brand/15 text-brand dark:text-white font-medium"
                      : "border-slate-200 hover:bg-slate-100 dark:border-white/10 dark:hover:bg-white/5")
                  }>
                    <input type="radio" name={`q${i}`} className="mr-2"
                      checked={answers[i] === oi}
                      onChange={() => setAnswers({ ...answers, [i]: oi })} />
                    {opt}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-6">
          <button onClick={submit} disabled={submitting} className="btn-success px-6">
            {submitting ? "Submitting…" : "Submit challenge"}
          </button>
          <button onClick={() => setActive(null)} className="btn-ghost">Cancel</button>
        </div>
      </Shell>
    );
  }

  // ── Result of the attempt I just submitted ──────────────────────────────────
  if (active && active.result) {
    const r = active.result;
    return (
      <Shell requireRole="student" title="Challenge submitted">
        <div className="card p-8 max-w-md mx-auto text-center shadow-soft-lg">
          <span className="grid place-items-center h-16 w-16 mx-auto rounded-2xl bg-brand-grad text-white mb-4 shadow-glow"><Icon name="trophy" size={30} className="text-white" /></span>
          <p className="stat-label">Your score</p>
          <p className="text-5xl font-extrabold grad-text mt-1">{r.score}<span className="text-lg muted font-bold"> / {r.total}</span></p>
          <p className="muted text-sm mt-4">
            {r.status === "complete" ? "Both players are done — see the comparison below." : "Waiting for your opponent to play."}
          </p>
          <button onClick={() => setActive(null)} className="btn-ghost w-full mt-6">
            <Icon name="arrowLeft" size={16} /> Back to challenges
          </button>
        </div>
      </Shell>
    );
  }

  // ── List + create ───────────────────────────────────────────────────────────
  return (
    <Shell requireRole="student" title="Challenges" subtitle="Challenge a classmate to the same test and compare">
      <form onSubmit={create} className="card p-5 mb-6">
        <h2 className="h-section mb-3 flex items-center gap-2"><Icon name="trophy" size={16} /> New challenge</h2>
        <div className="grid sm:grid-cols-4 gap-3 items-end">
          <div className="sm:col-span-2">
            <label className="stat-label">Classmate email</label>
            <input className="input mt-1" placeholder="classmate@gmail.com" value={form.opponent_email}
              onChange={(e) => setForm({ ...form, opponent_email: e.target.value })} required />
          </div>
          <div>
            <label className="stat-label">Subject</label>
            <input className="input mt-1" placeholder="e.g. Physics" value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })} />
          </div>
          <button className="btn-primary py-2" disabled={creating}>
            {creating ? "Creating…" : "Challenge"}
          </button>
        </div>
        {msg && <p className="text-sm mt-3 text-brand dark:text-violet-400">{msg}</p>}
      </form>

      {loading ? (
        <div className="space-y-3"><SkeletonCard lines={2} /><SkeletonCard lines={2} /></div>
      ) : list.length === 0 ? (
        <div className="card">
          <EmptyState icon={<Icon name="trophy" size={26} />} title="No challenges yet"
            hint="Challenge a classmate above — you'll both take the same test, then compare scores." />
        </div>
      ) : (
        <div className="space-y-3">
          {list.map((c) => <ChallengeRow key={c.id} c={c} onTake={begin} />)}
        </div>
      )}
    </Shell>
  );
}

function ScorePill({ label, score, total, win }) {
  return (
    <div className={"panel px-4 py-3 text-center flex-1 " + (win ? "ring-1 ring-emerald-500/50" : "")}>
      <p className="text-xs muted truncate">{label}</p>
      <p className="text-2xl font-bold tabular-nums mt-0.5">
        {score == null ? "—" : score}<span className="text-sm muted">/{total ?? "—"}</span>
      </p>
    </div>
  );
}

function ChallengeRow({ c, onTake }) {
  const bothDone = c.my_score != null && c.opp_score != null;
  const iWin = bothDone && c.my_score > c.opp_score;
  const oppWin = bothDone && c.opp_score > c.my_score;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="min-w-0">
          <p className="font-semibold truncate">{c.subject || "Mixed"} · {c.questions_count} questions</p>
          <p className="muted text-xs">vs {c.opp_name || "classmate"}</p>
        </div>
        {c.my_turn ? (
          <button onClick={() => onTake(c.id)} className="btn-primary shrink-0">
            Take it <Icon name="arrowRight" size={16} />
          </button>
        ) : (
          <span className={"badge " + (bothDone ? "badge-green" : "badge-amber")}>
            {bothDone ? "Complete" : "Waiting for opponent"}
          </span>
        )}
      </div>

      {(c.my_score != null || c.opp_score != null) && (
        <div className="flex items-center gap-3">
          <ScorePill label="You" score={c.my_score} total={c.my_total} win={iWin} />
          <span className="font-bold muted">vs</span>
          <ScorePill label={c.opp_name || "Opponent"} score={c.opp_score} total={c.opp_total} win={oppWin} />
        </div>
      )}
      {bothDone && (
        <p className="text-center text-sm font-semibold mt-3">
          {iWin ? "🏆 You won!" : oppWin ? "Tough luck — they edged you out." : "🤝 It's a tie!"}
        </p>
      )}
    </div>
  );
}
