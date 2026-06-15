"""RAG ingestion — PDF/text -> chunks -> embed -> Qdrant upsert.

Usage:
    python -m rag.ingest --pdf data/ncert_pdfs/physics.pdf \
        --source ncert --subject Physics --chapter "Laws of Motion" --collection rag_shared

Shared content (NCERT, PYQs, NTA cutoffs) -> rag_shared.
Institute notes -> rag_{institute_id}.
"""

import os
import argparse

from rag.qdrant_client import (
    upsert_chunks, create_shared_collection, create_institute_collection, client,
)


def extract_pdf_text(path: str) -> str:
    """Extract all text from a PDF using PyMuPDF (fitz)."""
    import fitz
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Simple word-window chunker with overlap."""
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def _collection_exists(name: str) -> bool:
    try:
        existing = {c.name for c in client.get_collections().collections}
        return name in existing
    except Exception:
        return False


def ingest_pdf(
    pdf_path: str,
    source: str,
    subject: str = None,
    chapter: str = None,
    level: int = 1,
    collection: str = "rag_shared",
    institute_id: str = None,
) -> int:
    """Ingest one PDF into a Qdrant collection. Returns number of chunks upserted."""
    if institute_id:
        collection = f"rag_{institute_id}"

    # Create the collection if missing (don't recreate — that wipes existing data)
    if not _collection_exists(collection):
        if collection == "rag_shared":
            create_shared_collection()
        elif institute_id:
            create_institute_collection(institute_id)

    text = extract_pdf_text(pdf_path)
    pieces = chunk_text(text)
    chunks = [{
        "content": p,
        "source": source,
        "subject": subject,
        "chapter": chapter,
        "level": level,
    } for p in pieces]

    count = upsert_chunks(chunks, collection)
    print(f"Ingested {count} chunks from {pdf_path} -> {collection}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Ingest a PDF into Qdrant")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--source", required=True,
                        choices=["ncert", "pyq", "institute_notes",
                                 "video_transcript", "nta_cutoff"])
    parser.add_argument("--subject", default=None)
    parser.add_argument("--chapter", default=None)
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument("--collection", default="rag_shared")
    parser.add_argument("--institute-id", default=None)
    args = parser.parse_args()

    ingest_pdf(
        pdf_path=args.pdf,
        source=args.source,
        subject=args.subject,
        chapter=args.chapter,
        level=args.level,
        collection=args.collection,
        institute_id=args.institute_id,
    )


if __name__ == "__main__":
    main()
