"""Advanced RAG pipeline — 6 patterns over Qdrant.

Agentic multi-query → CRAG quality gate → HyDE fallback → Web fallback → CrossEncoder rerank.
"""

import os
import json
from functools import lru_cache

from sentence_transformers import SentenceTransformer, CrossEncoder

from rag.qdrant_client import search_qdrant

os.environ["SENTENCE_TRANSFORMERS_HOME"] = "/tmp/sentence_transformers"

embedder = SentenceTransformer("all-MiniLM-L6-v2")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


# ── Pattern 1: Agentic RAG ────────────────────────────────────────────────────
# AI plans 2-4 targeted sub-queries instead of one fixed search
def agentic_search(question: str, subject: str = None, institute_id: str = None) -> list:
    from graph.llm import get_llm
    llm = get_llm()
    plan = llm.invoke(
        f"Break this into 2-4 specific search queries to find all needed context.\n"
        f"Question: {question}\n"
        f'Return ONLY a JSON array: ["query1", "query2", ...]\nNo preamble.'
    )
    try:
        queries = json.loads(plan.content)
    except Exception:
        queries = [question]

    all_chunks = []
    for q in queries:
        embedding = embedder.encode(q).tolist()
        chunks = search_qdrant(embedding, institute_id=institute_id, subject=subject)
        all_chunks.extend(chunks)

    seen, unique = set(), []
    for c in all_chunks:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


# ── Pattern 2: HyDE ───────────────────────────────────────────────────────────
def hyde_search(question: str, subject: str = None, institute_id: str = None) -> list:
    from graph.llm import get_llm
    llm = get_llm()
    hypothetical = llm.invoke(
        f"Write a 2-paragraph textbook answer (like NCERT) to: {question}\nNo preamble."
    ).content
    embedding = embedder.encode(hypothetical).tolist()
    return search_qdrant(embedding, institute_id=institute_id, subject=subject, top_k=8)


# ── Pattern 3: RAPTOR ─────────────────────────────────────────────────────────
def raptor_search(question: str, complexity: float = 0.5,
                  subject: str = None, institute_id: str = None) -> list:
    level = 3 if complexity > 0.8 else (2 if complexity > 0.4 else 1)
    embedding = embedder.encode(question).tolist()
    return search_qdrant(embedding, institute_id=institute_id, subject=subject, level=level)


# ── Pattern 4: CRAG ───────────────────────────────────────────────────────────
def crag_check(chunks: list, question: str) -> tuple[list, bool]:
    if not chunks:
        return [], False
    from graph.llm import get_llm
    llm = get_llm()
    scores = []
    for chunk in chunks[:5]:
        try:
            s = llm.invoke(
                f"Rate relevance 0-10. Question: {question}\nText: {chunk[:400]}\n"
                f"Return only the number."
            ).content.strip().split()[0]
            scores.append(float(s))
        except Exception:
            scores.append(5.0)
    avg = sum(scores) / len(scores) if scores else 0
    if avg < 5.0:
        return [], False
    return [c for c, s in zip(chunks, scores) if s >= 5.0], True


# ── Pattern 5: Web fallback ───────────────────────────────────────────────────
def web_search_fallback(query: str) -> list:
    from langchain_community.tools.tavily_search import TavilySearchResults
    tool = TavilySearchResults(max_results=3, api_key=os.getenv("TAVILY_API_KEY"))
    results = tool.invoke(query)
    edu_domains = ["ncert.nic.in", "nta.ac.in", "wikipedia.org", ".edu", "khanacademy"]
    return [r["content"] for r in results
            if any(d in r.get("url", "") for d in edu_domains)]


# ── Pattern 6: CrossEncoder Re-ranking ────────────────────────────────────────
def rerank_by_level(query: str, chunks: list, student_level: str = "intermediate") -> list:
    if len(chunks) <= 1:
        return chunks
    contextual_q = f"[Student level: {student_level}] {query}"
    pairs = [(contextual_q, c) for c in chunks]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(scores, chunks), reverse=True)
    return [c for _, c in ranked[:5]]


# ── Combined pipeline ─────────────────────────────────────────────────────────
@lru_cache(maxsize=500)
def full_rag_pipeline(
    question: str,
    subject: str = None,
    institute_id: str = None,
    student_level: str = "intermediate",
) -> list:
    # Step 1: Agentic multi-query search via Qdrant
    chunks = agentic_search(question, subject=subject, institute_id=institute_id)
    # Step 2: CRAG quality check
    good_chunks, ok = crag_check(chunks, question)
    if not ok:
        # Step 3: HyDE fallback
        chunks = hyde_search(question, subject=subject, institute_id=institute_id)
        good_chunks, ok = crag_check(chunks, question)
    if not ok:
        # Step 4: Web search fallback
        good_chunks = web_search_fallback(question)
    if not good_chunks:
        return []
    # Step 5: Re-rank by student level
    return rerank_by_level(question, good_chunks, student_level)
