"""Study material — the only way content enters RAG_SERVER.

A teacher uploads a file. The original goes to the private Supabase Storage
bucket `study-materials` (so it can always be re-indexed, e.g. after RAG_SERVER
loses data on one of its own redeploys) and a copy goes to RAG_SERVER for
chunking + indexing. One study_materials row tracks each file.

Files are renamed "{subject}_{chapter}_{material_type}_{original}" so the
citations students see read well ("Physics_Laws_of_Motion_notes_ch5.pdf · p. 4").

Deleting a material removes the row and the stored original only. Chunks already
indexed stay in RAG_SERVER: it is used as-is, and no delete endpoint is called.

Rows with institute_id NULL belong to single-institute / demo setups whose
accounts have no institute; they use the env-default RAG tenant.
"""

import asyncio
import mimetypes
import re
import uuid
from pathlib import PurePath

BUCKET = "study-materials"
MAX_BYTES = 50 * 1024 * 1024  # RAG_SERVER's upload limit
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".html", ".json",
                      ".xml", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
MATERIAL_TYPES = ("notes", "ncert", "pyq", "dpp", "lecture", "other")
EXAMS = ("JEE", "NEET", "Boards", "Other")
NOT_CONFIGURED = ("RAG_SERVER is not configured for your institute, so study material can't "
                  "be indexed yet. Ask your admin to set RAG_SERVER_URL and the API key.")
# CLI uploads (rag/transcribe.py) have no logged-in teacher.
CLI_UPLOADER = "00000000-0000-0000-0000-000000000000"


class MaterialError(Exception):
    """An error with the HTTP status the endpoint should return."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()


def _bucket():
    return _supabase().storage.from_(BUCKET)


def _scoped(query, institute_id):
    return query.eq("institute_id", institute_id) if institute_id else query.is_("institute_id", "null")


def _slug(text, limit: int) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "_", str(text or "")).strip("_.")[:limit].strip("_.")


def citation_filename(original: str, subject=None, chapter=None, material_type=None) -> str:
    """'Physics', 'Laws of Motion', 'notes', 'ch 5.PDF' -> 'Physics_Laws_of_Motion_notes_ch_5.pdf'."""
    p = PurePath(original or "file")
    parts = [s for s in (_slug(subject, 40), _slug(chapter, 60), _slug(material_type, 20)) if s]
    parts.append(_slug(p.stem, 80) or "file")
    return "_".join(parts) + p.suffix.lower()


def normalise_meta(exam=None, material_type=None) -> tuple[str | None, str]:
    """Validate the dropdown values. Returns (exam, material_type)."""
    mt = (material_type or "notes").strip().lower()
    if mt not in MATERIAL_TYPES:
        raise MaterialError(400, f"material_type must be one of: {', '.join(MATERIAL_TYPES)}.")
    ex = (exam or "").strip()
    if ex:
        match = [e for e in EXAMS if e.lower() == ex.lower()]
        if not match:
            raise MaterialError(400, f"exam must be one of: {', '.join(EXAMS)}.")
        ex = match[0]
    return ex or None, mt


def validate_file(filename: str, size: int) -> None:
    ext = PurePath(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise MaterialError(400, "Unsupported file type. Allowed: "
                                 + ", ".join(sorted(e[1:] for e in ALLOWED_EXTENSIONS)) + ".")
    if size == 0:
        raise MaterialError(400, "The file is empty.")
    if size > MAX_BYTES:
        raise MaterialError(413, "The file is larger than 50 MB.")


async def _rag(institute_id):
    """(tenant, api_key) for the institute, or 503 if RAG_SERVER isn't configured."""
    from rag import rag_server_client
    from rag.rag_config import get_rag_config
    tenant, api_key = await asyncio.to_thread(get_rag_config, institute_id)
    if not rag_server_client.is_enabled(api_key):
        raise MaterialError(503, NOT_CONFIGURED)
    return tenant, api_key


def _indexing_fields(sent: dict) -> dict:
    """study_materials columns from an upload_document(wait=False) result."""
    running = sent.get("status") == "running"
    return {"execution_id": sent.get("execution_id"),
            "status": "running" if running else "failed",
            "message": None if running else (sent.get("message") or "Upload to RAG_SERVER failed."),
            "chunks_indexed": None}


# ── Upload / list / re-index / delete ─────────────────────────────────────────

