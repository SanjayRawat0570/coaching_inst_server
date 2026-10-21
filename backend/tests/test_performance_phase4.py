"""Performance Phase 4: scheduled jobs run once across workers, are timed, batch
their students, and the Docker image stays CPU-only with the model baked in."""

import pathlib
import sys
import threading
import time
import types

import pytest

from concurrency import for_each
from scheduler import jobs as sched_jobs
from scheduler import locks

ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── advisory lock: the first worker runs, the others skip ─────────────────────
class _FakePg:
    """psycopg2 stand-in sharing one lock table, like one Postgres server."""

    held: set = set()
    guard = threading.Lock()

    @classmethod
    def connect(cls, *_a, **_k):
        return cls._Conn()

    class _Conn:
        autocommit = False

        def cursor(self):
            return _FakePg._Cur()

        def close(self):
            pass

    class _Cur:
        def execute(self, sql, params):
            key = params[0]
            with _FakePg.guard:
                if "unlock" in sql:
                    _FakePg.held.discard(key)
                    self.result = (True,)
                elif key in _FakePg.held:
                    self.result = (False,)
                else:
                    _FakePg.held.add(key)
                    self.result = (True,)

        def fetchone(self):
            return self.result


@pytest.fixture
def fake_pg(monkeypatch):
    _FakePg.held = set()
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=_FakePg.connect))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://fake")
    monkeypatch.setattr(locks, "MIN_HOLD_SECONDS", 0.3)


def test_only_one_worker_runs_a_job(fake_pg):
    ran, results = [], []

    def job():
        ran.append(1)
        return "done"

    workers = [threading.Thread(target=lambda: results.append(locks.run_exclusive("at_risk", job)))
               for _ in range(4)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert len(ran) == 1
    assert sorted(results) == ["done"] + [locks.SKIPPED] * 3
    assert not _FakePg.held  # released afterwards


def test_a_fast_job_holds_the_lock_long_enough_for_a_late_duplicate(fake_pg):
    out = []
    first = threading.Thread(target=lambda: out.append(locks.run_exclusive("x", lambda: "a")))
    first.start()
    time.sleep(0.1)  # second worker fires a moment later; job "a" is long finished
    out.append(locks.run_exclusive("x", lambda: "b"))
    first.join()
    assert sorted(out) == ["a", locks.SKIPPED]


def test_different_jobs_dont_block_each_other(fake_pg):
    out = []
    t = threading.Thread(target=lambda: out.append(locks.run_exclusive("a", lambda: 1)))
    t.start()
    out.append(locks.run_exclusive("b", lambda: 2))
    t.join()
    assert sorted(out) == [1, 2]


def test_unreachable_database_still_runs_the_job(monkeypatch):
    def refuse(*_a, **_k):
        raise OSError("connection refused")
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=refuse))
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://down")
    monkeypatch.setattr(locks, "MIN_HOLD_SECONDS", 0)
    assert locks.run_exclusive("x", lambda: "ran") == "ran"


def test_lock_keys_fit_postgres_int():
    for name in ("at_risk_nightly", "flashcard_reminders", "x" * 200):
        assert -2 ** 31 <= locks._key(name) < 2 ** 31
    assert locks._key("a") == locks._key("a") != locks._key("b")


# ── the scheduler's wrapper: timed, recorded, never raising ───────────────────
def test_guarded_job_records_its_run(monkeypatch):
    monkeypatch.setattr(sched_jobs, "run_exclusive", lambda name, fn: fn())
    sched_jobs._guarded("demo", lambda: "ok")()
    assert sched_jobs.LAST_RUNS["demo"]["status"] == "ok"
    assert sched_jobs.LAST_RUNS["demo"]["duration_s"] >= 0


