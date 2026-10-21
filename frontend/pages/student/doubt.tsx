import { useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import Icon from "../../components/Icon";
import { useToast } from "../../components/Toast";
import { api, streamDoubt } from "../../lib/api";
import { useAuth } from "../../lib/useAuth";

// Markdown + KaTeX are a separate chunk, fetched when this page opens; until it
// arrives an answer shows as plain text (never blank).
function useMarkdown() {
  const [Md, setMd] = useState<any>(null);
  useEffect(() => {
    let alive = true;
    import("../../components/Markdown").then((m) => alive && setMd(() => m.default));
    return () => { alive = false; };
  }, []);
  return Md;
}

export default function DoubtPage() {
  const toast = useToast();
  const Markdown = useMarkdown();
  const { instituteId } = useAuth();
  const [messages, setMessages] = useState([]); // {role, content, meta?, rating?, error?, stopped?}
  const [conversationId, setConversationId] = useState(null); // RAG_SERVER chat memory
  const [input, setInput] = useState("");
  const [subject, setSubject] = useState("");
  const [socratic, setSocratic] = useState(false);
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [image, setImage] = useState(null); // base64 (no data: prefix)
  const fileRef = useRef(null);
  const listRef = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const lastAsk = useRef<{ question: string; image: string | null } | null>(null);

  // Tokens arrive many times a second; they're collected here and drawn at most
  // once per animation frame, so long answers stream smoothly.
  const pending = useRef("");
  const frame = useRef(0);

  function flush() {
    frame.current = 0;
    const chunk = pending.current;
    if (!chunk) return;
    pending.current = "";
    setMessages((m) => {
      const copy = [...m];
      const last = copy[copy.length - 1];
      copy[copy.length - 1] = { ...last, content: last.content + chunk };
      return copy;
    });
  }

  function queueToken(t) {
    pending.current += t;
    if (!frame.current) frame.current = requestAnimationFrame(flush);
  }

  useEffect(() => () => {
    if (frame.current) cancelAnimationFrame(frame.current);
    abortRef.current?.abort();
  }, []);

  // Follow the answer only while the reader is at the bottom; scrolling up to
  // re-read something isn't interrupted.
  function onScroll() {
    const el = listRef.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  }
  useEffect(() => {
    const el = listRef.current;
    if (el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  // ── Hindi voice input via the browser Web Speech API (free, Chrome) ──────────
  function startVoice() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      toast("Voice input needs Chrome.", "info");
      return;
    }
    const rec = new SR();
    rec.lang = "hi-IN";
    rec.onresult = (e) => setInput((prev) => `${prev} ${e.results[0][0].transcript}`.trim());
    rec.start();
  }

  function onPickImage(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImage(String(reader.result).split(",")[1]);
    reader.readAsDataURL(file);
  }

  function updateLast(patch) {
    setMessages((m) => {
      const copy = [...m];
      copy[copy.length - 1] = { ...copy[copy.length - 1], ...patch };
      return copy;
    });
  }

  async function ask(question: string, img: string | null, { retry = false } = {}) {
    const history = messages
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.content }));
    const isFirstMessage = !messages.some((m) => m.role === "assistant" && !m.error);
    lastAsk.current = { question, image: img };
    if (retry) {
      // Replace the failed answer bubble instead of adding another question.
      setMessages((m) => [...m.slice(0, -1), { role: "assistant", content: "" }]);
    } else {
      setMessages((m) => [...m, { role: "user", content: question || "[image question]" },
                          { role: "assistant", content: "" }]);
    }
    atBottom.current = true;
    setStreaming(true);
    setStatus("Reading your question…");
    const controller = new AbortController();
    abortRef.current = controller;

    await streamDoubt(
      {
        institute_id: instituteId,
        question,
        subject,
        socratic,
        image_b64: img,
        conversation_history: history,
        conversation_id: conversationId,
        new_conversation: isFirstMessage,
      },
      {
        signal: controller.signal,
        onStatus: (s) => setStatus(s),
        onMeta: (meta) => {
          if (meta?.conversation_id) setConversationId(meta.conversation_id);
          flush();
          updateLast({ meta });
        },
        onToken: (t) => {
          setStatus("Writing the answer…");
          queueToken(t);
        },
        onError: (msg) => {
          pending.current = "";
          updateLast({ content: msg, error: true });
        },
        onDone: () => {
          flush();
          if (controller.signal.aborted) updateLast({ stopped: true });
          abortRef.current = null;
          setStreaming(false);
          setStatus("");
          setImage(null);
          if (fileRef.current) fileRef.current.value = "";
        },
      },
    );
  }

  function send() {
    const question = input.trim();
    if ((!question && !image) || streaming) return;
    setInput("");
    ask(question, image);
  }

  function stop() {
    abortRef.current?.abort();
  }

  function retry() {
    if (lastAsk.current && !streaming) ask(lastAsk.current.question, lastAsk.current.image, { retry: true });
  }

  function newChat() {
    setMessages([]);
    setConversationId(null);
    setStatus("");
  }

  // 👍 / 👎 — once per answer. Optimistic; rolled back if the request fails.
  async function rate(index, helpful) {
    const msg = messages[index];
    if (!msg?.meta?.doubt_id || msg.rating) return;
    const setRating = (rating) =>
      setMessages((m) => m.map((x, i) => (i === index ? { ...x, rating } : x)));
    setRating(helpful ? "up" : "down");
    try {
      await api("/doubt/feedback", { method: "POST", body: { doubt_id: msg.meta.doubt_id, helpful } });
      toast("Thanks for the feedback!");
    } catch (e) {
      // 409 = already rated earlier: keep the choice shown.
      if (!String(e.message).includes("already rated")) {
        setRating(null);
        toast("Couldn't save your rating. Please try again.", "error");
      }
    }
  }

  return (
    <Shell requireRole="student" title="Ask a Doubt" subtitle="24/7 AI tutor — answers from NCERT & your institute notes">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <label className="sr-only" htmlFor="doubt-subject">Subject</label>
        <input
          id="doubt-subject"
          type="text"
          autoComplete="off"
          className="input max-w-[200px]"
          placeholder="Type any subject"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm muted cursor-pointer select-none min-h-[40px]">
          <input
            type="checkbox"
            className="accent-[#7c5cff] h-4 w-4"
            checked={socratic}
            onChange={(e) => setSocratic(e.target.checked)}
          />
          Socratic mode (guide me, don&apos;t just answer)
        </label>
        <button
          onClick={newChat}
          disabled={streaming || messages.length === 0}
          className="btn-ghost ml-auto text-sm disabled:opacity-50"
          title="Start a fresh conversation"
        >
          New chat
        </button>
      </div>

      <div
        ref={listRef}
        onScroll={onScroll}
        className="card h-[55vh] overflow-y-auto p-4 space-y-4"
        role="log"
        aria-live="polite"
        aria-busy={streaming}
      >
        {messages.length === 0 && (
          <div className="empty-state h-full">
            <span className="icon"><Icon name="doubt" size={26} /></span>
            <p className="font-semibold">Ask me anything</p>
            <p className="muted text-sm mt-1 max-w-sm">
              Type your question, speak it (Hindi supported), or upload a photo of a problem.
            </p>
          </div>
        )}
        {messages.map((m, i) => {
          const isUser = m.role === "user";
          const isLast = i === messages.length - 1;
          const split = isUser || m.error ? { body: m.content, confidence: null } : splitConfidence(m.content);
          const body = split.body;
          // RAG_SERVER's confidence ([META]) wins over a "CONFIDENCE: XX%" line in the text.
          const confidence = m.meta ? m.meta.confidence ?? null : split.confidence;
          const gap = !!m.meta && (m.meta.answerable === false || m.meta.confidence === "low");
          return (
            <div key={i} className={"flex items-end gap-2 " + (isUser ? "flex-row-reverse" : "")}>
              <span
                className={
                  "grid place-items-center h-8 w-8 rounded-lg shrink-0 " +
                  (isUser ? "bg-brand-grad text-white" : "bg-slate-200 text-slate-600 dark:bg-ink-700 dark:text-slate-300")
                }
              >
                <Icon name={isUser ? "user" : "bot"} size={16} className={isUser ? "text-white" : ""} />
              </span>
              <div className={"flex flex-col gap-1 max-w-[85%] min-w-0 " + (isUser ? "items-end" : "items-start")}>
                <div
                  className={
                    "px-4 py-2.5 rounded-2xl leading-relaxed shadow-sm max-w-full overflow-x-auto " +
                    (isUser
                      ? "whitespace-pre-wrap bg-brand-grad text-white rounded-br-sm shadow-glow"
                      : m.error
                      ? "bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-500/10 dark:text-rose-200 dark:border-rose-400/25 rounded-bl-sm"
                      : "bg-slate-100 text-slate-800 dark:bg-ink-700 dark:text-slate-100 rounded-bl-sm")
                  }
                >
                  {isUser || m.error ? (
                    body
                  ) : body ? (
                    Markdown ? <Markdown>{body}</Markdown> : <span className="whitespace-pre-wrap">{body}</span>
                  ) : streaming && isLast ? (
                    <span className="inline-flex gap-1 py-1" aria-label="Writing the answer">
                      <span className="h-2 w-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="h-2 w-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="h-2 w-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: "300ms" }} />
                    </span>
                  ) : (
                    ""
                  )}
                </div>
                {!isUser && m.error && isLast && !streaming && (
                  <button onClick={retry} className="btn-ghost text-xs">
                    <Icon name="arrowRight" size={14} /> Retry
                  </button>
                )}
                {!isUser && m.stopped && <p className="text-xs muted">Stopped.</p>}
                {!isUser && m.meta && <SourceChips citations={m.meta.citations} />}
                {!isUser && gap && (
                  <p className="text-xs rounded-lg px-2.5 py-1.5 bg-amber-500/10 text-amber-700 border border-amber-500/20 dark:text-amber-300 dark:border-amber-400/25">
                    Not clearly covered in your institute&apos;s notes — your teacher has been informed.
                  </p>
                )}
                {!isUser && (confidence != null || m.meta?.doubt_id) && (
                  <div className="flex items-center gap-2">
                    {confidence != null && <ConfidenceBadge value={confidence} />}
                    {m.meta?.doubt_id && (
                      <span className="inline-flex items-center gap-1">
                        {[
                          { helpful: true, key: "up", label: "👍", title: "Helpful" },
                          { helpful: false, key: "down", label: "👎", title: "Not helpful" },
                        ].map((b) => (
                          <button
                            key={b.key}
                            onClick={() => rate(i, b.helpful)}
                            disabled={!!m.rating}
                            title={b.title}
                            aria-label={b.title}
                            aria-pressed={m.rating === b.key}
                            className={
                              "text-sm min-h-[40px] min-w-[40px] rounded-md transition " +
                              (m.rating === b.key
                                ? "bg-brand/15 ring-1 ring-brand/30"
                                : m.rating
                                ? "opacity-30"
                                : "hover:bg-slate-200 dark:hover:bg-ink-700")
                            }
                          >
                            {b.label}
                          </button>
                        ))}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Where the answer is: Reading your question… → Searching your notes… → Writing the answer… */}
      <p className="text-xs muted mt-2 min-h-[1rem] flex items-center gap-1.5" aria-live="polite">
        {status && (
          <>
            <span className="h-1.5 w-1.5 rounded-full bg-brand animate-pulse" />
            {status}
          </>
        )}
      </p>
      {image && <p className="inline-flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-300 mt-2"><Icon name="camera" size={13} /> Image attached</p>}

      <div className="flex items-center gap-2 mt-3">
        <button onClick={startVoice} className="btn-ghost px-2.5" title="Hindi voice input" aria-label="Voice input">
          <Icon name="mic" size={18} />
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          className="btn-ghost px-2.5"
          title="Upload question photo"
          aria-label="Upload photo"
        >
          <Icon name="camera" size={18} />
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={onPickImage}
        />
        {/* The box stays usable while an answer streams: type the next question. */}
        <input
          className="input flex-1 min-w-0"
          aria-label="Your doubt"
          placeholder="Type your doubt…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        {streaming ? (
          <button onClick={stop} className="btn-ghost px-5" aria-label="Stop the answer">
            Stop
          </button>
        ) : (
          <button onClick={send} className="btn-primary px-5">
            Send <Icon name="send" size={16} />
          </button>
        )}
      </div>
    </Shell>
  );
}

// F16 — pull "CONFIDENCE: XX%" off the end of an answer and return the clean body.
function splitConfidence(text) {
  if (!text) return { body: text, confidence: null };
  const m = text.match(/CONFIDENCE:\s*(\d{1,3})\s*%/i);
  if (!m) return { body: text, confidence: null };
  return {
    body: text.replace(m[0], "").trimEnd(),
    confidence: Math.min(100, parseInt(m[1], 10)),
  };
}

// value: a 0–100 number (old "CONFIDENCE: XX%" answers) or RAG_SERVER's "high" | "medium" | "low".
function ConfidenceBadge({ value }) {
  const level =
    typeof value === "number" ? (value >= 80 ? "high" : value >= 50 ? "medium" : "low") : String(value).toLowerCase();
  const tone =
    level === "high" ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
    : level === "medium" ? "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30"
    : "bg-rose-500/15 text-rose-600 dark:text-rose-400 border-rose-500/30";
  const label = typeof value === "number" ? `${value}% confident` : `${level.charAt(0).toUpperCase()}${level.slice(1)} confidence`;
  return (
    <span className={"inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border " + tone}>
      <Icon name="check" size={12} /> {label}
    </span>
  );
}

// "Physics_Notes.pdf · p. 12" chips, one per distinct source + page.
function SourceChips({ citations }) {
  const seen = new Set();
  const chips = (citations || []).filter((c) => {
    if (!c?.source) return false;
    const key = `${c.source}|${c.page ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (!chips.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <span key={`${c.source}|${c.page ?? ""}`} className="badge-brand" title={c.source}>
          {c.source}
          {c.page != null && c.page !== "" ? ` · p. ${c.page}` : ""}
        </span>
      ))}
    </div>
  );
}
