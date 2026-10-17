"""Move content from the old Qdrant RAG into RAG_SERVER (and memories into pgvector).

One-off script. Every upload goes through rag.study_materials.create_material,
so each migrated file also gets a study_materials row and a Storage copy (it can
be re-indexed later from the Study Material page). Always run with --dry-run
first and check the plan.

Three modes (combine as needed):

  --files DIR      the original files (NCERT/PYQ PDFs, notes) still exist:
                   upload every supported file under DIR.
  --from-qdrant    only Qdrant has the text: export each collection's chunks,
                   grouped by (source, subject) into one .md per group with a
                   "## chapter" heading per chapter, and upload those.
  --memories       copy Qdrant `longterm_memories` into the Supabase
                   student_memories table (vectors copied as-is; same model).

Targets: rag_{institute_id} collections go to that institute's tenant. The
shared collection (rag_shared: NCERT/PYQs every institute used to see) goes to
each --shared-to institute, or to the env-default tenant if none is given —
RAG_SERVER tenants are isolated, so shared content must be uploaded per tenant.
--files uploads go to --institute (or the env-default tenant).

source=nta_cutoff chunks are skipped: cutoffs now live in the nta_cutoffs table
(python -m scripts.import_nta_cutoffs <csv>).

qdrant-client is no longer a backend dependency. For --from-qdrant / --memories:
    pip install qdrant-client==1.9.1

Usage (from backend/):
    python -m scripts.migrate_to_rag_server --from-qdrant --memories --dry-run
    python -m scripts.migrate_to_rag_server --files data/ncert_pdfs --material-type ncert \
        --subject Physics --institute <uuid> --dry-run
"""

import argparse
import asyncio
import os
import sys
import uuid
from collections import defaultdict
from pathlib import Path

# Old ingest chunking (rag/ingest.py): 800-word windows overlapping by 120 words.
CHUNK_WORDS, OVERLAP_WORDS = 800, 120
KEY_WORDS = 30
MATERIAL_TYPE = {"ncert": "ncert", "pyq": "pyq", "institute_notes": "notes",
                 "video_transcript": "lecture"}
SKIP_SOURCES = {"nta_cutoff"}
MEMORY_COLLECTION = "longterm_memories"
SOURCE_LABEL = {"ncert": "NCERT", "pyq": "Previous Year Questions",
                "institute_notes": "Institute notes", "video_transcript": "Lecture transcripts"}


# ── Rebuilding documents from chunks ──────────────────────────────────────────

def order_chunks(texts: list[str]) -> str:
    """Re-join overlapping word-window chunks in reading order.

    Qdrant ids were random, so the original order is gone. Chunk i+1 starts with
    the last OVERLAP_WORDS words of chunk i, which lets us chain them back
    together and drop the duplicated overlap. Chunks that don't chain (e.g.
    from different PDFs in one chapter) are appended as separate paragraphs.
    """
    chunks = [t.split() for t in texts if t and t.strip()]
    if not chunks:
        return ""
    by_head = defaultdict(list)
    for i, words in enumerate(chunks):
        by_head[" ".join(words[:KEY_WORDS])].append(i)

    def successor(i):
        tail = chunks[i][CHUNK_WORDS - OVERLAP_WORDS:CHUNK_WORDS - OVERLAP_WORDS + KEY_WORDS]
        if len(chunks[i]) < CHUNK_WORDS or len(tail) < KEY_WORDS:
            return None
        nxt = [j for j in by_head.get(" ".join(tail), []) if j != i]
        return nxt[0] if nxt else None

    nexts = {i: successor(i) for i in range(len(chunks))}
    has_pred = {j for j in nexts.values() if j is not None}
    used, docs = set(), []
    starts = [i for i in range(len(chunks)) if i not in has_pred] + list(range(len(chunks)))
    for start in starts:
        if start in used:
            continue
        words, i, first = [], start, True
        while i is not None and i not in used:
            used.add(i)
            words.extend(chunks[i] if first else chunks[i][OVERLAP_WORDS:])
            first, i = False, nexts[i]
        docs.append(" ".join(words))
    return "\n\n".join(docs)


