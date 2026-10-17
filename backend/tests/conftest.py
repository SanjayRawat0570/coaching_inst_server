"""Shared test setup: make `backend/` importable and give tests a known RAG env."""

import os
import sys
from types import SimpleNamespace

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


class _FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.op, self.payload, self.filters = db, table, "select", None, []

    def select(self, *_, **__):
        self.op = "select"
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def _filter(self, kind, key, value):
        self.filters.append((kind, key, value))
        return self

    def eq(self, key, value):
        return self._filter("eq", key, value)

    def gte(self, key, value):
        return self._filter("gte", key, value)

    def is_(self, key, value):
        return self._filter("is", key, value)

    def limit(self, *_):
        return self

    def execute(self):
        self.db.calls.append(SimpleNamespace(table=self.table, op=self.op,
                                             payload=self.payload, filters=self.filters))
        rows = self.db.results.get((self.table, self.op), [])
        if callable(rows):
            rows = rows(self)
        if isinstance(rows, Exception):
            raise rows
        return SimpleNamespace(data=rows)


class FakeSupabase:
    """Minimal supabase-py stand-in. Set results[(table, op)] to rows, an
    Exception, or a callable(query) -> rows; inspect .calls afterwards."""

    def __init__(self):
        self.results, self.calls = {}, []

    def table(self, name):
        return _FakeQuery(self, name)

    def ops(self, table, op):
        return [c for c in self.calls if c.table == table and c.op == op]


@pytest.fixture
def fake_sb():
    return FakeSupabase()
