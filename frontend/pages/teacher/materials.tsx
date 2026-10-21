import { useEffect, useRef, useState } from "react";
import Shell from "../../components/Shell";
import { EmptyState, SkeletonCard } from "../../components/ui";
import Icon from "../../components/Icon";
import { api, apiUpload, errorDetail } from "../../lib/api";
import { supabase } from "../../lib/supabase";

// Mirrors backend rag/study_materials.py.
const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.txt,.md,.html,.json,.xml,.jpg,.jpeg,.png,.bmp,.tif,.tiff";
const MAX_BYTES = 50 * 1024 * 1024;
const MATERIAL_TYPES = [
  { value: "notes", label: "Notes" },
  { value: "ncert", label: "NCERT" },
  { value: "pyq", label: "PYQs" },
  { value: "dpp", label: "DPP" },
  { value: "lecture", label: "Lecture transcript" },
  { value: "other", label: "Other" },
];
const EXAMS = ["JEE", "NEET", "Boards", "Other"];
const EMPTY_FORM = { subject: "", chapter: "", class_level: "", exam: "JEE", material_type: "notes" };

export default function MaterialsPage() {
  const [materials, setMaterials] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<any>(EMPTY_FORM);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [msg, setMsg] = useState({ text: "", error: false });
  const [busyId, setBusyId] = useState(null); // row being re-indexed / deleted
  const [isAdmin, setIsAdmin] = useState(false);
  const [reindexingAll, setReindexingAll] = useState(false);
  const fileRef = useRef(null);

  async function load({ quiet = false } = {}) {
    if (!quiet) setLoading(true);
    try {
      const data = await api("/teacher/materials");
      setMaterials(data.materials || []);
    } catch (e) {
      if (!quiet) setMsg({ text: errorDetail(e), error: true });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    supabase.auth.getUser().then(({ data }) => setIsAdmin(data?.user?.user_metadata?.role === "admin"));
  }, []);

  // Admin: re-send every stored original (after the RAG server lost its data).
  async function reindexAll() {
    if (!window.confirm("Send every stored file to the RAG server again? Use this if answers stopped citing your notes.")) return;
    setReindexingAll(true);
    try {
      const res = await api("/admin/materials/reindex-all", { method: "POST" });
      setMsg({
        text:
          `Re-indexing ${res.sent} of ${res.total} files.` +
          (res.failed?.length ? ` Failed: ${res.failed.map((f) => f.filename).join(", ")}.` : ""),
        error: !!res.failed?.length,
      });
      await load({ quiet: true });
    } catch (err) {
      setMsg({ text: errorDetail(err), error: true });
    } finally {
      setReindexingAll(false);
    }
  }

  // Poll every 3 s while anything is still indexing.
  const anyRunning = materials.some((m) => m.status === "running");
  useEffect(() => {
    if (!anyRunning) return;
    const t = setInterval(() => load({ quiet: true }), 3000);
    return () => clearInterval(t);
  }, [anyRunning]);

  function pickFile(e) {
    const f = e.target.files?.[0] || null;
    if (f && f.size > MAX_BYTES) {
      setMsg({ text: "That file is larger than 50 MB.", error: true });
      e.target.value = "";
      setFile(null);
      return;
    }
    setMsg({ text: "", error: false });
    setFile(f);
  }

  async function upload(e) {
    e.preventDefault();
    if (!file) {
      setMsg({ text: "Choose a file to upload.", error: true });
      return;
    }
    setUploading(true);
    setMsg({ text: "Uploading…", error: false });
    const body = new FormData();
    body.append("file", file);
    Object.entries(form).forEach(([k, v]) => body.append(k, String(v ?? "")));
    try {
      const row = await apiUpload("/teacher/materials/upload", body);
      setMaterials((m) => [row, ...m]);
      setMsg(
        row.status === "failed"
          ? { text: `Saved, but indexing failed: ${row.message}`, error: true }
          : { text: `Uploaded ${row.filename} — indexing now.`, error: false }
      );
      setFile(null);
      setForm({ ...form, chapter: "" });
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setMsg({ text: errorDetail(err), error: true });
    } finally {
      setUploading(false);
    }
  }

  async function reindex(m) {
    setBusyId(m.id);
    try {
      const row = await api(`/teacher/materials/${m.id}/reindex`, { method: "POST" });
      setMaterials((list) => list.map((x) => (x.id === m.id ? row : x)));
    } catch (err) {
      setMsg({ text: errorDetail(err), error: true });
    } finally {
      setBusyId(null);
    }
  }

  async function remove(m) {
    const ok = window.confirm(
      `Delete "${m.filename}"?\n\nThis removes the file from this list and from storage. ` +
        "Chunks already indexed stay searchable in the RAG server."
    );
    if (!ok) return;
    setBusyId(m.id);
    try {
      await api(`/teacher/materials/${m.id}`, { method: "DELETE" });
      setMaterials((list) => list.filter((x) => x.id !== m.id));
    } catch (err) {
      setMsg({ text: errorDetail(err), error: true });
    } finally {
      setBusyId(null);
    }
  }

  const field = (key, label, props = {}) => (
    <div className="min-w-[160px] flex-1">
      <label className="block text-xs muted mb-1">{label}</label>
      <input
        type="text"
        autoComplete="off"
        className="input text-sm"
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        {...props}
      />
    </div>
  );

  return (
    <Shell
      requireRole={["teacher", "admin"]}
      title="Study Material"
      subtitle="Upload notes, NCERT and PYQs — doubts, tests and grading answer from what you upload here"
      actions={
        isAdmin && materials.length > 0 ? (
          <button onClick={reindexAll} disabled={reindexingAll} className="btn-ghost text-sm">
            {reindexingAll ? "Re-indexing…" : "Re-index all"}
          </button>
        ) : null
      }
    >
      <form onSubmit={upload} className="card p-5 mb-6 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-[2]">
            <label className="block text-xs muted mb-1">File (max 50 MB)</label>
            <input ref={fileRef} type="file" accept={ACCEPT} onChange={pickFile} className="input text-sm" />
          </div>
          {field("subject", "Subject", { placeholder: "e.g. Physics" })}
          {field("chapter", "Chapter", { placeholder: "e.g. Laws of Motion" })}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          {field("class_level", "Class", { placeholder: "e.g. 11, 12, Dropper" })}
          <div>
            <label className="block text-xs muted mb-1">Exam</label>
            <select className="input text-sm" value={form.exam} onChange={(e) => setForm({ ...form, exam: e.target.value })}>
              {EXAMS.map((x) => (
                <option key={x} value={x}>{x}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs muted mb-1">Type</label>
            <select
              className="input text-sm"
              value={form.material_type}
              onChange={(e) => setForm({ ...form, material_type: e.target.value })}
            >
              {MATERIAL_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <button type="submit" disabled={uploading} className="btn-primary px-5">
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
        {msg.text && (
          <p className={"text-sm " + (msg.error ? "text-rose-600 dark:text-rose-400" : "muted")}>{msg.text}</p>
        )}
      </form>

      {loading ? (
        <div className="space-y-4">
          <SkeletonCard lines={3} />
          <SkeletonCard lines={3} />
        </div>
      ) : materials.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={<Icon name="concepts" size={26} />}
            title="No study material yet"
            hint="Upload your notes, NCERT chapters or PYQs above. Student doubts will cite them."
          />
        </div>
      ) : (
        <div className="card p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left muted border-b border-slate-200 dark:border-white/10">
                <th className="py-3 px-4 font-medium">File</th>
                <th className="py-3 px-4 font-medium">Subject / chapter</th>
                <th className="py-3 px-4 font-medium">Type</th>
                <th className="py-3 px-4 font-medium">Status</th>
                <th className="py-3 px-4 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {materials.map((m) => (
                <tr key={m.id} className="border-b border-slate-100 dark:border-white/5 align-top">
                  <td className="py-3 px-4">
                    <p className="font-medium break-all">{m.filename}</p>
                    <p className="text-xs muted">
                      {[m.exam, m.class_level && `Class ${m.class_level}`, m.created_at && new Date(m.created_at).toLocaleDateString()]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </td>
                  <td className="py-3 px-4">{[m.subject, m.chapter].filter(Boolean).join(" / ") || <span className="muted">—</span>}</td>
                  <td className="py-3 px-4">
                    <span className="badge-cyan">{MATERIAL_TYPES.find((t) => t.value === m.material_type)?.label || m.material_type || "—"}</span>
                  </td>
                  <td className="py-3 px-4">
                    <StatusBadge m={m} />
                  </td>
                  <td className="py-3 px-4 text-right whitespace-nowrap">
                    {m.status !== "running" && (
                      <button
                        onClick={() => reindex(m)}
                        disabled={busyId === m.id}
                        className="btn-ghost text-xs px-3 py-1.5"
                        title="Send the stored original to the RAG server again"
                      >
                        Re-index
                      </button>
                    )}
                    <button
                      onClick={() => remove(m)}
                      disabled={busyId === m.id}
                      className="btn-ghost text-xs px-3 py-1.5 text-rose-600 dark:text-rose-400"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs muted px-4 py-3">
            Deleting removes a file from this list and from storage; chunks already indexed stay searchable in the RAG
            server. If answers stop citing your notes after a RAG server update, use Re-index.
          </p>
        </div>
      )}
    </Shell>
  );
}

function StatusBadge({ m }) {
  if (m.status === "running") {
    // RAG_SERVER progress may be a 0–1 fraction or a 0–100 percentage.
    const pct = typeof m.progress === "number" ? Math.round(m.progress <= 1 ? m.progress * 100 : m.progress) : null;
    return (
      <span className="badge-amber inline-flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
        Indexing{pct != null ? ` ${pct}%` : "…"}
      </span>
    );
  }
  if (m.status === "completed") {
    return <span className="badge-green">{m.chunks_indexed ?? 0} chunks</span>;
  }
  return (
    <div className="space-y-1 max-w-xs">
      <span className="badge border bg-rose-500/10 text-rose-600 border-rose-500/30 dark:text-rose-400">Failed</span>
      {m.message && <p className="text-xs muted break-words">{m.message}</p>}
    </div>
  );
}
