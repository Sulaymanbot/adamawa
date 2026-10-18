"""Consistent JSON envelopes and error handling.

Success: {"ok": true,  "data": ..., "meta": {...}, "request_id": "..."}
Error:   {"ok": false, "error": {"code", "message", "details"}, "request_id": "..."}
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from flask import Flask, g, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger("app.errors")


class APIError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []


def ok(data: Any = None, status: int = 200, meta: dict | None = None):
    body: dict[str, Any] = {"ok": True, "data": data, "request_id": g.get("request_id")}
    if meta:
        body["meta"] = meta
    return jsonify(body), status


def error_response(status: int, code: str, message: str, details=None):
    body = {
        "ok": False,
        "error": {"code": code, "message": message, "details": details or []},
        "request_id": g.get("request_id"),
    }
    return jsonify(body), status


def pydantic_details(exc: ValidationError) -> list[dict[str, str]]:
    details = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err.get("loc", ())) or "body"
        msg = err.get("msg", "Invalid value")
        # pydantic prefixes custom ValueError messages with "Value error, "
        msg = msg.removeprefix("Value error, ")
        details.append({"field": field, "message": msg})
    return details


def _wants_json() -> bool:
    return request.path.startswith("/api/")


_HTTP_CODES = {
    400: ("bad_request", "The request could not be processed."),
    401: ("unauthenticated", "Please sign in to continue."),
    403: ("forbidden", "You do not have permission to perform this action."),
    404: ("not_found", "The requested resource was not found."),
    405: ("method_not_allowed", "This method is not allowed for this resource."),
    409: ("conflict", "The request conflicts with the current state."),
    413: ("payload_too_large", "The request is too large."),
    415: ("unsupported_media_type", "Requests must be sent as JSON."),
    422: ("validation_error", "Some fields are invalid."),
    429: ("rate_limited", "Too many requests. Please wait a moment and try again."),
}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(exc: APIError):
        if _wants_json():
            return error_response(exc.status, exc.code, exc.message, exc.details)
        return _render_error_page(exc.status, exc.message)

    @app.errorhandler(ValidationError)
    def handle_validation(exc: ValidationError):
        return error_response(422, "validation_error", "Some fields are invalid.", pydantic_details(exc))

    @app.errorhandler(CSRFError)
    def handle_csrf(exc: CSRFError):
        from app.services import audit_service

        audit_service.record("security.csrf_rejected", description=f"CSRF check failed on {request.path}")
        if _wants_json():
            return error_response(
                400, "csrf_failed", "Your session security token is missing or expired. Refresh the page and try again."
            )
        return _render_error_page(400, "Your session security token expired. Please go back and try again.")

    @app.errorhandler(429)
    def handle_rate_limit(exc):
        from app.services import audit_service

        audit_service.record("security.rate_limited", description=f"Rate limit hit on {request.path}")
        code, message = _HTTP_CODES[429]
        if _wants_json():
            return error_response(429, code, message)
        return _render_error_page(429, message)

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        status = exc.code or 500
        code, message = _HTTP_CODES.get(status, ("http_error", "The request could not be completed."))
        if _wants_json():
            return error_response(status, code, message)
        return _render_error_page(status, message)

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        # Log the exception type and request id only: never request bodies.
        log.exception("unhandled_error", extra={"error_type": type(exc).__name__})
        from app.extensions import db

        # Best effort: the session may itself be unusable at this point.
        with contextlib.suppress(Exception):
            db.session.rollback()
        message = "Something went wrong on our side. No changes were saved."
        if _wants_json():
            return error_response(500, "server_error", message)
        return _render_error_page(500, message)


def _render_error_page(status: int, message: str):
    template = {403: "errors/403.html", 404: "errors/404.html"}.get(status, "errors/error.html")
    return render_template(template, status=status, message=message), status
