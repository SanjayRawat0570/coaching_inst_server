"""AIR Rank Predictor — estimates All India Rank from NTA cutoff data in Qdrant.

After each test we estimate a percentage, retrieve historical rank-vs-score cutoff
chunks (source='nta_cutoff') from Qdrant, and let the LLM map the student to an AIR
band grounded in that data. The latest prediction is persisted onto the student
profile (predicted_rank / _context / _at) so the dashboard can show it as a big
number (F5).
"""

import os
import json
from datetime import datetime, timezone

from graph.state import CoachingState


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def rank_predictor_node(state: CoachingState) -> CoachingState:
    """Set state['air_rank'] as an estimated band, grounded in NTA cutoff RAG data."""
    try:
        from graph.llm import get_llm
        from rag.retriever import embedder
        from rag.qdrant_client import search_qdrant

        result = state.get("evaluation_result") or {}
        score = result.get("score", state.get("score") or 0)
        total = result.get("total_marks") or 0
        pct = round((score / total) * 100, 1) if total else 0.0
        target_exam = state.get("subject") or "JEE"

        # Retrieve historical rank-vs-score cutoffs from the shared NTA collection
        query = f"{target_exam} marks {score} out of {total} percentile rank cutoff"
        embedding = embedder.encode(query).tolist()
        cutoff_chunks = search_qdrant(
            embedding, source="nta_cutoff", level=1, top_k=5
        )
        cutoff_context = "\n".join(cutoff_chunks)

        llm = get_llm()
        raw = llm.invoke(
            f"Estimate an All India Rank band for a {target_exam} aspirant.\n"
            f"Latest test: {score}/{total} ({pct}%).\n"
            f"Historical NTA rank-vs-score data:\n{cutoff_context or '(no data — give a rough band)'}\n"
            'Return ONLY JSON: {"band": "AIR 8,000 - 12,000", '
            '"context": "one short sentence of context"}'
        ).content.strip()

        # Parse the structured band/context; fall back to the raw text as the band.
        band, context = raw, ""
        try:
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            band = (data.get("band") or raw).strip()
            context = (data.get("context") or "").strip()
        except Exception as e:
            print(f"[rank_predictor] JSON parse failed, using raw text: {e}")

        # Best-effort persist onto the student profile so the dashboard can show it.
        try:
            _supabase().table("students").update({
                "predicted_rank": band,
                "predicted_rank_context": context,
                "predicted_rank_at": datetime.now(timezone.utc).isoformat(),
                "last_active": datetime.now(timezone.utc).isoformat(),
            }).eq("id", state["student_id"]).execute()
        except Exception as e:
            print(f"[rank_predictor] persist failed: {e}")

        return {**state, "air_rank": band, "air_rank_context": context, "score": score}

    except Exception as e:
        return {**state, "error": str(e), "air_rank": "Not enough data yet",
                "air_rank_context": ""}
