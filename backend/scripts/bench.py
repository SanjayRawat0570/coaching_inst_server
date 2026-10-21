"""Latency + round-trip benchmark for the hot endpoints.

Two modes:

  In-process (default) — imports the FastAPI app and calls it with TestClient as
  real accounts of each role (auth is overridden, so no passwords are needed).
  Every outbound HTTP call (Supabase, LLM, RAG_SERVER) is counted per request.
    python -m scripts.bench --runs 10
    python -m scripts.bench --runs 10 --include-writes   # also LLM / DB-writing endpoints

  HTTP — times a running backend end-to-end, including token verification.
  Tokens are Supabase access tokens (copy from the browser's session).
    python -m scripts.bench --base-url https://<backend> \
        --token student=eyJ... --token teacher=eyJ... --token admin=eyJ... --token parent=eyJ...

Accounts for in-process mode: BENCH_STUDENT_EMAIL / BENCH_TEACHER_EMAIL /
BENCH_PARENT_EMAIL / BENCH_ADMIN_EMAIL, else the first auth account of each role.

Read-only endpoints run by default. --include-writes adds /doubt/stream,
/test/generate and /test/submit (--test-id): they write rows and spend LLM quota.
Prints timings and counts only, never response data. Run from backend/.
"""

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROLES = ("student", "teacher", "parent", "admin")


def _pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return s[k]


# ── outbound call counter ─────────────────────────────────────────────────────
_calls: Counter = Counter()


def _install_counter():
    """Count every httpx request by host (supabase-py, LLM SDKs and the RAG_SERVER
    connector all go through httpx)."""
    import httpx

    def wrap(send):
        def counted(self, request, *a, **kw):
            _calls[_label(request.url.host)] += 1
            return send(self, request, *a, **kw)
        return counted

    def wrap_async(send):
        async def counted(self, request, *a, **kw):
            _calls[_label(request.url.host)] += 1
            return await send(self, request, *a, **kw)
        return counted

    httpx.Client.send = wrap(httpx.Client.send)
    httpx.AsyncClient.send = wrap_async(httpx.AsyncClient.send)


def _label(host: str) -> str:
    if host in ("testserver",):
        return "app"
    sb = urlparse(os.getenv("SUPABASE_URL") or "").hostname
    rag = urlparse(os.getenv("RAG_SERVER_URL") or "").hostname
    if host == sb:
        return "supabase"
    if rag and host == rag:
        return "rag_server"
    if "groq" in host or "googleapis" in host or "openrouter" in host:
        return "llm"
    return host


# ── endpoint list ─────────────────────────────────────────────────────────────
def _endpoints(users, include_writes, test_id):
    teacher_inst = (users.get("teacher") or {}).get("institute_id") or ""
    student_email = (users.get("student") or {}).get("email") or ""
    eps = [
        ("GET", "/health", None, None),
        ("GET", "/progress", "student", None),
        ("GET", "/leaderboard", "student", None),
        ("GET", "/flashcards/due", "student", None),
        ("GET", f"/teacher/overview?institute_id={teacher_inst}", "teacher", None),
        ("GET", f"/teacher/students?institute_id={teacher_inst}", "teacher", None),
        ("GET", f"/teacher/alerts?institute_id={teacher_inst}", "teacher", None),
        ("GET", "/admin/analytics", "admin", None),
        ("GET", "/parent/report", "parent", None),
    ]
    if include_writes:
        eps += [
            ("STREAM", "/doubt/stream", "student",
             {"question": "What is Newton's second law of motion?", "subject": "Physics"}),
            ("POST", "/test/generate", "teacher",
             {"student_id": student_email, "institute_id": teacher_inst, "num_questions": 5}),
        ]
        if test_id:
            eps.append(("POST", "/test/submit", "student", {"test_id": test_id, "answers": []}))
    return eps


# ── accounts (in-process mode) ────────────────────────────────────────────────
def _load_users():
    from auth.supabase_auth import get_supabase
    sb = get_supabase()
    res = sb.auth.admin.list_users()
    accounts = res if isinstance(res, list) else getattr(res, "users", []) or []
    users = {}
    for role in ROLES:
        want = (os.getenv(f"BENCH_{role.upper()}_EMAIL") or "").strip().lower()
        for u in accounts:
            meta = u.user_metadata or {}
            if (want and (u.email or "").lower() == want) or (
                    not want and (meta.get("role") or "student") == role):
                users[role] = {"id": u.id, "email": u.email, "role": meta.get("role") or "student",
                               "name": meta.get("name"), "institute_id": meta.get("institute_id"),
                               "parent_email": meta.get("parent_email"), "raw": u}
                break
    return users


# ── runners ───────────────────────────────────────────────────────────────────
def _run_inproc(args):
    _install_counter()
    from fastapi.testclient import TestClient
    import main
    from auth.supabase_auth import get_current_user

    users = _load_users()
    print("accounts:", {r: bool(users.get(r)) for r in ROLES})
    current = {"user": None}
    main.app.dependency_overrides[get_current_user] = lambda: current["user"]
    client = TestClient(main.app)

    def call(method, path, role, body):
        current["user"] = users.get(role) if role else None
        if method == "GET":
            return client.get(path), None
        if method == "POST":
            return client.post(path, json=body), None
        t0 = time.perf_counter()
        ttft = None
        with client.stream("POST", path, json=body) as r:
            for line in r.iter_lines():
                if ttft is None and line.startswith("data: ") and not line.startswith("data: [STATUS]"):
                    ttft = (time.perf_counter() - t0) * 1000
        return r, ttft

    return _bench(args, _endpoints(users, args.include_writes, args.test_id), call,
                  skip=lambda role: role and not users.get(role), auth_cost=_auth_cost())