def build_markdown(source: str, subject: str | None, chapters: dict[str, list[str]]) -> str:
    title = f"{subject or 'General'} — {SOURCE_LABEL.get(source, source)}"
    parts = [f"# {title}", "_Migrated from the old SmartCoaching Qdrant index._"]
    for chapter in sorted(chapters, key=lambda c: (c == "", c)):
        parts.append(f"## {chapter or 'General'}")
        parts.append(order_chunks(chapters[chapter]))
    return "\n\n".join(parts) + "\n"


def group_points(points) -> dict[tuple, dict[str, list[str]]]:
    """{(source, subject): {chapter: [chunk text, ...]}} from Qdrant payloads."""
    groups: dict[tuple, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for p in points:
        pl = p.payload or {}
        source = pl.get("source") or "institute_notes"
        if source in SKIP_SOURCES or (pl.get("level") or 1) != 1:
            continue
        text = pl.get("content") or pl.get("text") or ""
        if text.strip():
            groups[(source, pl.get("subject"))][pl.get("chapter") or ""].append(text)
    return groups


# ── Qdrant access ─────────────────────────────────────────────────────────────

def _qdrant():
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        raise SystemExit("qdrant-client is not installed: pip install qdrant-client==1.9.1")
    if not os.getenv("QDRANT_URL"):
        raise SystemExit("QDRANT_URL is not set (needed only for this one-off migration).")
    return QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"), timeout=60)


def scroll_all(client, collection: str, with_vectors: bool = False):
    offset = None
    while True:
        points, offset = client.scroll(collection, limit=256, offset=offset,
                                       with_payload=True, with_vectors=with_vectors)
        yield from points
        if offset is None:
            return


def _institute_of(collection: str) -> str | None:
    """rag_<uuid> -> uuid; anything else -> None."""
    try:
        return str(uuid.UUID(collection[len("rag_"):]))
    except ValueError:
        return None


# ── Plans ─────────────────────────────────────────────────────────────────────

def plan_qdrant(client, shared_to: list) -> list[dict]:
    """One upload per (target institute, source, subject) group."""
    uploads = []
    for col in client.get_collections().collections:
        name = col.name
        if name == MEMORY_COLLECTION or not name.startswith("rag_"):
            continue
        targets = shared_to if name == "rag_shared" else [_institute_of(name)]
        if name != "rag_shared" and targets == [None]:
            print(f"  ! skipping {name}: not rag_shared or rag_<institute uuid>")
            continue
        groups = group_points(scroll_all(client, name))
        for (source, subject), chapters in sorted(groups.items(), key=lambda g: str(g[0])):
            md = build_markdown(source, subject, chapters)
            for target in targets:
                uploads.append({
                    "collection": name, "institute_id": target, "subject": subject,
                    "material_type": MATERIAL_TYPE.get(source, "other"),
                    "filename": "migrated.md", "content": md.encode("utf-8"),
                    "chunks": sum(len(v) for v in chapters.values()),
                    "chapters": len(chapters)})
    return uploads


def plan_files(folder: str, institute_id, subject, chapter, material_type, exam, class_level):
    from rag.study_materials import ALLOWED_EXTENSIONS, MAX_BYTES
    uploads, skipped = [], []
    for path in sorted(Path(folder).rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS or path.stat().st_size > MAX_BYTES:
            skipped.append(path)
            continue
        uploads.append({"path": path, "institute_id": institute_id, "subject": subject,
                        "chapter": chapter, "material_type": material_type, "exam": exam,
                        "class_level": class_level, "filename": path.name})
    for p in skipped:
        print(f"  ! skipping {p}: unsupported type or over 50 MB")
    return uploads


def run_uploads(uploads: list[dict]) -> int:
    from rag.study_materials import create_material, MaterialError, CLI_UPLOADER, citation_filename
    failed = 0
    for u in uploads:
        content = u["content"] if "content" in u else u["path"].read_bytes()
        name = citation_filename(u["filename"], u.get("subject"), u.get("chapter"), u["material_type"])
        try:
            row = asyncio.run(create_material(
                content, u["filename"], institute_id=u["institute_id"], uploaded_by=CLI_UPLOADER,
                subject=u.get("subject"), chapter=u.get("chapter"), class_level=u.get("class_level"),
                exam=u.get("exam"), material_type=u["material_type"]))
            print(f"  uploaded {name} -> {u['institute_id'] or 'default tenant'}: {row.get('status')}"
                  + (f" ({row.get('message')})" if row.get("message") else ""))
            failed += row.get("status") == "failed"
        except MaterialError as e:
            failed += 1
            print(f"  FAILED {name}: {e.detail}")
    return failed


def migrate_memories(client, dry_run: bool) -> int:
    from memory.long_term import TABLE, _vec_literal
    rows = []
    for p in scroll_all(client, MEMORY_COLLECTION, with_vectors=True):
        pl = p.payload or {}
        vector = p.vector if isinstance(p.vector, list) else None
        if pl.get("student_id") and pl.get("memory") and vector:
            rows.append({"student_id": pl["student_id"], "memory": pl["memory"],
                         "embedding": _vec_literal(vector)})
    print(f"  {len(rows)} memories for {len({r['student_id'] for r in rows})} students")
    if dry_run or not rows:
        return 0
    from auth.supabase_auth import get_supabase
    sb, failed = get_supabase(), 0
    for i in range(0, len(rows), 200):
        batch = rows[i:i + 200]
        try:
            sb.table(TABLE).insert(batch).execute()
        except Exception:
            for r in batch:  # one bad row (e.g. a deleted student) must not drop the batch
                try:
                    sb.table(TABLE).insert(r).execute()
                except Exception as e:
                    failed += 1
                    print(f"  ! memory for student {r['student_id']} skipped: {e}")
    print(f"  copied {len(rows) - failed} memories ({failed} skipped)")
    return failed


# ── CLI ───────────────────────────────────────────────────────────────────────

def _uuid_or_none(value):
    if value in (None, "", "default"):
        return None
    return str(uuid.UUID(value))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Move old Qdrant RAG content into RAG_SERVER")
    p.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    p.add_argument("--from-qdrant", action="store_true")
    p.add_argument("--memories", action="store_true")
    p.add_argument("--files", metavar="DIR")
    p.add_argument("--institute", type=_uuid_or_none, default=None,
                   help="target institute for --files (default: env-default tenant)")
    p.add_argument("--shared-to", type=_uuid_or_none, action="append", default=None,
                   help="institute(s) that get rag_shared; repeatable; 'default' = env tenant")
    p.add_argument("--material-type", default="notes")
    for flag in ("--subject", "--chapter", "--exam", "--class-level"):
        p.add_argument(flag)
    args = p.parse_args(argv)
    if not (args.from_qdrant or args.memories or args.files):
        p.error("choose at least one of --files, --from-qdrant, --memories")

    from dotenv import load_dotenv
    load_dotenv()

    uploads = []
    if args.files:
        print(f"Files under {args.files}:")
        uploads += plan_files(args.files, args.institute, args.subject, args.chapter,
                              args.material_type, args.exam, args.class_level)
    client = _qdrant() if (args.from_qdrant or args.memories) else None
    try:
        if client is not None:
            client.get_collections()
    except Exception as e:
        print(f"Could not reach Qdrant at QDRANT_URL ({e}). Run this from a network that can "
              "reach it, or check whether the cluster is suspended.", file=sys.stderr)
        return 2
    if args.from_qdrant:
        print("Qdrant collections:")
        uploads += plan_qdrant(client, args.shared_to or [None])

    from rag.study_materials import citation_filename
    for u in uploads:
        name = citation_filename(u["filename"], u.get("subject"), u.get("chapter"), u["material_type"])
        extra = (f" — {u['chunks']} chunks, {u['chapters']} chapters from {u['collection']}"
                 if "collection" in u else "")
        print(f"  {'would upload' if args.dry_run else 'upload'} {name} -> "
              f"{u['institute_id'] or 'default tenant'}{extra}")

    failed = 0
    if args.memories:
        print("Long-term memories (Qdrant -> Supabase student_memories):")
        failed += migrate_memories(client, args.dry_run)
    if args.dry_run:
        print(f"Dry run: {len(uploads)} uploads planned, nothing written.")
        return 0
    failed += run_uploads(uploads)
    print(f"Done: {len(uploads)} uploads, {failed} problems. Check the Study Material page.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
