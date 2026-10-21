"""Small load test: N concurrent students using the app, no extra dependencies.

Each virtual student loops over the student pages' requests (progress,
leaderboard, flashcards due, concept map, study plan) with a short random think
time, for --seconds. Reports per endpoint and overall: requests, p50 / p95 ms and
error rate. Read-only by default.

  In-process (default): the app runs inside this script, as the real account(s)
  BENCH_STUDENT_EMAIL (else the first student account) — token checks skipped,
  every other part real (Supabase, caches, threadpool).
    python -m scripts.loadtest --users 50 --seconds 30 --truststore

  HTTP: a running backend, one access token reused by every virtual student.
    python -m scripts.loadtest --base-url http://localhost:8000 --token eyJ... --users 50

  --doubts adds a doubt every few loops (writes doubt_logs rows). It refuses to run
  unless RAG_SERVER_URL points at localhost: never load-test the live RAG_SERVER.

Run from backend/. Prints numbers only, never response data.
"""

import argparse
import asyncio
import os
import random
import sys
import time
from collections import defaultdict
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

READS = ["/progress", "/leaderboard", "/flashcards/due", "/student/concept-map", "/student/plan"]


def _pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(p / 100 * len(s)))]


def _check_doubts_allowed():
    host = urlparse(os.getenv("RAG_SERVER_URL") or "").hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("--doubts needs RAG_SERVER_URL pointing at a local RAG_SERVER copy "
                         f"(got host {host or 'none'!r}). Never load-test the live RAG_SERVER.")


async def _user(i, client, headers, deadline, think, doubts, results, sem_start):
    await asyncio.sleep(random.uniform(0, sem_start))  # ramp up instead of a thundering start
    loop_n = 0
    while time.monotonic() < deadline:
        loop_n += 1
        for path in READS:
            if time.monotonic() >= deadline:
                return
            t0 = time.perf_counter()
            try:
                r = await client.get(path, headers=headers)
                ok = r.status_code < 500
                code = r.status_code
            except Exception as e:  # noqa: BLE001
                ok, code = False, type(e).__name__
            results[path].append(((time.perf_counter() - t0) * 1000, ok, code))
            await asyncio.sleep(random.uniform(think * 0.5, think * 1.5))
        if doubts and loop_n % 3 == 0:
            t0 = time.perf_counter()
            try:
                async with client.stream("POST", "/doubt/stream", headers=headers,
                                         json={"question": f"Load test question {i}-{loop_n}"}) as r:
                    async for _ in r.aiter_lines():
                        pass
                ok, code = r.status_code < 500, r.status_code
            except Exception as e:  # noqa: BLE001
                ok, code = False, type(e).__name__
            results["/doubt/stream"].append(((time.perf_counter() - t0) * 1000, ok, code))


async def _run(args):
    import httpx

    if args.base_url:
        client = httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=120)
        headers = {"Authorization": f"Bearer {args.token}"}
        mode = f"HTTP {args.base_url}"
    else:
        import main
        from auth.supabase_auth import get_current_user
        from scripts.bench import _load_users
        student = _load_users().get("student")
        if not student:
            raise SystemExit("No student account found (set BENCH_STUDENT_EMAIL).")
        main.app.dependency_overrides[get_current_user] = lambda: student
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                   base_url="http://app", timeout=120)
        headers = {}
        mode = "in-process (token check skipped)"

    results = defaultdict(list)
    deadline = time.monotonic() + args.seconds
    t0 = time.perf_counter()
    async with client:
        await asyncio.gather(*(_user(i, client, headers, deadline, args.think, args.doubts,
                                     results, min(5.0, args.seconds / 4))
                               for i in range(args.users)))
    wall = time.perf_counter() - t0

    print(f"\n{args.users} concurrent students, {args.seconds}s, think ~{args.think}s, {mode}")
    print(f"{'endpoint':24} {'requests':>8} {'p50 ms':>8} {'p95 ms':>8} {'errors':>7}")
    every = []
    for path in [*READS, "/doubt/stream"]:
        rows = results.get(path)
        if not rows:
            continue
        every += rows
        ms = [r[0] for r in rows]
        err = sum(1 for r in rows if not r[1])
        print(f"{path:24} {len(rows):>8} {_pct(ms, 50):>8.0f} {_pct(ms, 95):>8.0f} {err / len(rows):>6.1%}")
    ms = [r[0] for r in every]
    err = [r[2] for r in every if not r[1]]
    print(f"{'ALL':24} {len(every):>8} {_pct(ms, 50):>8.0f} {_pct(ms, 95):>8.0f} "
          f"{len(err) / max(1, len(every)):>6.1%}   ({len(every) / wall:.1f} req/s)")
    if err:
        kinds = defaultdict(int)
        for e in err:
            kinds[e] += 1
        print("errors:", dict(kinds))


def main():
    from dotenv import load_dotenv
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--users", type=int, default=50)
    p.add_argument("--seconds", type=int, default=30)
    p.add_argument("--think", type=float, default=1.0, help="mean seconds between a user's requests")
    p.add_argument("--base-url")
    p.add_argument("--token", help="access token for HTTP mode")
    p.add_argument("--doubts", action="store_true", help="also ask doubts (local RAG_SERVER only)")
    p.add_argument("--truststore", action="store_true", help="use the OS certificate store")
    args = p.parse_args()
    if args.base_url and not args.token:
        raise SystemExit("--base-url needs --token")
    if args.doubts:
        _check_doubts_allowed()
    if args.truststore:
        import truststore
        truststore.inject_into_ssl()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
