"""Per-institute RAG_SERVER config — which tenant + API key an institute uses.

Each institute is one RAG_SERVER tenant. The tenant slug lives on
institutes.rag_tenant; the tenant-scoped API key lives in institute_secrets,
a table with RLS enabled and no policies, so only the backend's service-role
client can read it (institutes itself has no RLS, so the key can't live there).

An institute uses its own tenant + key only when BOTH are set. Otherwise (no
institute, a half-configured row, or the lookup failed) it falls back to the
RAG_SERVER_TENANT / RAG_SERVER_API_KEY env vars — the single-institute default.

Results are cached for CACHE_SECONDS. The API key is never logged.
"""

import os
import threading
import time
import uuid

CACHE_SECONDS = 300          # a looked-up config is reused for 5 minutes
ERROR_CACHE_SECONDS = 60     # a failed lookup is retried after 1 minute

_cache: dict[str, tuple[float, tuple[str, str]]] = {}
_lock = threading.Lock()


def _supabase():
    from auth.supabase_auth import get_supabase
    return get_supabase()


def _env_config() -> tuple[str, str]:
    return (os.getenv("RAG_SERVER_TENANT") or "smartcoaching",
            os.getenv("RAG_SERVER_API_KEY", ""))


def _as_uuid(value) -> str | None:
    try:
        return str(uuid.UUID(str(value))) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _load(institute_id: str) -> tuple[tuple[str, str], bool]:
    """Read the institute's tenant + key. Returns ((tenant, api_key), ok)."""
    try:
        sb = _supabase()
        inst = (sb.table("institutes").select("rag_tenant")
                .eq("id", institute_id).limit(1).execute().data) or []
        secret = (sb.table("institute_secrets").select("rag_api_key")
                  .eq("institute_id", institute_id).limit(1).execute().data) or []
    except Exception as e:
        print(f"[rag_config] lookup failed for institute {institute_id}, using env default: {e}")
        return _env_config(), False

    tenant = ((inst[0].get("rag_tenant") if inst else None) or "").strip()
    api_key = ((secret[0].get("rag_api_key") if secret else None) or "").strip()
    if tenant and api_key:
        return (tenant, api_key), True
    if tenant or api_key:
        print(f"[rag_config] institute {institute_id} has only one of rag_tenant / "
              "rag_api_key set; using env default")
    return _env_config(), True


def get_rag_config(institute_id: str | None) -> tuple[str, str]:
    """Return (tenant, api_key) for an institute, falling back to the env defaults.

    api_key may be "" when nothing is configured; rag_server_client then reports
    itself as disabled and every call fails soft.
    """
    iid = _as_uuid(institute_id)
    if not iid:
        return _env_config()

    now = time.monotonic()
    with _lock:
        hit = _cache.get(iid)
        if hit and hit[0] > now:
            return hit[1]

    config, ok = _load(iid)
    ttl = CACHE_SECONDS if ok else ERROR_CACHE_SECONDS
    with _lock:
        _cache[iid] = (now + ttl, config)
    return config


def clear_cache() -> None:
    """Forget cached configs (e.g. right after an institute's key is changed)."""
    with _lock:
        _cache.clear()
