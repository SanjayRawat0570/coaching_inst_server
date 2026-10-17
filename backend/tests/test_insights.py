"""Phase 6: content gaps + answer quality, admin AI usage, cluster sources."""

import pytest
from fastapi.testclient import TestClient

import main
from agents import doubt_cluster_agent
from auth.supabase_auth import get_current_user
from rag import rag_config, rag_server_client

INST = "99999999-9999-9999-9999-999999999999"


def _user(role):
    return lambda: {"id": "auth-1", "email": "t@x.com", "role": role, "institute_id": INST}


@pytest.fixture
def client(monkeypatch, fake_sb):
    monkeypatch.setattr(main, "get_supabase", lambda: fake_sb)
    monkeypatch.setattr(main, "_caller_institute_id", lambda u: INST)
    monkeypatch.setattr(rag_config, "get_rag_config", lambda iid: ("inst-a", "sk-a"))
    main.app.dependency_overrides[get_current_user] = _user("teacher")
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


PREFIX = "Doubt not covered by institute material: "


def test_rag_insights(client, fake_sb):
    fake_sb.results[("alerts", "select")] = [
        {"message": PREFIX + "What is dark matter?", "created_at": "2026-10-10T08:00:00"},
        {"message": PREFIX + "what is dark matter?", "created_at": "2026-10-12T08:00:00"},
        {"message": PREFIX + "Explain string theory", "created_at": "2026-10-11T08:00:00"},
    ]
    fake_sb.results[("students", "select")] = [{"id": "s1"}, {"id": "s2"}]
    fake_sb.results[("doubt_logs", "select")] = [
        {"rating": 5, "answerable": True}, {"rating": 1, "answerable": False},
        {"rating": 5, "answerable": True}, {"rating": None, "answerable": True},
        {"rating": None, "answerable": None},
    ]
    body = client.get("/teacher/rag-insights").json()

    assert body["content_gaps"] == [
        {"question": "What is dark matter?", "count": 2, "last_seen": "2026-10-12T08:00:00"},
        {"question": "Explain string theory", "count": 1, "last_seen": "2026-10-11T08:00:00"},
    ]
    assert body["answer_quality"] == {"doubts": 5, "rated": 3, "helpful_pct": 67, "answerable_pct": 75}
    alerts = fake_sb.ops("alerts", "select")[0].filters
    assert ("eq", "alert_type", "content_gap") in alerts and ("eq", "institute_id", INST) in alerts
    assert ("in", "student_id", ["s1", "s2"]) in fake_sb.ops("doubt_logs", "select")[0].filters


def test_rag_insights_before_migration(client, fake_sb):
    fake_sb.results[("students", "select")] = [{"id": "s1"}]
    fake_sb.results[("doubt_logs", "select")] = RuntimeError("column doubt_logs.rating does not exist")
    body = client.get("/teacher/rag-insights").json()
    assert body == {"content_gaps": [], "answer_quality": None}


def test_rag_insights_teacher_only(client):
    main.app.dependency_overrides[get_current_user] = _user("student")
    assert client.get("/teacher/rag-insights").status_code == 403


def test_admin_rag_usage(client, monkeypatch):
    seen = {}

    async def usage(**kw):
        seen.update(kw)
        return {"total_queries": 12, "cache_hit_rate": 0.25}

    monkeypatch.setattr(rag_server_client, "tenant_usage", usage)
    main.app.dependency_overrides[get_current_user] = _user("admin")
    r = client.get("/admin/rag/usage")
    assert r.json() == {"connected": True, "tenant": "inst-a",
                        "usage": {"total_queries": 12, "cache_hit_rate": 0.25}}
    assert seen == {"tenant": "inst-a", "api_key": "sk-a"} and "sk-a" not in r.text

    async def down(**kw):
        return None
    monkeypatch.setattr(rag_server_client, "tenant_usage", down)
    assert client.get("/admin/rag/usage").json()["connected"] is False

    main.app.dependency_overrides[get_current_user] = _user("teacher")
    assert client.get("/admin/rag/usage").status_code == 403


def test_clusters_get_top_source(monkeypatch):
    searched = []

    def fake_search(q, *, top_k=5, tenant=None, api_key=None):
        searched.append((q, top_k))
        return [{"id": "c", "text": "t", "source": "Physics.pdf", "page": 9}] if "Torque" in q else []

    monkeypatch.setattr(rag_server_client, "search_sync", fake_search)
    monkeypatch.setattr(rag_config, "get_rag_config", lambda iid: ("inst-a", "sk-a"))
    clusters = [{"label": "Torque basics", "samples": ["what is torque"], "size": 3},
                {"label": "Organic naming", "samples": [], "size": 2}]
    out = doubt_cluster_agent._attach_sources(clusters, INST)
    assert out[0]["source"] == {"source": "Physics.pdf", "page": 9}
    assert out[1]["source"] is None
    assert searched[0] == ("Torque basics what is torque", 1)


def test_cluster_insert_retries_without_source(monkeypatch, fake_sb):
    monkeypatch.setattr(doubt_cluster_agent, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(doubt_cluster_agent, "_cluster_group",
                        lambda group: [{"label": "L", "samples": ["q"], "size": 2, "subject": None}])
    monkeypatch.setattr(doubt_cluster_agent, "_attach_sources",
                        lambda c, iid: [{**x, "source": {"source": "a.pdf", "page": 1}} for x in c])
    fake_sb.results[("doubt_logs", "select")] = [{"id": "d1", "student_id": "s1", "question": "q"}]
    fake_sb.results[("students", "select")] = [{"id": "s1", "institute_id": INST}]

    def insert(q):
        if "source" in q.payload:
            raise RuntimeError("column doubt_clusters.source does not exist")
        return [q.payload]

    fake_sb.results[("doubt_clusters", "insert")] = insert
    assert doubt_cluster_agent.cluster_doubts(days=7) == {"institutes": 1, "clusters": 1}
    assert "source" not in fake_sb.ops("doubt_clusters", "insert")[-1].payload
