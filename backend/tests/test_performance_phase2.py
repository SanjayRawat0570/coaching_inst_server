"""Performance Phase 2: batched queries (no N+1), the TTL cache and its
invalidation, never sharing cached data across institutes or roles."""

import pytest
from fastapi.testclient import TestClient

import cache
import main
from agents import flashcard_agent, parent_report_agent, progress_tracker
from auth.supabase_auth import get_current_user
from graph import knowledge_graph

INST_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
INST_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _as(role, uid="auth-1", email="u@x.com"):
    return lambda: {"id": uid, "email": email, "role": role, "institute_id": INST_A}


@pytest.fixture
def client(monkeypatch, fake_sb):
    monkeypatch.setattr(main, "get_supabase", lambda: fake_sb)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def _filter(q, kind, key=None):
    for k, kk, v in q.filters:
        if k == kind and (key is None or kk == key):
            return v
    return None


# ── cache ─────────────────────────────────────────────────────────────────────
def test_cache_hit_then_expiry(monkeypatch):
    calls = []
    compute = lambda: calls.append(1) or len(calls)  # noqa: E731
    assert cache.get_or_set(("leaderboard", INST_A), 30, compute) == 1
    assert cache.get_or_set(("leaderboard", INST_A), 30, compute) == 1
    now = cache.time.monotonic()
    monkeypatch.setattr(cache.time, "monotonic", lambda: now + 31)
    assert cache.get_or_set(("leaderboard", INST_A), 30, compute) == 2


def test_invalidate_institute_only_drops_that_institute_and_unscoped_views():
    for key in [("leaderboard", INST_A), ("leaderboard", INST_B), ("leaderboard", None),
                ("teacher_overview", "teacher", INST_A), ("concept_map", "s1")]:
        cache.get_or_set(key, 60, lambda: "v")
    cache.invalidate_institute(INST_A)
    left = set(cache._store)
    assert ("leaderboard", INST_B) in left and ("concept_map", "s1") in left
    assert ("leaderboard", INST_A) not in left and ("leaderboard", None) not in left
    assert ("teacher_overview", "teacher", INST_A) not in left


def test_cache_can_be_disabled(monkeypatch):
    monkeypatch.setenv("CACHE_DISABLED", "1")
    calls = []
    cache.get_or_set(("k",), 60, lambda: calls.append(1))
    cache.get_or_set(("k",), 60, lambda: calls.append(1))
    assert len(calls) == 2


# ── leaderboard: cached per institute, "is_me" per caller ─────────────────────
def test_leaderboard_is_cached_per_institute_and_personal(client, fake_sb, monkeypatch):
    rows_of = {INST_A: [{"id": "s1", "name": "A", "xp_points": 50}, {"id": "s2", "name": "B", "xp_points": 10}],
               INST_B: [{"id": "s9", "name": "Z", "xp_points": 99}]}
    me = {"auth-1": ("s1", INST_A), "auth-2": ("s2", INST_A), "auth-9": ("s9", INST_B)}
    monkeypatch.setattr(main, "_student_row", lambda uid: {"id": me[uid][0], "institute_id": me[uid][1]})
    fake_sb.results[("students", "select")] = lambda q: rows_of[_filter(q, "eq", "institute_id")]

    main.app.dependency_overrides[get_current_user] = _as("student", "auth-1")
    a1 = client.get("/leaderboard").json()["leaderboard"]
    main.app.dependency_overrides[get_current_user] = _as("student", "auth-2")
    a2 = client.get("/leaderboard").json()["leaderboard"]
    main.app.dependency_overrides[get_current_user] = _as("student", "auth-9")
    b = client.get("/leaderboard").json()["leaderboard"]

    assert [r["is_me"] for r in a1] == [True, False]
    assert [r["is_me"] for r in a2] == [False, True]
    assert [r["name"] for r in b] == ["Z"]                  # never institute A's board
    assert len(fake_sb.ops("students", "select")) == 2      # one per institute


def test_activity_invalidates_the_institute_board(client, fake_sb, monkeypatch):
    monkeypatch.setattr(main, "_student_row", lambda uid: {"id": "s1", "institute_id": INST_A})
    monkeypatch.setattr(main, "_award_badges", lambda sid: set())
    fake_sb.results[("students", "select")] = [{"id": "s1", "xp_points": 0, "institute_id": INST_A}]
    main.app.dependency_overrides[get_current_user] = _as("student")
    client.get("/leaderboard")
    main._award_activity("s1", "doubt")
    client.get("/leaderboard")
    board_reads = [c for c in fake_sb.ops("students", "select") if _filter(c, "eq", "institute_id")]
    assert len(board_reads) == 2


