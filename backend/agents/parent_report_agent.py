"""Parent Reporter — Sunday 8PM weekly progress report to every parent.

Aggregates the week's activity, has the LLM write a warm plain-language paragraph
(parents are not exam experts), emails it to the parent, and logs
it to parent_reports.
"""

from datetime import datetime, timedelta, timezone

from graph.state import CoachingState


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()  # one shared client per process (a new one costs ~1 s)


MAX_ROWS = 1000  # PostgREST's default row cap per request


def _week_summaries(sb, student_ids: list[str], streaks: dict | None = None) -> dict:
    """This week's summary for several students in 3–4 queries in total (not 5 per
    student). streaks: {student_id: streak_days} when the caller already has it."""
    ids = [i for i in dict.fromkeys(student_ids or []) if i]
    if not ids:
        return {}
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    doubt_rows = (sb.table("doubt_logs").select("student_id")
                  .in_("student_id", ids).gte("created_at", week_ago)
                  .limit(MAX_ROWS).execute()).data or []
    doubts = {i: 0 for i in ids}
    for d in doubt_rows:
        if d.get("student_id") in doubts:
            doubts[d["student_id"]] += 1
    if len(doubt_rows) >= MAX_ROWS:  # capped: count each student exactly
        for i in ids:
            doubts[i] = (sb.table("doubt_logs").select("id", count="exact")
                         .eq("student_id", i).gte("created_at", week_ago).execute()).count or 0

    tests = {i: [] for i in ids}
    for t in (sb.table("tests").select("student_id, score, total_marks, subject, created_at")
              .in_("student_id", ids).gte("created_at", week_ago).execute()).data or []:
        tests.setdefault(t.get("student_id"), []).append(t)

    concepts = {i: [] for i in ids}
    for w in (sb.table("weakness_map").select("student_id, concept, score")
              .in_("student_id", ids).execute()).data or []:
        concepts.setdefault(w.get("student_id"), []).append(w)

    if streaks is None:
        streaks = {s["id"]: s.get("streak_days") for s in
                   (sb.table("students").select("id, streak_days").in_("id", ids).execute()).data or []}

    out = {}
    for i in ids:
        rows = concepts.get(i, [])
        # Postgres order: ascending puts NULL scores last, descending first. Ties are
        # broken by concept name (Postgres left them in no fixed order).
        weak = sorted(rows, key=lambda w: (w.get("score") is None, w.get("score") or 0,
                                           w.get("concept") or ""))[:3]
        strong = sorted(rows, key=lambda w: (w.get("score") is not None, -(w.get("score") or 0),
                                             w.get("concept") or ""))[:3]
        ts = tests.get(i, [])
        out[i] = {
            "doubts": doubts.get(i, 0),
            "tests_taken": len(ts),
            "avg_pct": round(
                sum((t["score"] / t["total_marks"] * 100)
                    for t in ts if t.get("total_marks")) / len(ts), 1
            ) if ts else None,
            "streak_days": streaks.get(i) or 0,
            "weak_concepts": [w["concept"] for w in weak],
            "strong_concepts": [s["concept"] for s in strong],
        }
    return out


def _week_summary(sb, student_id: str) -> dict:
    return _week_summaries(sb, [student_id])[student_id]


def _report_html(name: str, report_text: str, summary: dict) -> str:
    """F8: parent email body — the narrative plus the headline scores/doubts/streak."""
    avg = f"{summary['avg_pct']}%" if summary.get("avg_pct") is not None else "—"
    return (
        f"<h2 style='margin:0 0 8px'>Weekly Progress — {name}</h2>"
        f"<p style='line-height:1.5'>{report_text}</p>"
        "<ul style='line-height:1.7'>"
        f"<li><b>Tests taken:</b> {summary.get('tests_taken', 0)}</li>"
        f"<li><b>Average score:</b> {avg}</li>"
        f"<li><b>Doubts asked:</b> {summary.get('doubts', 0)}</li>"
        f"<li><b>Current streak:</b> {summary.get('streak_days', 0)} day(s)</li>"
        "</ul>"
    )


def build_report(student: dict) -> dict:
    """Compose and send one parent report. Returns delivery status.

    F8: emails the PARENT via Resend. Includes scores, doubts and streak.
    """
    from graph.llm import get_llm
    from notifications import send_email

    sb = _supabase()
    summary = _week_summary(sb, student["id"])
    name = student.get("name", "their child")

    try:
        report_text = get_llm(temperature=0.5).invoke(
            f"Write a warm weekly progress report for the parent of {name}, "
            "a JEE/NEET student. Use simple language a non-expert parent understands. "
            "Be encouraging but honest. 4-6 sentences, no bullet points.\n"
            f"This week's data (scores, doubts, streak): {summary}"
        ).content.strip()
    except Exception:
        report_text = (
            f"This week {name} took {summary['tests_taken']} test(s), "
            f"asked {summary['doubts']} doubts, and is on a {summary['streak_days']}-day streak. "
            "Keep encouraging daily practice!"
        )

    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()

    # F8: email the PARENT via Resend.
    parent_email = student.get("parent_email")
    email_res = (send_email(parent_email, f"Weekly Progress Report — {name}",
                            _report_html(name, report_text, summary))
                 if parent_email else {"ok": False, "channel": "email", "error": "no parent email on file"})
    delivered = bool(email_res.get("ok"))
    delivery = email_res

    try:
        sb.table("parent_reports").insert({
            "student_id": student["id"],
            "report_text": report_text,
            "week_start": week_start,
            "delivery_status": "sent" if delivered else "failed",
        }).execute()
    except Exception as e:
        print(f"[parent_report] log insert failed: {e}")

    return {"student_id": student["id"], "delivery": delivery,
            "channels": {"email": email_res}, "report": report_text}


def parent_report_node(state: CoachingState) -> CoachingState:
    """Graph node form (used in the post-test parallel branch as a light notifier)."""
    try:
        sb = _supabase()
        row = sb.table("students").select("*").eq("id", state["student_id"]).limit(1).execute().data
        if not row:
            return {**state, "error": "student_not_found"}
        outcome = build_report(row[0])
        return {**state, "agent_output": outcome["report"]}
    except Exception as e:
        return {**state, "error": str(e)}


def run_weekly() -> dict:
    """Scheduled Sunday 8PM job — report to every parent."""
    sb = _supabase()
    students = sb.table("students").select("*").execute().data or []
    from concurrency import for_each
    # 2 at a time: each sends an email, and Resend's free tier allows 2 requests/second.
    results = for_each(students, build_report, label="parent_report", limit=2)
    sent = sum(1 for r in results if r and r["delivery"].get("ok"))
    return {"students": len(students), "sent": sent}
