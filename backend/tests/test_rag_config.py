"""rag/rag_config.py — per-institute tenant/key lookup with env fallback + cache."""

import pytest

from rag import rag_config

INST = "11111111-1111-1111-1111-111111111111"


class _Query:
    def __init__(self, rows, log, table):
        self.rows, self.log, self.table = rows, log, table

    def select(self, *_):
        return self

    def eq(self, *_):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        self.log.append(self.table)
        if isinstance(self.rows, Exception):
            raise self.rows
        return type("Res", (), {"data": self.rows})()


class FakeSupabase:
    def __init__(self, tables):
        self.tables, self.log = tables, []

    def table(self, name):
        return _Query(self.tables.get(name, []), self.log, name)


@pytest.fixture(autouse=True)
def _fresh_cache():
    rag_config.clear_cache()
    yield
    rag_config.clear_cache()


def _use(monkeypatch, tables):
    sb = FakeSupabase(tables)
    monkeypatch.setattr(rag_config, "_supabase", lambda: sb)
    return sb


def test_no_institute_uses_env(monkeypatch):
    sb = _use(monkeypatch, {})
    assert rag_config.get_rag_config(None) == ("inst-env", "sk-env")
    assert rag_config.get_rag_config("not-a-uuid") == ("inst-env", "sk-env")
    assert sb.log == []  # no DB lookup at all


def test_env_tenant_default(monkeypatch):
    monkeypatch.delenv("RAG_SERVER_TENANT")
    monkeypatch.delenv("RAG_SERVER_API_KEY")
    assert rag_config.get_rag_config(None) == ("smartcoaching", "")


def test_institute_with_tenant_and_key(monkeypatch):
    _use(monkeypatch, {"institutes": [{"rag_tenant": "inst-a"}],
                       "institute_secrets": [{"rag_api_key": "sk-a"}]})
    assert rag_config.get_rag_config(INST) == ("inst-a", "sk-a")


@pytest.mark.parametrize("tables", [
    {"institutes": [{"rag_tenant": "inst-a"}]},                         # no key
    {"institutes": [{"rag_tenant": None}], "institute_secrets": [{"rag_api_key": "sk-a"}]},
    {},                                                                 # no rows at all
])
def test_half_configured_institute_uses_env(monkeypatch, tables):
    _use(monkeypatch, tables)
    assert rag_config.get_rag_config(INST) == ("inst-env", "sk-env")


def test_lookup_error_uses_env(monkeypatch):
    _use(monkeypatch, {"institutes": RuntimeError("column rag_tenant does not exist")})
    assert rag_config.get_rag_config(INST) == ("inst-env", "sk-env")


def test_result_is_cached(monkeypatch):
    sb = _use(monkeypatch, {"institutes": [{"rag_tenant": "inst-a"}],
                            "institute_secrets": [{"rag_api_key": "sk-a"}]})
    rag_config.get_rag_config(INST)
    rag_config.get_rag_config(INST.upper())  # same institute, different spelling
    assert sb.log == ["institutes", "institute_secrets"]

    rag_config.clear_cache()
    rag_config.get_rag_config(INST)
    assert len(sb.log) == 4


def test_key_never_printed(monkeypatch, capsys):
    _use(monkeypatch, {"institutes": [{"rag_tenant": None}],
                       "institute_secrets": [{"rag_api_key": "sk-secret-123"}]})
    rag_config.get_rag_config(INST)
    assert "sk-secret-123" not in capsys.readouterr().out
