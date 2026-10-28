"""Security headers, request ids and an origin allow-list for CORS."""

from __future__ import annotations

import re
import uuid

from flask import Flask, current_app, g, request

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def assign_request_id() -> None:
    incoming = request.headers.get("X-Request-ID", "")
    g.request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex


def apply_security_headers(response):
    response.headers["X-Request-ID"] = g.get("request_id", "")
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # HTTPS CSRF checks require Referer on same-origin requests.
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if current_app.config.get("ENABLE_HSTS"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if not request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"

    origin = request.headers.get("Origin")
    if origin and origin in current_app.config.get("CORS_ORIGINS", []):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken, Idempotency-Key"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def init_security(app: Flask) -> None:
    app.before_request(assign_request_id)
    app.after_request(apply_security_headers)