async def create_material(content: bytes, original_name: str, *, institute_id, uploaded_by,
                          subject=None, chapter=None, class_level=None, exam=None,
                          material_type="notes") -> dict:
    """Store the original, send it to RAG_SERVER (no waiting) and save the row."""
    from rag import rag_server_client

    validate_file(original_name, len(content))
    exam, material_type = normalise_meta(exam, material_type)
    tenant, api_key = await _rag(institute_id)

    material_id = str(uuid.uuid4())
    filename = citation_filename(original_name, subject, chapter, material_type)
    path = f"{institute_id or 'shared'}/{material_id}/{filename}"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    try:
        await asyncio.to_thread(_bucket().upload, path, content, {"content-type": mime})
    except Exception as e:
        print(f"[study_materials] storage upload failed for {path}: {e}")
        raise MaterialError(502, f"Could not save the file to Supabase Storage. Check that the "
                                 f"private bucket '{BUCKET}' exists.")

    sent = await rag_server_client.upload_document(content, filename, tenant=tenant,
                                                   api_key=api_key, wait=False)
    row = {"id": material_id, "institute_id": institute_id, "uploaded_by": uploaded_by,
           "filename": filename, "subject": subject or None, "chapter": chapter or None,
           "class_level": class_level or None, "exam": exam, "material_type": material_type,
           "storage_path": path, **_indexing_fields(sent)}
    try:
        data = await asyncio.to_thread(
            lambda: _supabase().table("study_materials").insert(row).execute().data)
    except Exception as e:
        print(f"[study_materials] insert failed: {e}")
        await asyncio.to_thread(_remove_quietly, path)
        raise MaterialError(500, "Could not save the material. Has the study_materials table "
                                 "been created (migrations/2026-10-18_study_materials.sql)?")
    return (data or [row])[0]


async def _refresh(row: dict, api_key: str) -> dict:
    """Ask RAG_SERVER how a running upload is doing; persist it once it's finished."""
    import httpx
    from rag import rag_server_client

    try:
        state = await rag_server_client.upload_status(row["execution_id"], api_key=api_key)
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            return row
        state = {"status": "failed",
                 "message": "RAG_SERVER no longer knows this upload — re-index it."}
    except Exception as e:
        print(f"[study_materials] status check failed for {row['id']}: {e}")
        return row

    if state.get("status") not in ("completed", "failed"):
        return {**row, "progress": state.get("progress")}
    update = {"status": state["status"], "message": state.get("message"),
              "chunks_indexed": state.get("chunks_indexed")}
    try:
        await asyncio.to_thread(
            lambda: _supabase().table("study_materials").update(update).eq("id", row["id"]).execute())
    except Exception as e:
        print(f"[study_materials] status update failed for {row['id']}: {e}")
    return {**row, **update}


async def list_materials(institute_id) -> list[dict]:
    """The institute's materials, newest first; running uploads are refreshed."""
    from rag.rag_config import get_rag_config

    rows = await asyncio.to_thread(lambda: _scoped(
        _supabase().table("study_materials").select("*"), institute_id)
        .order("created_at", desc=True).limit(200).execute().data) or []
    running = [r for r in rows if r.get("status") == "running" and r.get("execution_id")]
    if not running:
        return rows
    _, api_key = await asyncio.to_thread(get_rag_config, institute_id)
    fresh = {r["id"]: r for r in await asyncio.gather(*(_refresh(r, api_key) for r in running))}
    return [fresh.get(r["id"], r) for r in rows]


async def _get(material_id: str, institute_id) -> dict:
    try:
        uuid.UUID(str(material_id))
    except ValueError:
        raise MaterialError(404, "Material not found.")
    rows = await asyncio.to_thread(lambda: _scoped(
        _supabase().table("study_materials").select("*").eq("id", material_id), institute_id)
        .limit(1).execute().data)
    if not rows:
        raise MaterialError(404, "Material not found.")
    return rows[0]


async def reindex_material(material_id: str, institute_id) -> dict:
    """Send the stored original to RAG_SERVER again."""
    from rag import rag_server_client

    row = await _get(material_id, institute_id)
    tenant, api_key = await _rag(institute_id)
    try:
        content = await asyncio.to_thread(_bucket().download, row["storage_path"])
    except Exception as e:
        print(f"[study_materials] storage download failed for {row['storage_path']}: {e}")
        raise MaterialError(502, "The original file could not be read from Supabase Storage.")

    sent = await rag_server_client.upload_document(content, row["filename"], tenant=tenant,
                                                   api_key=api_key, wait=False)
    update = _indexing_fields(sent)
    await asyncio.to_thread(
        lambda: _supabase().table("study_materials").update(update).eq("id", row["id"]).execute())
    return {**row, **update}


def _remove_quietly(path: str) -> None:
    try:
        _bucket().remove([path])
    except Exception as e:
        print(f"[study_materials] storage cleanup failed for {path}: {e}")


async def delete_material(material_id: str, institute_id) -> dict:
    """Remove the stored original and the row. RAG_SERVER chunks stay."""
    row = await _get(material_id, institute_id)
    try:
        await asyncio.to_thread(_bucket().remove, [row["storage_path"]])
    except Exception as e:
        print(f"[study_materials] storage delete failed for {row['storage_path']}: {e}")
        raise MaterialError(502, "Could not delete the file from Supabase Storage. Try again.")
    await asyncio.to_thread(
        lambda: _supabase().table("study_materials").delete().eq("id", row["id"]).execute())
    return {"deleted": row["id"],
            "note": "Chunks already indexed stay searchable in RAG_SERVER."}
