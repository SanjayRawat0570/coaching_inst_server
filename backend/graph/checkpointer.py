"""Checkpointer factory — durable graph state for HITL + time-travel debugging.

Preference order:
  1. PostgresSaver on SUPABASE_DB_URL  (durable, survives restarts, true replay)
  2. SqliteSaver on a local file        (durable enough for single-node dev)
  3. In-memory SqliteSaver              (last resort)

Exposes get_state_history() so any past agent execution can be replayed/inspected
(the "time-travel debug" pattern).
"""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_checkpointer():
    """Return the best available checkpointer for this environment."""
    db_url = os.getenv("SUPABASE_DB_URL")

    # 1. PostgresSaver (only in newer langgraph / langgraph-checkpoint-postgres)
    if db_url:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            saver = PostgresSaver.from_conn_string(db_url)
            try:
                saver.setup()  # create checkpoint tables if missing
            except Exception:
                pass
            print("[checkpointer] using PostgresSaver (durable, time-travel enabled)")
            return saver
        except Exception as e:
            print(f"[checkpointer] PostgresSaver unavailable ({e}); falling back to SQLite")

    # 2 & 3. SQLite (file, else in-memory)
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = os.getenv("CHECKPOINT_DB", "/tmp/coaching_checkpoints.sqlite")
        try:
            return SqliteSaver.from_conn_string(path)
        except Exception:
            return SqliteSaver.from_conn_string(":memory:")
    except Exception as e:
        print(f"[checkpointer] no checkpointer available: {e}")
        return None


def get_state_history(thread_id: str) -> list[dict]:
    """Time-travel: list every checkpoint for a run so it can be replayed/inspected."""
    from graph.coaching_graph import get_graph
    saver = get_checkpointer()
    if saver is None:
        return []
    graph = get_graph(checkpointer=saver)
    config = {"configurable": {"thread_id": thread_id}}
    history = []
    try:
        for snapshot in graph.get_state_history(config):
            history.append({
                "checkpoint_id": snapshot.config.get("configurable", {}).get("checkpoint_id"),
                "next": list(snapshot.next),
                "values_keys": list((snapshot.values or {}).keys()),
                "created_at": getattr(snapshot, "created_at", None),
            })
    except Exception as e:
        print(f"[checkpointer] history failed: {e}")
    return history