def test_guarded_job_marks_skips_and_failures(monkeypatch):
    monkeypatch.setattr(sched_jobs, "run_exclusive", lambda name, fn: locks.SKIPPED)
    sched_jobs._guarded("skip", lambda: None)()
    assert sched_jobs.LAST_RUNS["skip"]["status"] == "skipped"

    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(sched_jobs, "run_exclusive", lambda name, fn: fn())
    sched_jobs._guarded("bad", boom)()  # must not raise
    assert sched_jobs.LAST_RUNS["bad"]["status"] == "failed"


def test_scheduler_registers_aligned_cron_jobs(monkeypatch):
    added = []

    class _FakeScheduler:
        def __init__(self, **kw):
            self.kw = kw

        def add_job(self, fn, trigger, id, **when):
            added.append((id, trigger, when))

        def start(self):
            pass

        def get_jobs(self):
            return [type("J", (), {"id": a[0]}) for a in added]

        def shutdown(self, wait=False):
            pass

    monkeypatch.setattr(sched_jobs, "BackgroundScheduler", _FakeScheduler)
    monkeypatch.setattr(sched_jobs, "_scheduler", None)
    s = sched_jobs.start_scheduler()
    assert s.kw["job_defaults"] == {"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}
    assert {a[1] for a in added} == {"cron"}
    assert dict((a[0], a[2]) for a in added)["flashcard_reminders"] == {"minute": "*/5"}
    assert len(added) == 6
    monkeypatch.setattr(sched_jobs, "_scheduler", None)


# ── batching students ─────────────────────────────────────────────────────────
def test_for_each_batches_and_isolates_failures():
    def fn(s):
        if s["id"] == 3:
            raise ValueError("bad row")
        return s["id"] * 10
    out = for_each([{"id": i} for i in range(7)], fn, batch_size=3, limit=2)
    assert out == [0, 10, 20, None, 40, 50, 60]


def test_for_each_runs_a_batch_side_by_side():
    t = time.perf_counter()
    for_each(range(3), lambda _: time.sleep(0.2), batch_size=3, limit=3)
    assert time.perf_counter() - t < 0.45


def test_emailing_jobs_stay_under_resends_rate_limit(monkeypatch, fake_sb):
    from agents import inactivity_alert_agent, parent_report_agent
    seen = {}
    real = for_each

    def spy(items, fn, label="job", batch_size=50, limit=None):
        seen[label] = limit
        return real(items, fn, label=label, batch_size=batch_size, limit=limit)

    import concurrency
    monkeypatch.setattr(concurrency, "for_each", spy)
    fake_sb.results[("students", "select")] = []
    monkeypatch.setattr(inactivity_alert_agent, "_supabase", lambda: fake_sb)
    monkeypatch.setattr(parent_report_agent, "_supabase", lambda: fake_sb)
    inactivity_alert_agent.run_nightly()
    parent_report_agent.run_weekly()
    assert seen == {"inactivity": 1, "parent_report": 2}


# ── Docker image ──────────────────────────────────────────────────────────────
def test_dockerfile_installs_cpu_torch_before_the_requirements():
    text = (ROOT / "Dockerfile").read_text(encoding="utf8")
    cpu = text.index("download.pytorch.org/whl/cpu torch")
    reqs = text.index("pip install -r requirements.txt")
    assert cpu < reqs


def test_dockerfile_bakes_the_model_and_runs_offline():
    text = (ROOT / "Dockerfile").read_text(encoding="utf8")
    assert "SentenceTransformer('all-MiniLM-L6-v2')" in text
    assert "COPY --from=build /opt/models /opt/models" in text
    runtime = text[text.index("FROM python:3.11-slim\n"):]
    assert "HF_HUB_OFFLINE=1" in runtime
    assert "SENTENCE_TRANSFORMERS_HOME=/opt/models/sentence_transformers" in runtime
    assert "${PORT:-8000}" in runtime


def test_tests_are_not_shipped_in_the_image():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf8").splitlines()
    assert "backend/tests" in ignore and "frontend" in ignore