def _run_http(args):
    _install_counter()
    import httpx
    tokens = dict(t.split("=", 1) for t in args.token)
    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180)

    def call(method, path, role, body):
        h = {"Authorization": f"Bearer {tokens[role]}"} if role else {}
        if method == "GET":
            return client.get(path, headers=h), None
        if method == "POST":
            return client.post(path, json=body, headers=h), None
        t0 = time.perf_counter()
        ttft = None
        with client.stream("POST", path, json=body, headers=h) as r:
            for line in r.iter_lines():
                if ttft is None and line.startswith("data: ") and not line.startswith("data: [STATUS]"):
                    ttft = (time.perf_counter() - t0) * 1000
        return r, ttft

    # Institute ids for teacher routes aren't known here; they fall back to unscoped.
    users = {r: {} for r in tokens}
    return _bench(args, _endpoints(users, args.include_writes, args.test_id), call,
                  skip=lambda role: role and role not in tokens, auth_cost=None)


def _auth_cost():
    """One token-verification round trip (what every real request pays first)."""
    from auth.supabase_auth import get_supabase
    sb = get_supabase()
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        try:
            sb.auth.get_user("invalid.token.for-timing")
        except Exception:
            pass
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.median(times)


def _bench(args, endpoints, call, skip, auth_cost):
    rows = []
    for method, path, role, body in endpoints:
        if skip(role):
            rows.append({"endpoint": path.split("?")[0], "skipped": f"no {role} account/token"})
            continue
        runs = 1 if method != "GET" else args.runs  # writes/LLM: one run each
        times, ttfts, statuses, per_call = [], [], Counter(), []
        cold = None
        for i in range(runs + (1 if method == "GET" else 0)):
            _calls.clear()
            t0 = time.perf_counter()
            try:
                r, ttft = call(method, path, role, body)
                statuses[r.status_code] += 1
            except Exception as e:
                statuses[type(e).__name__] += 1
                ttft = None
            ms = (time.perf_counter() - t0) * 1000
            if method == "GET" and i == 0:
                cold = ms  # first call: imports, client creation, caches
                continue
            times.append(ms)
            if ttft is not None:
                ttfts.append(ttft)
            per_call.append(dict(_calls))
        out_calls = {}
        for c in per_call:
            for k, v in c.items():
                if k != "app":
                    out_calls[k] = max(out_calls.get(k, 0), v)
        rows.append({
            "endpoint": path.split("?")[0], "role": role or "-", "runs": len(times),
            "cold_ms": round(cold) if cold else None,
            "p50_ms": round(_pct(times, 50)) if times else None,
            "p95_ms": round(_pct(times, 95)) if times else None,
            "ttft_ms": round(statistics.median(ttfts)) if ttfts else None,
            "calls": out_calls, "status": dict(statuses),
        })

    print(f"\n{'endpoint':28} {'role':8} {'cold':>7} {'p50':>7} {'p95':>7} {'ttft':>7}  calls/request         status")
    for r in rows:
        if "skipped" in r:
            print(f"{r['endpoint']:28} skipped ({r['skipped']})")
            continue
        calls = ", ".join(f"{k} {v}" for k, v in sorted(r["calls"].items())) or "-"
        f = lambda v: "-" if v is None else str(v)  # noqa: E731
        print(f"{r['endpoint']:28} {r['role']:8} {f(r['cold_ms']):>7} {f(r['p50_ms']):>7} "
              f"{f(r['p95_ms']):>7} {f(r['ttft_ms']):>7}  {calls:20}  {r['status']}")
    if auth_cost is not None:
        print(f"\nIn-process mode skips token verification; a real request adds "
              f"~{auth_cost:.0f} ms (Supabase auth.get_user round trip).")
    if args.json:
        with open(args.json, "w", encoding="utf8") as fh:
            json.dump({"rows": rows, "auth_ms": auth_cost}, fh, indent=2)
        print("saved", args.json)
    return rows


def main():
    from dotenv import load_dotenv
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--base-url", help="HTTP mode: a running backend")
    p.add_argument("--token", action="append", default=[], help="role=access_token (HTTP mode)")
    p.add_argument("--include-writes", action="store_true",
                   help="also /doubt/stream, /test/generate, /test/submit (writes rows, uses LLM quota)")
    p.add_argument("--test-id", help="a test the student account may submit (with --include-writes)")
    p.add_argument("--truststore", action="store_true",
                   help="use the OS certificate store (networks with TLS interception)")
    p.add_argument("--json", help="also save the results to this file")
    args = p.parse_args()
    if args.truststore:
        import truststore
        truststore.inject_into_ssl()
    if args.base_url:
        _run_http(args)
    else:
        # TestClient is used without its context manager, so the app's lifespan
        # (and with it the scheduler) never starts during a benchmark.
        _run_inproc(args)


if __name__ == "__main__":
    main()
