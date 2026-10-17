"""Shared test setup: make `backend/` importable and give tests a known RAG env."""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def rag_env(monkeypatch):
    """Every test starts with a configured (but fake) RAG_SERVER."""
    monkeypatch.setenv("RAG_SERVER_URL", "http://rag.test")
    monkeypatch.setenv("RAG_SERVER_API_KEY", "sk-env")
    monkeypatch.setenv("RAG_SERVER_TENANT", "inst-env")
    monkeypatch.setenv("RAG_SERVER_TIMEOUT", "5")


@pytest.fixture
def mock_http(monkeypatch):
    """Route every httpx client through a MockTransport.

    Usage: ``calls = mock_http(handler)`` — handler(request) -> httpx.Response
    (or raises). Returns the list of requests the handler saw.
    """
    real_async, real_sync = httpx.AsyncClient, httpx.Client

    def install(handler):
        calls = []

        def recording(request):
            calls.append(request)
            return handler(request)

        transport = httpx.MockTransport(recording)
        monkeypatch.setattr(httpx, "AsyncClient",
                            lambda *a, **kw: real_async(*a, transport=transport, **kw))
        monkeypatch.setattr(httpx, "Client",
                            lambda *a, **kw: real_sync(*a, transport=transport, **kw))
        return calls

    return install
