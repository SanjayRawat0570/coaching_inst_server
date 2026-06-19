"""Doubt Cluster Agent (F3) — groups similar student doubts so a teacher sees the
hot topics at a glance.

Embeds recent doubts (MiniLM), clusters them by cosine similarity (Agglomerative),
labels each cluster, and stores the top clusters per institute in `doubt_clusters`.
Runs nightly; can also be triggered on demand from the teacher dashboard.
"""

import os
import uuid as _uuid
from collections import Counter
from datetime import datetime, timezone, timedelta

from rag.embedder import embed_batch


def _as_uuid(value):
    try:
        return str(_uuid.UUID(str(value))) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _supabase():
    from supabase import create_client
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY"))


def _label_for(questions: list[str]) -> str:
    """Short topic label for a cluster — LLM if available, else the shortest doubt."""
    rep = min(questions, key=len)
    try:
        from graph.llm import get_llm
        out = get_llm(temperature=0).invoke(
            "Give a 3-6 word topic label for this group of student doubts. "
            "Reply with ONLY the label.\n- " + "\n- ".join(questions[:6])
        ).content.strip().strip('"')
        return out[:80] or rep[:80]
    except Exception:
        return rep[:80]


def _cluster_group(doubts: list[dict], max_clusters: int = 8) -> list[dict]:
    """Cluster one institute's doubts; return top clusters (size >= 2)."""
    from sklearn.cluster import AgglomerativeClustering

    questions = [d.get("question") or "" for d in doubts]
    if len(questions) < 2:
        return []
    vectors = embed_batch(questions)

    model = AgglomerativeClustering(
        n_clusters=None, distance_threshold=0.45, metric="cosine", linkage="average"
    )
    labels = model.fit_predict(vectors)

    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(i)

    clusters = []
    for idxs in groups.values():
        if len(idxs) < 2:
            continue  # only surface genuinely repeated doubts
        qs = [questions[i] for i in idxs]
        subs = [doubts[i].get("subject") for i in idxs if doubts[i].get("subject")]
        clusters.append({
            "label": _label_for(qs),
            "subject": (Counter(subs).most_common(1)[0][0] if subs else None),
            "size": len(idxs),
            "samples": qs[:3],
        })
    clusters.sort(key=lambda c: c["size"], reverse=True)
    return clusters[:max_clusters]


def cluster_doubts(days: int = 7) -> dict:
    """Cluster recent doubts per institute and persist the top clusters."""
    sb = _supabase()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    doubts = (sb.table("doubt_logs").select("id, student_id, question, subject, created_at")
              .gte("created_at", since).limit(2000).execute().data) or []
    if not doubts:
        return {"institutes": 0, "clusters": 0}

    # Map each doubt to its institute via the students table.
    sids = list({d["student_id"] for d in doubts if d.get("student_id")})
    inst_of = {}
    if sids:
        srows = (sb.table("students").select("id, institute_id")
                 .in_("id", sids).execute().data) or []
        inst_of = {s["id"]: s.get("institute_id") for s in srows}

    by_inst: dict = {}
    for d in doubts:
        by_inst.setdefault(inst_of.get(d.get("student_id")), []).append(d)

    total = 0
    for institute_id, group in by_inst.items():
        clusters = _cluster_group(group)
        # Replace this institute's previous clusters.
        try:
            q = sb.table("doubt_clusters").delete()
            q = q.is_("institute_id", "null") if institute_id is None else q.eq("institute_id", institute_id)
            q.execute()
        except Exception as e:
            print(f"[doubt_cluster] clear failed: {e}")
        for c in clusters:
            try:
                sb.table("doubt_clusters").insert({**c, "institute_id": institute_id}).execute()
                total += 1
            except Exception as e:
                print(f"[doubt_cluster] insert failed: {e}")

    return {"institutes": len(by_inst), "clusters": total}


def top_clusters(institute_id: str | None, limit: int = 8) -> list[dict]:
    """Stored doubt clusters for a teacher's institute (newest first, biggest first)."""
    try:
        sb = _supabase()
        q = sb.table("doubt_clusters").select("*")
        iid = _as_uuid(institute_id)
        q = q.eq("institute_id", iid) if iid else q.is_("institute_id", "null")
        rows = q.order("size", desc=True).limit(limit).execute().data or []
        return rows
    except Exception as e:
        print(f"[doubt_cluster] top_clusters failed: {e}")
        return []


def run_nightly() -> dict:
    """Scheduled nightly job — recompute clusters from the last 7 days of doubts."""
    return cluster_doubts(days=7)
