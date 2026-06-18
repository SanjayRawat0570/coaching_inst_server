"""Supabase Auth — FastAPI dependencies. No MongoDB, no Firebase.

Verifies the Supabase-issued JWT on every request and exposes:
  - get_current_user  : returns the decoded Supabase user (raises 401 if invalid)
  - require_role(...)  : dependency factory that also enforces a role
  - get_current_student_id : convenience — resolves the students.id row for the caller
"""

import os
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client

bearer_scheme = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Single Supabase client reused across requests.

    Uses the service-role key when available so server-side reads/writes bypass
    Row Level Security (RLS checks auth.uid(), which is null for a keyed backend
    call — without the service key every insert/select on an RLS table would fail).
    Falls back to the anon key for local experiments. The user's own JWT is still
    validated separately in get_current_user.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_KEY) must be set"
        )
    return create_client(url, key)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """Validate the bearer JWT against Supabase Auth and return the user object.

    Returns a dict: {id, email, role, name, institute_id, raw}
    Raises 401 on any failure.
    """
    token = credentials.credentials
    try:
        supabase = get_supabase()
        result = supabase.auth.get_user(token)
        user = result.user
        if user is None:
            raise ValueError("No user for token")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    metadata = user.user_metadata or {}
    return {
        "id": user.id,
        "email": user.email,
        "role": metadata.get("role"),
        "name": metadata.get("name"),
        "institute_id": metadata.get("institute_id"),
        "parent_email": metadata.get("parent_email"),
        "raw": user,
    }


def require_role(*allowed_roles: str):
    """Dependency factory — enforce that the caller has one of the allowed roles.

    Usage:
        @app.get("/teacher/alerts")
        def alerts(user=Depends(require_role("teacher", "admin"))):
            ...
    """

    def _checker(user=Depends(get_current_user)):
        role = user.get("role")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(allowed_roles)} (you are '{role}')",
            )
        return user

    return _checker


def get_current_student_id(user=Depends(get_current_user)) -> str:
    """Resolve the students.id row for the authenticated auth user.

    Raises 404 if no student row is linked to this auth_id.
    """
    supabase = get_supabase()
    res = (
        supabase.table("students")
        .select("id")
        .eq("auth_id", user["id"])
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No student profile linked to this account",
        )
    return rows[0]["id"]
