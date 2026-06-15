"""Qdrant Cloud — RAG content store. Shared (NCERT + PYQs) + per-institute collections."""

import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
)

client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
)

VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension


def create_shared_collection():
    """NCERT + PYQs — visible to all institutes."""
    client.recreate_collection(
        collection_name="rag_shared",
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )


def create_institute_collection(institute_id: str):
    """Private notes for one institute only."""
    client.recreate_collection(
        collection_name=f"rag_{institute_id}",
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )


def upsert_chunks(chunks: list[dict], collection_name: str):
    """
    Each chunk dict must have: content, source, subject, chapter, level
    source: 'ncert' | 'pyq' | 'institute_notes' | 'video_transcript' | 'nta_cutoff'
    level:  1=raw chunk, 2=paragraph, 3=chapter summary, 4=subject summary (RAPTOR)
    """
    from sentence_transformers import SentenceTransformer
    embedder = SentenceTransformer("all-MiniLM-L6-v2")

    points = []
    for chunk in chunks:
        embedding = embedder.encode(chunk["content"]).tolist()
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "content": chunk["content"],
                "source": chunk.get("source", "unknown"),
                "subject": chunk.get("subject"),
                "chapter": chunk.get("chapter"),
                "level": chunk.get("level", 1),
            },
        ))

    # Batch insert 100 at a time
    for i in range(0, len(points), 100):
        client.upsert(collection_name=collection_name, points=points[i:i + 100])

    return len(points)


def search_qdrant(
    query_embedding: list,
    institute_id: str = None,
    subject: str = None,
    source: str = None,
    level: int = 1,
    top_k: int = 5,
) -> list[str]:
    """Search both shared and institute-specific collections."""

    conditions = []
    if subject:
        conditions.append(FieldCondition(key="subject", match=MatchValue(value=subject)))
    if source:
        conditions.append(FieldCondition(key="source", match=MatchValue(value=source)))
    if level:
        conditions.append(FieldCondition(key="level", match=MatchValue(value=level)))
    qdrant_filter = Filter(must=conditions) if conditions else None

    results = []

    # Search institute-private collection
    if institute_id:
        try:
            hits = client.search(
                collection_name=f"rag_{institute_id}",
                query_vector=query_embedding,
                limit=top_k,
                query_filter=qdrant_filter,
                with_payload=True,
            )
            results.extend([h.payload["content"] for h in hits])
        except Exception:
            pass  # collection may not exist yet for new institute

    # Always search shared collection (NCERT + PYQs)
    try:
        shared_hits = client.search(
            collection_name="rag_shared",
            query_vector=query_embedding,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        results.extend([h.payload["content"] for h in shared_hits])
    except Exception:
        pass

    # Deduplicate preserving order
    seen, unique = set(), []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)

    return unique[:top_k]
