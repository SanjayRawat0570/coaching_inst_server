"""GET /admin/rag/health — admin only, reports status, never leaks the API key."""

import pytest
from fastapi.testclient import TestClient

import main
from auth.supabase_auth import get_current_user
from rag import rag_config, rag_server_client


def _as(role):
    return lambda: {"id": "auth-1", "email": "a@x.com", "role": role, "institute_id": None}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "_caller_institute_id", lambda user: "inst-uuid")
    monkeypatch.setattr(rag_config, "get_rag_config", lambda iid: ("inst-a", "sk-secret-123"))
    yield TestClient(main.app)  # not used as a context manager -> scheduler isn't started
    main.app.dependency_overrides.clear()


def test_admin_gets_status_without_key(client, monkeypatch):
    async def up():
        return True
    monkeypatch.setattr(rag_server_client, "health", up)
    main.app.dependency_overrides[get_current_user] = _as("admin")

    r = client.get("/admin/rag/health")
    assert r.status_code == 200
    assert r.json() == {"configured": True, "reachable": True, "tenant": "inst-a"}
    assert "sk-secret-123" not in r.text


def test_unreachable_and_unconfigured(client, monkeypatch):
    monkeypatch.delenv("RAG_SERVER_URL")
    main.app.dependency_overrides[get_current_user] = _as("admin")

    r = client.get("/admin/rag/health")
    assert r.json() == {"configured": False, "reachable": False, "tenant": "inst-a"}


@pytest.mark.parametrize("role", ["student", "teacher", "parent"])
def test_non_admin_forbidden(client, role):
    main.app.dependency_overrides[get_current_user] = _as(role)
    assert client.get("/admin/rag/health").status_code == 403
