"""Structured logging with sensitive-value redaction.

Request bodies are never logged. As defence in depth, a filter also redacts
any log field whose name looks sensitive.
"""

from __future__ import annotations

import json
import logging
import re
import time

from flask import Flask, g, has_request_context, request

SENSITIVE_KEYS = re.compile(r"pass(word)?|otp|code|secret|token|voter_?id|nin|candidate|ballot|choice|key", re.I)
_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for attr in list(record.__dict__):
            if attr not in _STD_ATTRS and SENSITIVE_KEYS.search(attr):
                setattr(record, attr, "[REDACTED]")
        if has_request_context():
            record.request_id = g.get("request_id", "-")
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for attr, value in record.__dict__.items():
            if attr not in _STD_ATTRS and not attr.startswith("_"):
                payload[attr] = value
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} {record.name}: {record.getMessage()}"
        extras = {k: v for k, v in record.__dict__.items() if k not in _STD_ATTRS and not k.startswith("_")}
        if extras:
            base += " " + " ".join(f"{k}={v}" for k, v in extras.items())
        if record.exc_info and record.exc_info[0]:
            base += f" exc_type={record.exc_info[0].__name__}"
        return base


def configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if app.config.get("LOG_JSON") else TextFormatter())
    handler.addFilter(RedactingFilter())
    root = logging.getLogger("app")
    root.handlers = [handler]
    root.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    root.propagate = True  # lets pytest's caplog observe records
    for existing in root.handlers:
        existing.addFilter(RedactingFilter())

    access = logging.getLogger("app.access")

    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()

    @app.after_request
    def _access_log(response):
        if not request.path.startswith("/static/"):
            access.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - g.get("_t0", time.perf_counter())) * 1000, 1),
                },
            )
        return response
