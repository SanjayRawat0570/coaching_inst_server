import { useRef, useState } from "react";
import Shell from "../../components/Shell";
import { streamDoubt } from "../../lib/api";
import { supabase } from "../../lib/supabase";

const SUBJECTS = ["Physics", "Chemistry", "Mathematics", "Biology"];

export default function DoubtPage() {
  const [messages, setMessages] = useState([]); // {role, content}
  const [input, setInput] = useState("");
  const [subject, setSubject] = useState("Physics");
  const [socratic, setSocratic] = useState(false);
  const [status, setStatus] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [image, setImage] = useState(null); // base64 (no data: prefix)
  const fileRef = useRef(null);

  // ── Hindi voice input via the browser Web Speech API (free, Chrome) ──────────
  function startVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
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
      },
      {
        onStatus: (s) => setStatus(s),
        onToken: (t) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = {
              role: "assistant",
              content: copy[copy.length - 1].content + t,
            };
            return copy;
          }),
        onError: (msg) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: "assistant", content: `⚠️ ${msg}` };
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

  return (
    <Shell requireRole="student" title="Ask a Doubt">
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          className="input max-w-[200px]"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
        >
          {SUBJECTS.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm muted">
          <input
            type="checkbox"
            checked={socratic}
            onChange={(e) => setSocratic(e.target.checked)}
          />
          Socratic mode (guide me, don&apos;t just answer)
        </label>
      </div>

      <div className="card h-[55vh] overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <p className="muted text-center mt-20">
            Ask anything — type, speak (🎙 Hindi), or upload a photo of a question.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={
                "inline-block px-4 py-2 rounded-2xl max-w-[80%] whitespace-pre-wrap " +
                (m.role === "user" ? "bg-brand-grad text-white shadow-glow" : "bg-ink-700 text-slate-100")
              }
            >
              {m.content || (streaming ? "…" : "")}
            </div>
          </div>
        ))}
      </div>

      {status && <p className="text-xs muted mt-2">{status}</p>}
      {image && <p className="text-xs text-emerald-300 mt-2">📷 Image attached</p>}

      <div className="flex items-center gap-2 mt-3">
        <button onClick={startVoice} className="btn-ghost" title="Hindi voice">
          🎙
        </button>
        <button
          onClick={() => fileRef.current?.click()}
          className="btn-ghost"
          title="Upload question photo"
        >
          📷
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
          Send
        </button>
      </div>
    </Shell>
  );
}
