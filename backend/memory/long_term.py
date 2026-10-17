"""Long-term memory — student learning patterns across all sessions.

Semantic recall of a student's past doubts: each exchange is embedded with the
local all-MiniLM-L6-v2 model (rag/embedder.py) and stored in the Supabase
pgvector table `student_memories`; recall goes through the
`match_student_memories` RPC (cosine similarity, one student at a time).
All free — no paid OpenAI, no Ollama, no separate vector database. Every
function fails soft so the agents keep working if Supabase is unreachable or
the migration (migrations/2026-10-18_remove_old_rag.sql) hasn't been run.

(Specced on Mem0, but mem0ai 0.1.0 was broken; this delivers the same capability.)
"""

TABLE = "student_memories"
MATCH_RPC = "match_student_memories"


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()


def _embed(text: str) -> list[float]:
    from rag.embedder import embed
    return embed(text)


def _vec_literal(vector: list[float]) -> str:
    """pgvector expects a '[0.1,0.2,...]' string literal over PostgREST."""
    return "[" + ",".join(str(x) for x in vector) + "]"


def add_memory(student_id: str, user_text: str, assistant_text: str = "") -> bool:
    """Persist a conversation turn as long-term memory. Returns True on success."""
    if not student_id or not user_text:
        return False
    try:
        memory = user_text if not assistant_text else f"{user_text}\n{assistant_text}"
        _supabase().table(TABLE).insert({
            "student_id": student_id,
            "memory": memory,
            "embedding": _vec_literal(_embed(user_text)),
        }).execute()
        return True
    except Exception as e:
        print(f"[long_term] add failed: {e}")
        return False


def get_memories(student_id: str, query: str, limit: int = 5) -> str:
    """Return a newline-joined string of relevant past memories for this student.

    Safe to call inside any agent node — returns "" on any failure.
    """
    if not student_id or not query:
        return ""
    try:
        rows = _supabase().rpc(MATCH_RPC, {
            "p_student_id": student_id,
            "query_embedding": _vec_literal(_embed(query)),
            "match_count": limit,
        }).execute().data or []
        return "\n".join(r.get("memory", "") for r in rows if r.get("memory"))
    except Exception as e:
        print(f"[long_term] search failed: {e}")
        return ""