# ── teacher overview ──────────────────────────────────────────────────────────
def test_overview_cache_is_keyed_by_role_and_cleared_by_alert_read(client, fake_sb):
    fake_sb.results[("students", "select")] = [{"id": "s1"}]
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    client.get(f"/teacher/overview?institute_id={INST_A}")
    client.get(f"/teacher/overview?institute_id={INST_A}")
    assert len(fake_sb.ops("alerts", "select")) == 1        # second hit cached
    main.app.dependency_overrides[get_current_user] = _as("admin")
    client.get(f"/teacher/overview?institute_id={INST_A}")
    assert len(fake_sb.ops("alerts", "select")) == 2        # other role: own entry
    main.app.dependency_overrides[get_current_user] = _as("teacher")
    client.post("/teacher/alerts/read", json={"alert_id": "al1"})
    client.get(f"/teacher/overview?institute_id={INST_A}")
    assert len(fake_sb.ops("alerts", "select")) == 3        # re-read after the change


# ── parent report: fixed number of queries for any number of children ─────────
def test_parent_report_batches_all_children(client, fake_sb):
    kids = [{"id": "k1", "name": "Asha", "streak_days": 4}, {"id": "k2", "name": "Ravi", "streak_days": 0}]
    fake_sb.results[("students", "select")] = kids
    fake_sb.results[("doubt_logs", "select")] = [{"student_id": "k1"}, {"student_id": "k1"}, {"student_id": "k2"}]
    fake_sb.results[("tests", "select")] = lambda q: (
        [{"id": "t1", "student_id": "k2", "score": 40, "total_marks": 50, "status": "evaluated"}]
        if _filter(q, "eq", "status") else
        [{"student_id": "k1", "score": 30, "total_marks": 40}])
    fake_sb.results[("weakness_map", "select")] = [
        {"student_id": "k1", "concept": "Optics", "score": 0.2},
        {"student_id": "k1", "concept": "Kinematics", "score": 0.9},
        {"student_id": "k2", "concept": "Atoms", "score": None}]
    fake_sb.results[("parent_reports", "select")] = [{"student_id": "k2", "report_text": "Good week"}]
    main.app.dependency_overrides[get_current_user] = _as("parent", email="p@x.com")

    body = client.get("/parent/report").json()
    k1, k2 = body["children"]
    assert k1["summary"]["doubts"] == 2 and k2["summary"]["doubts"] == 1
    assert k1["summary"]["streak_days"] == 4 and k1["summary"]["avg_pct"] == 75.0
    assert k1["summary"]["weak_concepts"] == ["Optics", "Kinematics"]
    assert k1["summary"]["strong_concepts"] == ["Kinematics", "Optics"]
    assert k1["latest_report"] is None and k2["latest_report"] == "Good week"
    assert k2["recent_tests"][0]["percent"] == 80 and k1["recent_tests"] == []
    assert body["student_name"] == "Asha"                   # top level mirrors child 1
    assert len(fake_sb.calls) == 6                          # was 1 + 7 per child = 15


def test_week_summary_orders_null_scores_like_postgres(fake_sb):
    fake_sb.results[("weakness_map", "select")] = [
        {"student_id": "s", "concept": "a", "score": None},
        {"student_id": "s", "concept": "b", "score": 0.5},
        {"student_id": "s", "concept": "c", "score": 0.1}]
    fake_sb.results[("students", "select")] = [{"id": "s", "streak_days": 1}]
    out = parent_report_agent._week_summary(fake_sb, "s")
    assert out["weak_concepts"] == ["c", "b", "a"]          # ASC: NULLs last
    assert out["strong_concepts"] == ["a", "b", "c"]        # DESC: NULLs first


def test_week_summary_counts_exactly_when_rows_are_capped(fake_sb, monkeypatch):
    monkeypatch.setattr(parent_report_agent, "MAX_ROWS", 2)
    fake_sb.results[("doubt_logs", "select")] = lambda q: [{"student_id": "s"}] * 2
    fake_sb.results[("students", "select")] = [{"id": "s"}]
    parent_report_agent._week_summary(fake_sb, "s")
    assert len(fake_sb.ops("doubt_logs", "select")) == 2    # list + exact count


def test_top_per_student_refetches_a_crowded_out_student(fake_sb):
    def rows(q):
        ids = _filter(q, "in", "student_id")
        return [{"student_id": "busy", "n": i} for i in range(4)] if len(ids) > 1 else [{"student_id": ids[0], "n": 0}]
    fake_sb.results[("tests", "select")] = rows
    out = main._top_per_student(lambda ids: fake_sb.table("tests").select("*").in_("student_id", ids),
                                ["busy", "quiet"], 2)
    assert len(out["busy"]) == 2 and out["quiet"] == [{"student_id": "quiet", "n": 0}]


# ── concept map ───────────────────────────────────────────────────────────────
def test_prerequisites_of_many_uses_three_queries(fake_sb, monkeypatch):
    monkeypatch.setattr(knowledge_graph, "_supabase", lambda: fake_sb)
    concepts = [{"id": "c1", "name": "Optics"}, {"id": "c2", "name": "Waves"}, {"id": "p1", "name": "Trig"}]
    fake_sb.results[("concepts", "select")] = lambda q: (
        [c for c in concepts if c["name"] in (_filter(q, "in", "name") or [])] or
        [c for c in concepts if c["id"] in (_filter(q, "in", "id") or [])])
    fake_sb.results[("concept_relationships", "select")] = [{"from_concept": "p1", "to_concept": "c1"}]
    out = knowledge_graph.prerequisites_of_many(["Optics", "Waves", "Unknown"])
    assert out == {"Optics": ["Trig"], "Waves": [], "Unknown": []}
    assert len(fake_sb.calls) == 3


