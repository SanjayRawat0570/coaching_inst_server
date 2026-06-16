"""Concept knowledge graph — Supabase pgvector (LAYER 1).

Stores concept embeddings + prerequisite relationships, so the platform can reason
about *why* a student is weak (missing prerequisite) not just *that* they are.

  - ensure_concept   : upsert a concept node with its 384-dim embedding
  - add_relationship : link two concepts (e.g. prerequisite_of)
  - link_prerequisites: LLM-infer prerequisites for a concept and wire them up
  - similar_concepts : pgvector cosine search via the match_concepts RPC
  - prerequisites_of : walk inbound 'prerequisite_of' edges

Everything fails soft so an agent never crashes if the graph is unavailable.
"""

import os
from functools import lru_cache

from rag.embedder import embed


@lru_cache(maxsize=1)
def _supabase():
    from supabase import create_client
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"),
    )


def _vec_literal(vector: list[float]) -> str:
    """pgvector expects a '[0.1,0.2,...]' string literal over PostgREST."""
    return "[" + ",".join(str(x) for x in vector) + "]"


def ensure_concept(name: str, subject: str = None, chapter: str = None,
                   description: str = None) -> str | None:
    """Upsert a concept node; returns its id. Embeds name+description."""
    try:
        sb = _supabase()
        existing = (sb.table("concepts").select("id")
                    .eq("name", name).limit(1).execute().data)
        if existing:
            return existing[0]["id"]

        text = f"{name}. {description or ''}".strip()
        row = sb.table("concepts").insert({
            "name": name,
            "subject": subject,
            "chapter": chapter,
            "description": description,
            "embedding": _vec_literal(embed(text)),
        }).execute().data
        return row[0]["id"] if row else None
    except Exception as e:
        print(f"[knowledge_graph] ensure_concept failed: {e}")
        return None


def add_relationship(from_concept_id: str, to_concept_id: str,
                     relationship: str = "prerequisite_of", weight: float = 1.0) -> bool:
    """Create a directed edge between two concept ids (idempotent)."""
    try:
        _supabase().table("concept_relationships").upsert({
            "from_concept": from_concept_id,
            "to_concept": to_concept_id,
            "relationship": relationship,
            "weight": weight,
        }, on_conflict="from_concept,to_concept,relationship").execute()
        return True
    except Exception as e:
        print(f"[knowledge_graph] add_relationship failed: {e}")
        return False


def link_prerequisites(concept: str, subject: str = None) -> list[str]:
    """Ask the LLM for prerequisite concepts, ensure them, and wire edges.

    Returns the list of prerequisite concept names created/linked.
    """
    try:
        import json
        from graph.llm import get_llm

        target_id = ensure_concept(concept, subject=subject)
        if not target_id:
            return []

        raw = get_llm().invoke(
            f"List 2-4 prerequisite concepts a JEE/NEET student must understand "
            f"before '{concept}'"
            f"{' in ' + subject if subject else ''}. "
            'Return ONLY a JSON array of short concept names. No preamble.'
        ).content
        try:
            prereqs = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
        except Exception:
            prereqs = []

        linked = []
        for p in prereqs:
            pid = ensure_concept(p, subject=subject)
            if pid and pid != target_id:
                # p is a prerequisite_of concept
                add_relationship(pid, target_id, "prerequisite_of")
                linked.append(p)
        return linked
    except Exception as e:
        print(f"[knowledge_graph] link_prerequisites failed: {e}")
        return []


def similar_concepts(query: str, top_k: int = 5) -> list[dict]:
    """Cosine-similarity search over concept embeddings via the match_concepts RPC."""
    try:
        result = _supabase().rpc("match_concepts", {
            "query_embedding": _vec_literal(embed(query)),
            "match_count": top_k,
        }).execute()
        return result.data or []
    except Exception as e:
        print(f"[knowledge_graph] similar_concepts failed (is match_concepts RPC created?): {e}")
        return []


def prerequisites_of(concept: str) -> list[str]:
    """Return names of concepts that are prerequisites of the given concept."""
    try:
        sb = _supabase()
        target = (sb.table("concepts").select("id")
                  .eq("name", concept).limit(1).execute().data)
        if not target:
            return []
        tid = target[0]["id"]
        edges = (sb.table("concept_relationships").select("from_concept")
                 .eq("to_concept", tid).eq("relationship", "prerequisite_of")
                 .execute().data or [])
        ids = [e["from_concept"] for e in edges]
        if not ids:
            return []
        rows = (sb.table("concepts").select("name").in_("id", ids).execute().data or [])
        return [r["name"] for r in rows]
    except Exception as e:
        print(f"[knowledge_graph] prerequisites_of failed: {e}")
        return []
