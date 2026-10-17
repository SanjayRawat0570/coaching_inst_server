"""Ingest a study-material file into RAG_SERVER from the command line.

A thin wrapper around rag.study_materials.create_material — the same path as the
teacher's Study Material page: the original goes to Supabase Storage, a
study_materials row is created, and RAG_SERVER does the chunking + indexing.

Usage (from backend/):
    python -m rag.ingest --file data/ncert_pdfs/physics_ch5.pdf --material-type ncert \
        --subject Physics --chapter "Laws of Motion" --institute-id <institute uuid>

For many files at once use scripts/migrate_to_rag_server.py --files DIR.
"""

import argparse
import asyncio
import uuid
from pathlib import Path


def ingest_file(path: str, institute_id: str = None, subject: str = None, chapter: str = None,
                material_type: str = "notes", exam: str = None, class_level: str = None) -> dict:
    """Upload one file as study material. Returns its study_materials row."""
    from rag.study_materials import create_material, CLI_UPLOADER
    file = Path(path)
    return asyncio.run(create_material(
        file.read_bytes(), file.name, institute_id=institute_id, uploaded_by=CLI_UPLOADER,
        subject=subject, chapter=chapter, class_level=class_level, exam=exam,
        material_type=material_type))


def main():
    from dotenv import load_dotenv
    from rag.study_materials import MaterialError, MATERIAL_TYPES
    load_dotenv()

    parser = argparse.ArgumentParser(description="Upload a study-material file to RAG_SERVER")
    parser.add_argument("--file", required=True)
    parser.add_argument("--material-type", default="notes", choices=MATERIAL_TYPES)
    parser.add_argument("--subject", default=None)
    parser.add_argument("--chapter", default=None)
    parser.add_argument("--exam", default=None, help="JEE | NEET | Boards | Other")
    parser.add_argument("--class-level", default=None)
    parser.add_argument("--institute-id", default=None,
                        help="institute uuid (omit for the env-default RAG tenant)")
    args = parser.parse_args()
    if args.institute_id:
        try:
            uuid.UUID(args.institute_id)
        except ValueError:
            raise SystemExit(f"[ingest] --institute-id must be a UUID, got {args.institute_id!r}")

    try:
        row = ingest_file(args.file, args.institute_id, args.subject, args.chapter,
                          args.material_type, args.exam, args.class_level)
    except MaterialError as e:
        raise SystemExit(f"[ingest] {e.detail}")
    print(f"[ingest] {row.get('filename')} -> status {row.get('status')}"
          + (f" ({row.get('message')})" if row.get("message") else ""))


if __name__ == "__main__":
    main()