def test_concept_map_is_cached_and_cleared_by_submit_and_build(client, fake_sb, monkeypatch):
    monkeypatch.setattr(main, "_resolve_student_id", lambda u: "s1")
    monkeypatch.setattr(knowledge_graph, "prerequisites_of_many", lambda names: {n: [] for n in names})
    fake_sb.results[("weakness_map", "select")] = [{"concept": "Optics", "score": 0.1}]
    main.app.dependency_overrides[get_current_user] = _as("student")
    client.get("/student/concept-map")
    client.get("/student/concept-map")
    assert len(fake_sb.ops("weakness_map", "select")) == 1
    cache.invalidate_student("s1")
    client.get("/student/concept-map")
    assert len(fake_sb.ops("weakness_map", "select")) == 2


# ── progress tracker: one read + one write for all concepts ───────────────────
def test_progress_tracker_batches_weakness_updates(fake_sb, monkeypatch):
    monkeypatch.setattr(progress_tracker, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(knowledge_graph, "ensure_concept", lambda *a, **k: "id")
    monkeypatch.setattr(knowledge_graph, "link_prerequisites", lambda *a, **k: [])
    import memory.episodic as episodic
    milestones = []
    monkeypatch.setattr(episodic, "record_milestone", lambda *a, **k: milestones.append(k))
    fake_sb.results[("weakness_map", "select")] = [{"concept": "Optics", "score": 0.7, "attempts": 3}]
    state = {"student_id": "s1", "subject": "Physics", "evaluation_result": {"per_concept": {
        "Optics": {"correct": 4, "total": 4}, "Atoms": {"correct": 1, "total": 2}}}}

    out = progress_tracker.progress_tracker_node(state)["weakness_update"]["concepts"]
    by = {u["concept"]: u for u in out}
    assert by["Optics"]["score"] == round(0.6 * 0.7 + 0.4 * 1.0, 3)  # EMA
    assert by["Optics"]["crossed_mastery"] is True and len(milestones) == 1
    assert by["Atoms"]["score"] == 0.5 and by["Atoms"]["previous"] == 0.0
    assert len(fake_sb.ops("weakness_map", "select")) == 1
    (write,) = fake_sb.ops("weakness_map", "upsert")
    assert {r["concept"]: r["attempts"] for r in write.payload} == {"Optics": 4, "Atoms": 1}


# ── flashcard reminders ───────────────────────────────────────────────────────
def test_due_counts_are_read_in_pages(fake_sb, monkeypatch):
    monkeypatch.setattr(flashcard_agent, "_supabase", lambda: fake_sb)
    pages = {0: [{"student_id": "a"}, {"student_id": "a"}], 2: [{"student_id": "b"}]}
    fake_sb.results[("flashcards", "select")] = lambda q: pages.get(_filter(q, "range")[0], [])
    assert flashcard_agent.due_counts_by_student(page_size=2) == {"a": 2, "b": 1}


def test_flashcard_reminders_email_only_students_with_due_cards(fake_sb, monkeypatch):
    import notifications
    from auth import supabase_auth
    from scheduler import jobs
    sent = []
    monkeypatch.setattr(flashcard_agent, "due_counts_by_student", lambda: {"s1": 3})
    monkeypatch.setattr(supabase_auth, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(notifications, "notify", lambda **k: sent.append(k))
    fake_sb.results[("students", "select")] = [{"id": "s1", "name": "Asha", "email": "a@x.com"}]
    jobs._flashcard_reminders()
    assert [s["to_email"] for s in sent] == ["a@x.com"] and "3 flashcards" in sent[0]["body"]
    assert len(fake_sb.ops("students", "select")) == 1


# ── admin analytics ───────────────────────────────────────────────────────────
def test_admin_analytics_reuses_names_and_is_cached(client, fake_sb, monkeypatch):
    class _Admin:
        @staticmethod
        def list_users():
            return []
    fake_sb.auth = type("A", (), {"admin": _Admin})()
    fake_sb.results[("students", "select")] = [{"id": "s1", "name": "Asha"}]
    fake_sb.results[("tests", "select")] = lambda q: (
        [{"id": "t1", "student_id": "s1", "score": 9, "total_marks": 10, "status": "evaluated"}]
        if _filter(q, "eq", "status") else [])
    main.app.dependency_overrides[get_current_user] = _as("admin")
    body = client.get(f"/admin/analytics?institute_id={INST_A}").json()
    assert body["recent_results"][0]["student_name"] == "Asha"
    assert len(fake_sb.ops("students", "select")) == 1      # names not re-queried
    n = len(fake_sb.calls)
    client.get(f"/admin/analytics?institute_id={INST_A}")
    assert len(fake_sb.calls) == n                          # cached
