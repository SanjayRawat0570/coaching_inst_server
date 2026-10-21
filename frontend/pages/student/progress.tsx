import { useState } from "react";
import dynamic from "next/dynamic";
import Shell from "../../components/Shell";
import { EmptyState, Stat, SkeletonCard, ResultsTable, ErrorState, Skeleton } from "../../components/ui";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { api, errorDetail } from "../../lib/api";
import { useApi } from "../../lib/hooks";

// Recharts loads only when a chart is drawn, after the page itself is on screen.
const MasteryChart = dynamic(() => import("../../components/charts/MasteryChart"), {
  ssr: false,
  loading: () => <Skeleton className="h-56 w-full" />,
});

const EMPTY = { weakness_map: [], profile: {}, recent_tests: [] };

export default function ProgressPage() {
  const toast = useToast();
  // Each section is its own cached request: coming back here is instant, and one
  // slow or failing section never blanks the others.
  const progressQ = useApi("/progress");
  const dueQ = useApi("/flashcards/due");
  const planQ = useApi("/student/plan");
  const cmapQ = useApi("/student/concept-map");
  const boardQ = useApi("/leaderboard");
  const badgesQ = useApi("/badges");

  const data: any = progressQ.data || EMPTY;
  const cards = dueQ.data?.cards || [];
  const plan = planQ.data?.plan || null;
  const cmap = cmapQ.data || { nodes: [], built: false };
  const board = boardQ.data?.leaderboard || [];
  const badges = badgesQ.data?.badges || [];
  const loading = !progressQ.data && !progressQ.error;

  const [revealed, setRevealed] = useState({});
  const [examEdit, setExamEdit] = useState(false);
  const [examInput, setExamInput] = useState("");
  const [savingExam, setSavingExam] = useState(false);
  const [planBusy, setPlanBusy] = useState(false);
  const [cmapBusy, setCmapBusy] = useState(false);

  async function generatePlan() {
    setPlanBusy(true);
    try {
      const res = await api("/student/plan/generate", { method: "POST" });
      planQ.mutate({ plan: res.plan || null }, { revalidate: false });
      toast("Your new study plan is ready.");
    } catch (e) {
      toast(errorDetail(e) || "Couldn't generate a plan. Please try again.", "error");
    } finally {
      setPlanBusy(false);
    }
  }

  async function buildConceptMap() {
    setCmapBusy(true);
    try {
      const res = await api("/student/concept-map/build", { method: "POST" });
      cmapQ.mutate(res || { nodes: [], built: false }, { revalidate: false });
    } catch (e) {
      toast(errorDetail(e) || "Couldn't build the map. Please try again.", "error");
    } finally {
      setCmapBusy(false);
    }
  }

  // Optimistic: the card leaves the list at once; it comes back if the save fails.
  async function review(cardId, quality) {
    const before = dueQ.data;
    dueQ.mutate({ ...before, cards: cards.filter((x) => x.id !== cardId) }, { revalidate: false });
    try {
      await api("/flashcards/review", { method: "POST", body: { card_id: cardId, quality } });
    } catch (e) {
      dueQ.mutate(before, { revalidate: false });
      toast("Couldn't save that review — the card is back. Please try again.", "error");
    }
  }

  async function saveExam() {
    setSavingExam(true);
    const exam = examInput.trim();
    const before = progressQ.data;
    progressQ.mutate({ ...data, profile: { ...data.profile, target_exam: exam || null } }, { revalidate: false });
    setExamEdit(false);
    try {
      await api("/profile", { method: "POST", body: { target_exam: exam } });
    } catch (e) {
      progressQ.mutate(before, { revalidate: false });
      toast("Couldn't save your target exam. Please try again.", "error");
    } finally {
      setSavingExam(false);
    }
  }

  const chart = (data.weakness_map || []).map((w) => ({
    name: w.concept,
    score: Math.round((w.score || 0) * 100),
    raw: w.score || 0,
  }));

  return (
    <Shell
      requireRole="student"
      title="My Progress"
      subtitle="Track your streak, mastery, and what to revise next"
    >
      {progressQ.error && !progressQ.data ? (
        <ErrorState message="Couldn't load your progress." onRetry={() => progressQ.mutate()} />
      ) : loading ? (
        <div className="grid md:grid-cols-3 gap-4">
          <SkeletonCard lines={1} />
          <SkeletonCard lines={1} />
          <SkeletonCard lines={1} />
          <div className="md:col-span-3">
            <SkeletonCard lines={5} />
          </div>
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {/* F5 — predicted AIR, the hero number */}
          <div className="card card-hover p-5 md:col-span-3 bg-gradient-to-br from-brand/5 to-transparent dark:from-violet-500/10">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="stat-label flex items-center gap-2">
                  <Icon name="progress" size={14} /> Predicted All-India Rank
                </p>
                {data.profile?.predicted_rank ? (
                  <>
                    <p className="text-4xl md:text-5xl font-bold tracking-tight text-brand dark:text-violet-400 mt-2 tabular-nums">
                      {data.profile.predicted_rank}
                    </p>
                    {data.profile?.predicted_rank_context && (
                      <p className="muted text-sm mt-2 max-w-2xl">{data.profile.predicted_rank_context}</p>
                    )}
                    <p className="muted text-xs mt-1">Updates with every test you attempt.</p>
                  </>
                ) : (
                  <p className="muted text-sm mt-3">
                    Take a test and your predicted rank will appear here.
                  </p>
                )}
              </div>
              <span className="icon-tile h-11 w-11 shrink-0"><Icon name="progress" /></span>
            </div>
          </div>

          {/* Stat cards */}
          <Stat icon={<Icon name="streak" />} label="Day streak" value={`${data.profile?.streak_days ?? 0}`} accent="text-amber-500 dark:text-neon-amber" sub="Keep it alive — study daily" />
          <Stat icon={<Icon name="xp" />} label="XP points" value={data.profile?.xp_points ?? 0} />
          {/* Target exam — editable */}
          <div className="card card-hover p-5">
            {examEdit ? (
              <div className="mt-2 flex flex-col gap-2">
                <input
                  className="input"
                  placeholder="e.g. JEE Advanced, NEET"
                  value={examInput}
                  onChange={(e) => setExamInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && saveExam()}
                  autoFocus
                />
                <div className="flex gap-2">
                  <button className="btn-primary flex-1 py-1 text-sm" onClick={saveExam} disabled={savingExam}>
                    {savingExam ? "Saving…" : "Save"}
                  </button>
                  <button className="btn-ghost flex-1 py-1 text-sm" onClick={() => setExamEdit(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="stat-label">Target exam</p>
                    <p className="stat-value mt-1.5 text-slate-900 dark:text-white truncate">
                      {data.profile?.target_exam || "—"}
                    </p>
                  </div>
                  <span className="icon-tile h-10 w-10 shrink-0"><Icon name="target" /></span>
                </div>
                <button
                  className="text-brand dark:text-violet-400 text-xs mt-2 font-medium hover:underline"
                  onClick={() => {
                    setExamInput(data.profile?.target_exam || "");
                    setExamEdit(true);
                  }}
                >
                  {data.profile?.target_exam ? "Change" : "Set target exam"}
                </button>
              </>
            )}
          </div>

          {/* Weakness chart */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3">Concept mastery (%)</h2>
            {chart.length === 0 ? (
              <EmptyState
                icon={<Icon name="mastery" size={26} />}
                title="No mastery data yet"
                hint="Take a test and your per-concept weakness map will appear here."
              />
            ) : (
              <MasteryChart data={chart} />
            )}
          </div>

          {/* F11 — badge shelf */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3 flex items-center gap-2">
              <Icon name="trophy" size={16} /> Your badges
              <span className="badge-brand">{badges.filter((b) => b.earned).length}/{badges.length}</span>
            </h2>
            {!badgesQ.data && <Skeleton className="h-24 w-full" />}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {badges.map((b) => (
                <div
                  key={b.key}
                  className={
                    "panel p-4 text-center transition " +
                    (b.earned ? "" : "opacity-45 grayscale")
                  }
                  title={b.desc}
                >
                  <span className={
                    "grid place-items-center h-12 w-12 mx-auto rounded-2xl mb-2 " +
                    (b.earned ? "bg-brand-grad text-white shadow-glow" : "bg-slate-200 dark:bg-white/10")
                  }>
                    <Icon name={b.icon} size={22} className={b.earned ? "text-white" : ""} />
                  </span>
                  <p className="text-sm font-semibold">{b.name}</p>
                  <p className="muted text-xs mt-0.5">{b.earned ? b.desc : `🔒 ${b.desc}`}</p>
                </div>
              ))}
            </div>
          </div>

          {/* F10 — animated top-10 leaderboard */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3 flex items-center gap-2">
              <Icon name="trophy" size={16} /> Class leaderboard · Top 10
            </h2>
            {!boardQ.data ? (
              <Skeleton className="h-24 w-full" />
            ) : board.length === 0 ? (
              <p className="muted text-sm">No XP earned in your class yet — be the first!</p>
            ) : (
              <div className="space-y-2">
                {board.map((row, i) => (
                  <div
                    key={i}
                    className={
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 animate-[fadeIn_.4s_ease] " +
                      (row.is_me
                        ? "bg-brand/10 ring-1 ring-brand/40"
                        : "bg-slate-50 dark:bg-white/[0.03]")
                    }
                    style={{ animationDelay: `${i * 50}ms`, animationFillMode: "backwards" }}
                  >
                    <span className={
                      "grid place-items-center h-8 w-8 rounded-lg font-bold text-sm shrink-0 " +
                      (row.rank === 1 ? "bg-amber-400 text-white"
                        : row.rank === 2 ? "bg-slate-400 text-white"
                        : row.rank === 3 ? "bg-orange-400 text-white"
                        : "bg-slate-200 text-slate-600 dark:bg-white/10 dark:text-slate-300")
                    }>
                      {row.rank}
                    </span>
                    <span className="font-medium truncate flex-1">
                      {row.name}{row.is_me && <span className="badge-brand ml-2">You</span>}
                    </span>
                    <span className="flex items-center gap-1 text-amber-500 text-xs">
                      <Icon name="streak" size={13} /> {row.streak}
                    </span>
                    <span className="font-bold tabular-nums text-brand dark:text-violet-400 w-20 text-right">
                      {row.xp.toLocaleString()} XP
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* F1 — 7-day study plan */}
          <div className="card p-5 md:col-span-3">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="h-section flex items-center gap-2">
                <Icon name="calendar" size={16} /> Your 7-day study plan
              </h2>
              <button onClick={generatePlan} disabled={planBusy} className="btn-ghost text-xs px-3 py-1.5">
                {planBusy ? "Generating…" : plan ? "Regenerate" : "Generate plan"}
              </button>
            </div>
            {!planQ.data && !planQ.error ? (
              <Skeleton className="h-24 w-full" />
            ) : !plan ? (
              <EmptyState
                icon={<Icon name="calendar" size={26} />}
                title="No study plan yet"
                hint="Generate a personalised 7-day plan built from your weak concepts."
              />
            ) : (
              <>
                {plan.summary && <p className="text-sm text-slate-600 dark:text-slate-300 mb-3">{plan.summary}</p>}
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {(plan.days || []).map((d, i) => (
                    <div key={i} className="panel p-3">
                      <p className="text-sm font-semibold">{d.day}</p>
                      <p className="text-xs text-brand dark:text-violet-400 mb-1.5">{d.focus}</p>
                      <ul className="space-y-1">
                        {(d.slots || []).map((s, j) => (
                          <li key={j} className="muted text-xs flex gap-1.5"><span>•</span>{s}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* F2 — concept dependency map */}
          <div className="card p-5 md:col-span-3">
            <div className="flex items-center justify-between gap-3 mb-3">
              <h2 className="h-section flex items-center gap-2">
                <Icon name="concepts" size={16} /> Concept dependency map
              </h2>
              <button onClick={buildConceptMap} disabled={cmapBusy} className="btn-ghost text-xs px-3 py-1.5">
                {cmapBusy ? "Building…" : cmap.built ? "Rebuild" : "Build map"}
              </button>
            </div>
            {!cmapQ.data && !cmapQ.error ? (
              <Skeleton className="h-16 w-full" />
            ) : !cmap.nodes?.length ? (
              <EmptyState
                icon={<Icon name="concepts" size={26} />}
                title="No concept map yet"
                hint="Take a test first, then build a map of what to learn before each weak concept."
              />
            ) : !cmap.built ? (
              <p className="muted text-sm">Click “Build map” to find the prerequisites for your weak concepts.</p>
            ) : (
              <div className="space-y-3">
                {cmap.nodes.map((n, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    {(n.prerequisites || []).length > 0 ? (
                      <>
                        {n.prerequisites.map((p, j) => (
                          <span key={j} className="badge bg-slate-500/10 text-slate-600 dark:text-slate-300 border border-slate-400/30">{p}</span>
                        ))}
                        <Icon name="arrowRight" size={14} className="muted" />
                      </>
                    ) : null}
                    <span className="badge-brand">{n.concept}</span>
                  </div>
                ))}
                <p className="muted text-xs mt-2">Learn the grey prerequisites before each highlighted weak concept.</p>
              </div>
            )}
          </div>

          {/* Recent test results */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3 flex items-center gap-2">
              <Icon name="tests" size={16} /> Recent test results
              {data.recent_tests?.length > 0 && <span className="badge-brand">{data.recent_tests.length}</span>}
            </h2>
            {(!data.recent_tests || data.recent_tests.length === 0) ? (
              <EmptyState
                icon={<Icon name="tests" size={26} />}
                title="No results yet"
                hint="Submit a test and your score appears here right after it's graded."
              />
            ) : (
              <ResultsTable rows={data.recent_tests} />
            )}
          </div>

          {/* Flashcards due */}
          <div className="card p-5 md:col-span-3">
            <h2 className="h-section mb-3 flex items-center gap-2">
              Flashcards due today
              <span className="badge-cyan">{cards.length}</span>
            </h2>
            {dueQ.error && !dueQ.data ? (
              <ErrorState compact message="Couldn't load your flashcards." onRetry={() => dueQ.mutate()} />
            ) : !dueQ.data ? (
              <Skeleton className="h-24 w-full" />
            ) : cards.length === 0 ? (
              <EmptyState icon={<Icon name="celebrate" size={26} />} title="All caught up!" hint="No flashcards are due right now — nice work." />
            ) : (
              <div className="grid md:grid-cols-2 gap-3">
                {cards.map((c) => (
                  <div key={c.id} className="panel p-4">
                    <p className="text-xs muted mb-1">{c.concept}</p>
                    <p className="font-medium">{c.question}</p>
                    {revealed[c.id] ? (
                      <>
                        <p className="mt-2 text-slate-600 dark:text-slate-300">{c.answer}</p>
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => review(c.id, 1)}
                            className="flex-1 bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-500/30 rounded-lg min-h-[40px] text-sm hover:bg-rose-500/25"
                          >
                            Forgot
                          </button>
                          <button
                            onClick={() => review(c.id, 3)}
                            className="flex-1 bg-amber-400/15 text-amber-600 dark:text-amber-300 border border-amber-400/30 rounded-lg min-h-[40px] text-sm hover:bg-amber-400/25"
                          >
                            Hard
                          </button>
                          <button
                            onClick={() => review(c.id, 5)}
                            className="flex-1 bg-emerald-500/15 text-emerald-600 dark:text-emerald-300 border border-emerald-500/30 rounded-lg min-h-[40px] text-sm hover:bg-emerald-500/25"
                          >
                            Easy
                          </button>
                        </div>
                      </>
                    ) : (
                      <button
                        onClick={() => setRevealed({ ...revealed, [c.id]: true })}
                        className="mt-2 text-brand dark:text-violet-400 text-sm font-medium hover:underline"
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
