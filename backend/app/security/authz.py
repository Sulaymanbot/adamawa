"""Role-based access control.

Permissions are mapped to roles in one place so new roles (e.g. a read-only
`auditor`) can be added without touching route code.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, g, redirect, request, url_for

from app.errors import APIError

PERMISSIONS: dict[str, frozenset[str]] = {
    "ballot.cast": frozenset({"voter"}),
    "voter.self": frozenset({"voter"}),
    "admin.dashboard": frozenset({"admin", "super_admin", "auditor"}),
    "voters.read": frozenset({"admin", "super_admin"}),
    "voters.verify": frozenset({"admin", "super_admin"}),
    "elections.manage": frozenset({"admin", "super_admin"}),
    "candidates.manage": frozenset({"admin", "super_admin"}),
    "results.publish": frozenset({"admin", "super_admin"}),
    "audit.read": frozenset({"admin", "super_admin", "auditor"}),
}


def has_permission(user, permission: str) -> bool:
    if user is None or user.status != "active":
        return False
    return user.role in PERMISSIONS.get(permission, frozenset())


def _record_denied(permission: str) -> None:
    from app.services import audit_service

    audit_service.record(
        "security.permission_denied",
        description=f"Denied '{permission}' on {request.method} {request.path}",
    )


def api_auth(permission: str | None = None):
    """Decorator for JSON API endpoints."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.get("user") is None:
                if g.get("session_expired"):
                    raise APIError(401, "session_expired", "Your session has expired. Please sign in again.")
                raise APIError(401, "unauthenticated", "Please sign in to continue.")
            if permission and not has_permission(g.user, permission):
                _record_denied(permission)
                raise APIError(403, "forbidden", "You do not have permission to perform this action.")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def page_auth(permission: str, login_endpoint: str = "web.login"):
    """Decorator for server-rendered pages: redirect to login or show 403."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.get("user") is None:
                return redirect(url_for(login_endpoint, next=request.path))
            if not has_permission(g.user, permission):
                _record_denied(permission)
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
