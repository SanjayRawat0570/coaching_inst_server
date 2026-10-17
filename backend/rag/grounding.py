"""Grounding helpers for the synchronous agents (test generator, reviewer, grader,
flashcards). Retrieval goes to RAG_SERVER only, through rag_server_client.

Everything fails soft: when RAG_SERVER is down, not configured or finds nothing,
the helpers return [] / None and the agent carries on as a plain LLM call with
`source: null` — a run is never failed because of retrieval.
"""

from concurrent.futures import ThreadPoolExecutor

from rag import rag_server_client


def _config(institute_id):
    from rag.rag_config import get_rag_config
    return get_rag_config(institute_id or None)


def enabled(institute_id) -> bool:
    """True when RAG_SERVER is configured for this institute (it may still be down)."""
    _, api_key = _config(institute_id)
    return rag_server_client.is_enabled(api_key)


def retrieve(queries: list[str], institute_id, top_k: int = 3) -> list[dict]:
    """All queries in parallel, merged + de-duplicated: [{id, text, source, page, score}]."""
    queries = [q for q in queries if q and q.strip()]
    if not queries:
        return []
    tenant, api_key = _config(institute_id)
    return rag_server_client.search_many_sync(queries, top_k=top_k, tenant=tenant, api_key=api_key)


def retrieve_each(queries: list[str], institute_id, top_k: int = 3) -> list[list[dict]]:
    """One result list per query (same order), searched in parallel."""
    if not queries:
        return []
    tenant, api_key = _config(institute_id)
    with ThreadPoolExecutor(max_workers=min(6, len(queries))) as pool:
        return list(pool.map(
            lambda q: rag_server_client.search_sync(q, top_k=top_k, tenant=tenant, api_key=api_key)
            if q and q.strip() else [], queries))


def source_of(chunks: list[dict], ref) -> dict | None:
    """{source, page} for the LLM's 1-based "[n]" reference, or None if it isn't valid."""
    try:
        n = int(ref)
    except (TypeError, ValueError):
        return None
    if 1 <= n <= len(chunks):
        return rag_server_client.citations_of([chunks[n - 1]])[0]
    return None


def chunk_for(chunks: list[dict], source: dict | None) -> dict | None:
    """The retrieved chunk a stored {source, page} points at."""
    if not source:
        return None
    for c in chunks or []:
        if c.get("source") == source.get("source") and c.get("page") == source.get("page"):
            return c
    return None
