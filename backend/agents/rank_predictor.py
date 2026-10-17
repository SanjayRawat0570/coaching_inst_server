"""AIR Rank Predictor — estimates All India Rank from NTA cutoff data.

After each test we estimate a percentage, look up historical marks/percentile ->
rank rows for the student's target exam in the nta_cutoffs table (imported from
CSV with scripts/import_nta_cutoffs.py — this is reference data, not RAG), and let
the LLM map the student to an AIR band grounded in those rows. The latest
prediction is persisted onto the student profile (predicted_rank / _context / _at)
so the dashboard can show it as a big number (F5).
"""

import os
import json
from datetime import datetime, timezone

from graph.state import CoachingState

GENERAL_CATEGORIES = {"gen", "general", "open", "ur", "common rank list", "crl"}


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _target_exam(sb, student_id: str) -> str:
    try:
        row = (sb.table("students").select("target_exam")
               .eq("id", student_id).limit(1).execute().data) or []
        return ((row[0].get("target_exam") if row else None) or "JEE").strip()
    except Exception as e:
        print(f"[rank_predictor] target exam lookup failed: {e}")
        return "JEE"


def cutoff_rows(sb, exam: str, pct: float, limit: int = 20) -> list[dict]:
    """The cutoff rows closest to the student's score, from the latest 2 years.

    General-category rows are preferred when the exam has any. A student's
    percentage is scaled to each row's max_marks; rows without marks are ranked
    by percentile instead.
    """
    try:
        rows = (sb.table("nta_cutoffs")
                .select("exam, year, category, marks, max_marks, percentile, rank")
                .ilike("exam", f"%{exam}%").order("year", desc=True)
                .limit(2000).execute().data) or []
    except Exception as e:
        print(f"[rank_predictor] nta_cutoffs lookup failed (table created?): {e}")
        return []
    if not rows:
        return []
    general = [r for r in rows if str(r.get("category") or "").strip().lower() in GENERAL_CATEGORIES]
    rows = general or rows
    years = sorted({r["year"] for r in rows if r.get("year")}, reverse=True)[:2]
    rows = [r for r in rows if r.get("year") in years]

    def distance(r):
        if r.get("marks") is not None and r.get("max_marks"):
            return abs(float(r["marks"]) / float(r["max_marks"]) * 100 - pct)
        if r.get("percentile") is not None:
            return abs(float(r["percentile"]) - pct)
        return float("inf")

    nearest = sorted(rows, key=distance)[:limit]
    return sorted(nearest, key=lambda r: (-(r.get("year") or 0), r.get("rank") or 0))


def _format_rows(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        marks = (f"{r['marks']}/{r['max_marks']} marks" if r.get("marks") is not None
                 and r.get("max_marks") else f"{r['marks']} marks" if r.get("marks") is not None else "")
        pctl = f"{r['percentile']} percentile" if r.get("percentile") is not None else ""
        lines.append(" | ".join(filter(None, [
            f"{r.get('exam')} {r.get('year')}", r.get("category") or "", marks, pctl,
            f"AIR {r.get('rank')}"])))
    return "\n".join(lines)


def rank_predictor_node(state: CoachingState) -> CoachingState:
    """Set state['air_rank'] as an estimated band, grounded in the nta_cutoffs table."""
    try:
        from graph.llm import get_llm

        result = state.get("evaluation_result") or {}
        score = result.get("score", state.get("score") or 0)
        total = result.get("total_marks") or 0
        pct = round((score / total) * 100, 1) if total else 0.0

        sb = _supabase()
        target_exam = _target_exam(sb, state["student_id"])
        cutoff_context = _format_rows(cutoff_rows(sb, target_exam, pct))

        llm = get_llm()
        raw = llm.invoke(
            f"Estimate an All India Rank band for a {target_exam} aspirant.\n"
            f"Latest test: {score}/{total} ({pct}%). Treat this % as their likely % in the real exam.\n"
            f"Historical NTA marks/percentile -> rank data:\n{cutoff_context or '(no data — give a rough band)'}\n"
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
            sb.table("students").update({
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
