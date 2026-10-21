"""Run independent slow calls (LLM, RAG) side by side, a few at a time.

LLM_CONCURRENCY (default 3) caps how many run at once, so a burst of work stays
inside the free tiers' rate limits.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def llm_concurrency() -> int:
    return max(1, int(os.getenv("LLM_CONCURRENCY", "3")))


def parallel_map(fn: Callable[[T], R], items: Iterable[T], limit: int | None = None) -> list[R]:
    """[fn(x) for x in items], up to `limit` at a time; results keep the input order.
    An exception from fn is raised, as the plain loop would."""
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=min(limit or llm_concurrency(), len(items))) as pool:
        return list(pool.map(fn, items))


def for_each(items: Iterable[T], fn: Callable[[T], R], label: str = "job",
             batch_size: int = 50, limit: int | None = None) -> list:
    """fn(item) for every item, in batches of batch_size, `limit` at a time.
    One item failing is logged and gives None; the rest carry on."""
    items = list(items)

    def safe(x):
        try:
            return fn(x)
        except Exception as e:
            ident = x.get("id") if isinstance(x, dict) else x
            print(f"[{label}] failed for {ident}: {e}")
            return None

    out: list = []
    for i in range(0, len(items), batch_size):
        out += parallel_map(safe, items[i:i + batch_size], limit=limit)
    return out
