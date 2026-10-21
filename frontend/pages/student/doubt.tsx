import { useRef, useState } from "react";
import Shell from "../../components/Shell";
import Icon from "../../components/Icon";
import { api, streamDoubt } from "../../lib/api";
import { supabase } from "../../lib/supabase";

export default function DoubtPage() {
  const [messages, setMessages] = useState([]); // {role, content, meta?, rating?}
  const [conversationId, setConversationId] = useState(null); // RAG_SERVER chat memory
  const [input, setInput] = useState("");
  const [subject, setSubject] = useState("");
  const [socratic, setSocratic] = useState(false);
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [image, setImage] = useState(null); // base64 (no data: prefix)
  const fileRef = useRef(null);

  // ── Hindi voice input via the browser Web Speech API (free, Chrome) ──────────
  function startVoice() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      alert("Voice input needs Chrome.");
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

  async function send() {
    const question = input.trim();
    if (!question && !image) return;

    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    const isFirstMessage = messages.length === 0;
    const userMsg = { role: "user", content: question || "[image question]" };
    setMessages((m) => [...m, userMsg, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);
    setStatus("Thinking…");

    // institute_id comes from the logged-in user's metadata
    const {
      data: { user },
    } = await supabase.auth.getUser();
    const institute_id = user?.user_metadata?.institute_id || "";

    await streamDoubt(
      {
        institute_id,
        question,
        subject,
        socratic,
        image_b64: image,
        conversation_history: history,
        conversation_id: conversationId,
        new_conversation: isFirstMessage,
      },
      {
        onStatus: (s) => setStatus(s),
        onMeta: (meta) => {
          if (meta?.conversation_id) setConversationId(meta.conversation_id);
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { ...copy[copy.length - 1], meta };
            return copy;
          });
        },
        onToken: (t) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = {
              ...copy[copy.length - 1],
              content: copy[copy.length - 1].content + t,
            };
            return copy;
          }),
        onError: (msg) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: "assistant", content: `Error: ${msg}` };
            return copy;
          }),
        onDone: () => {
          setStreaming(false);
          setStatus("");
          setImage(null);
          if (fileRef.current) fileRef.current.value = "";
        },
      }
    );
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
    } catch (e) {
      // 409 = already rated earlier: keep the choice shown.
      if (!String(e.message).includes("already rated")) setRating(null);
    }
  }

  return (
    <Shell requireRole="student" title="Ask a Doubt" subtitle="24/7 AI tutor — answers from NCERT & your institute notes">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <input
          type="text"
          autoComplete="off"
          className="input max-w-[200px]"
          placeholder="Type any subject"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
        />
        <label className="flex items-center gap-2 text-sm muted cursor-pointer select-none">
          <input
            type="checkbox"
            className="accent-[#7c5cff]"
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

      <div className="card h-[55vh] overflow-y-auto p-4 space-y-4">
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
          const split = isUser ? { body: m.content, confidence: null } : splitConfidence(m.content);
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
              <div className={"flex flex-col gap-1 max-w-[80%] " + (isUser ? "items-end" : "items-start")}>
                <div
                  className={
                    "px-4 py-2.5 rounded-2xl whitespace-pre-wrap leading-relaxed shadow-sm " +
                    (isUser
                      ? "bg-brand-grad text-white rounded-br-sm shadow-glow"
                      : "bg-slate-100 text-slate-800 dark:bg-ink-700 dark:text-slate-100 rounded-bl-sm")
                  }
                >
                  {body || (streaming && isLast ? (
                    <span className="inline-flex gap-1 py-1">
                      <span className="h-2 w-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="h-2 w-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="h-2 w-2 rounded-full bg-current opacity-60 animate-bounce" style={{ animationDelay: "300ms" }} />
                    </span>
                  ) : "")}
                </div>
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
                            className={
                              "text-sm px-1.5 py-0.5 rounded-md transition " +
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

      {status && <p className="text-xs muted mt-2">{status}</p>}
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
        <input
          className="input flex-1"
          placeholder="Type your doubt…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !streaming && send()}
        />
        <button
          onClick={send}
          disabled={streaming}
          className="btn-primary px-5"
        >
          Send <Icon name="send" size={16} />
        </button>
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
