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
