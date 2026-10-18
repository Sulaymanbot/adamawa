"""Versioned JSON API (/api/v1)."""

from flask import Blueprint, current_app, g, request

from app.errors import APIError

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


def rate(name: str):
    """Rate-limit value resolved from config at request time."""
    return lambda: current_app.config[name]


def user_or_ip() -> str:
    user = g.get("user")
    return f"user:{user.id}" if user is not None else f"ip:{request.remote_addr}"


def int_arg(name: str, default: int | None = None, *, minimum: int = 1, maximum: int = 2**31 - 1) -> int | None:
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise APIError(
            422, "validation_error", "Some fields are invalid.", [{"field": name, "message": "Must be a whole number"}]
        ) from None
    if not minimum <= value <= maximum:
        raise APIError(422, "validation_error", "Some fields are invalid.", [{"field": name, "message": "Out of range"}])
    return value


def page_meta(pagination) -> dict:
    return {"page": pagination.page, "per_page": pagination.per_page, "total": pagination.total, "pages": pagination.pages}


from app.api import admin, auth, docs, elections, locations, me  # noqa: E402,F401
