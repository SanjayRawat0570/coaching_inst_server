"""Long-term memory — Mem0 backed by Supabase pgvector.

Stores student patterns across all sessions permanently. Internal LLM is Groq and
the embedder is the local all-MiniLM-L6-v2 model — no paid OpenAI, no Ollama.

Every function fails soft: if Mem0 is misconfigured or unreachable the agent keeps
working with an empty memory string instead of crashing.
"""

import os
from functools import lru_cache

# Cache models locally on HF Spaces /tmp (matches Dockerfile)
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "/tmp/sentence_transformers")


def _build_config() -> dict:
    """Mem0 config: pgvector store (Supabase) + Groq LLM + local MiniLM embedder."""
    return {
        "vector_store": {
            "provider": "pgvector",
            "config": {
                "connection_string": os.getenv("SUPABASE_DB_URL"),
                "collection_name": "mem0_memories",
            },
        },
        "llm": {
            "provider": "groq",
            "config": {
                "model": "llama-3.3-70b-versatile",
                "api_key": os.getenv("GROQ_API_KEY"),
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {"model": "all-MiniLM-L6-v2"},
        },
    }


@lru_cache(maxsize=1)
def get_memory_client():
    """Lazily build a single Mem0 client. Returns None if unavailable."""
    try:
        from mem0 import Memory
        return Memory.from_config(_build_config())
    except Exception as e:  # missing deps, bad config, unreachable DB
        print(f"[long_term] Mem0 unavailable, running without long-term memory: {e}")
        return None


def get_memories(student_id: str, query: str, limit: int = 5) -> str:
    """Return a newline-joined string of relevant past memories for this student.

    Safe to call inside any agent node — returns "" on any failure.
    """
    client = get_memory_client()
    if client is None:
        return ""
    try:
        result = client.search(query=query, user_id=student_id, limit=limit)
        items = result.get("results", result) if isinstance(result, dict) else result
        memories = [
            (m.get("memory") or m.get("text") or "")
            for m in (items or [])
        ]
        return "\n".join([m for m in memories if m])
    except Exception as e:
        print(f"[long_term] search failed: {e}")
        return ""


def add_memory(student_id: str, user_text: str, assistant_text: str = "") -> bool:
    """Persist a conversation turn as long-term memory. Returns True on success."""
    client = get_memory_client()
    if client is None:
        return False
    try:
        messages = [{"role": "user", "content": user_text}]
        if assistant_text:
            messages.append({"role": "assistant", "content": assistant_text})
        client.add(messages, user_id=student_id)
        return True
    except Exception as e:
        print(f"[long_term] add failed: {e}")
        return False
