"""Long-term memory — student learning patterns across all sessions.

Specced on Mem0, but mem0ai 0.1.0 is broken (pgvector schema, missing Qdrant
index, internal validation bugs), so this delivers the same capability directly
on Qdrant + the local all-MiniLM-L6-v2 embedder: semantic recall of a student's
past doubts/notes. All free — no paid OpenAI, no Ollama. Every function fails
soft so the agents keep working even if Qdrant is unreachable.
"""

import uuid
from functools import lru_cache

COLLECTION = "longterm_memories"
VECTOR_SIZE = 384


@lru_cache(maxsize=1)
def _ensure_collection():
    """Create the memories collection + student_id index once. Returns client or None."""
    try:
        from rag.qdrant_client import client
        from qdrant_client.models import VectorParams, Distance, PayloadSchemaType

        names = {c.name for c in client.get_collections().collections}
        if COLLECTION not in names:
            client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
        # Filtering memories by student requires a keyword index on student_id.
        try:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name="student_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # index already exists
        return client
    except Exception as e:
        print(f"[long_term] Qdrant memory unavailable, running without it: {e}")
        return None


def add_memory(student_id: str, user_text: str, assistant_text: str = "") -> bool:
    """Persist a conversation turn as long-term memory. Returns True on success."""
    client = _ensure_collection()
    if client is None or not user_text:
        return False
    try:
        from rag.embedder import embed
        from qdrant_client.models import PointStruct

        memory = user_text if not assistant_text else f"{user_text}\n{assistant_text}"
        client.upsert(collection_name=COLLECTION, points=[PointStruct(
            id=str(uuid.uuid4()),
            vector=embed(user_text),
            payload={"student_id": student_id, "memory": memory},
        )])
        return True
    except Exception as e:
        print(f"[long_term] add failed: {e}")
        return False


def get_memories(student_id: str, query: str, limit: int = 5) -> str:
    """Return a newline-joined string of relevant past memories for this student.

    Safe to call inside any agent node — returns "" on any failure.
    """
    client = _ensure_collection()
    if client is None or not query:
        return ""
    try:
        from rag.embedder import embed
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        hits = client.search(
            collection_name=COLLECTION,
            query_vector=embed(query),
            query_filter=Filter(must=[
                FieldCondition(key="student_id", match=MatchValue(value=student_id))
            ]),
            limit=limit,
            with_payload=True,
        )
        return "\n".join(h.payload.get("memory", "") for h in hits if h.payload)
    except Exception as e:
        print(f"[long_term] search failed: {e}")
        return ""
