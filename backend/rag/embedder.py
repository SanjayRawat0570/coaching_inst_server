"""Embedding helper — single shared all-MiniLM-L6-v2 model (384-dim, CPU, free)."""

import os
from functools import lru_cache

os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", "/tmp/sentence_transformers")

MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_SIZE = 384


@lru_cache(maxsize=1)
def get_embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def embed(text: str) -> list[float]:
    """Embed a single string."""
    return get_embedder().encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed many strings at once (faster)."""
    return [v.tolist() for v in get_embedder().encode(texts)]
