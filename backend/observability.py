"""Request IDs, timing logs, slow-request warnings and in-memory request metrics.

Every HTTP request gets an id (the caller's X-Request-ID if it is a sane token,
else a new one) that is returned in the X-Request-ID header and written on its
log line:

    request id=3f2a… method=GET path=/progress status=200 ms=84 role=student

Logged: method, path (never the query string — it can hold emails or search
text), status, duration, the caller's role. Never logged: user ids, emails,
tokens, bodies. A request slower than SLOW_REQUEST_MS (default 2000) is a WARNING
naming the endpoint; for streamed responses (the doubt SSE) the time to the first
byte is what counts, since the stream is long on purpose.

The last METRICS_SIZE requests are kept in memory (per process) for the admin
System health card: counts, 5xx errors and slow requests in the last hour, p50/p95.
"""

import logging
import os
import re
import statistics
import threading
import time
import uuid
from collections import deque

log = logging.getLogger("smartcoaching.request")

METRICS_SIZE = 2000
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_metrics: deque = deque(maxlen=METRICS_SIZE)  # (monotonic ts, route, status, ms, slow)
_metrics_lock = threading.Lock()
STARTED_AT = time.time()


def setup_logging() -> None:
    """INFO-level lines to stdout (Railway's log view), unless logging is already set up."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    elif root.level > logging.INFO:
        root.setLevel(logging.INFO)


def _slow_ms() -> float:
    return float(os.getenv("SLOW_REQUEST_MS", "2000"))


def _route_of(scope) -> str:
    """The route template (/jobs/{job_id}) when the router matched one, else the path."""
    route = scope.get("route")
    return getattr(route, "path", None) or scope.get("path", "")


class RequestLogMiddleware:
    """Pure ASGI middleware, so a streamed response is timed until its last byte."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        t0 = time.perf_counter()
        info = {"status": 500, "ttfb": None, "streaming": False}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                info["status"] = message["status"]
                info["ttfb"] = time.perf_counter() - t0
                headers = list(message.get("headers") or [])
                ctype = dict(headers).get(b"content-type", b"")
                info["streaming"] = ctype.startswith(b"text/event-stream")
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            ms = (time.perf_counter() - t0) * 1000
            ttfb_ms = (info["ttfb"] or 0) * 1000
            route = _route_of(scope)
            role = (scope.get("state") or {}).get("role") or "-"
            judged = ttfb_ms if info["streaming"] else ms
            slow = judged > _slow_ms()
            line = (f"request id={request_id} method={scope.get('method')} path={route} "
                    f"status={info['status']} ms={ms:.0f}"
                    + (f" ttfb_ms={ttfb_ms:.0f}" if info["streaming"] else "")
                    + f" role={role}")
            if slow:
                log.warning("SLOW %s (> %.0f ms) %s", route, _slow_ms(), line)
            else:
                log.info(line)
            with _metrics_lock:
                _metrics.append((time.monotonic(), route, info["status"], judged, slow))


def summary(window_s: float = 3600) -> dict:
    """Requests in the last window_s seconds (this process): count, 5xx errors, slow
    ones, p50/p95 ms, and the slowest routes."""
    cutoff = time.monotonic() - window_s
    with _metrics_lock:
        rows = [r for r in _metrics if r[0] >= cutoff]
    times = sorted(r[3] for r in rows)

    def pct(p):
        return round(times[min(len(times) - 1, int(p / 100 * len(times)))]) if times else None

    by_route: dict[str, list[float]] = {}
    for r in rows:
        by_route.setdefault(r[1], []).append(r[3])
    slowest = sorted(((route, round(statistics.median(v)), len(v)) for route, v in by_route.items()),
                     key=lambda x: -x[1])[:5]
    return {
        "window_s": window_s,
        "requests": len(rows),
        "errors_5xx": sum(1 for r in rows if r[2] >= 500),
        "slow": sum(1 for r in rows if r[4]),
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "slowest_routes": [{"route": r, "p50_ms": m, "count": c} for r, m, c in slowest],
    }


def reset() -> None:
    with _metrics_lock:
        _metrics.clear()
