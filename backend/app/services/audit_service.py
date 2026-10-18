"""Audit logging (append-only, sanitised)."""

from __future__ import annotations

import logging
import re

from flask import g, has_request_context, request

from app.extensions import db
from app.models import AuditLog
from app.security.identifiers import hash_ip

log = logging.getLogger("app.audit")

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL = re.compile(r"([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9])[A-Za-z0-9.\-]*")
_LONG_DIGITS = re.compile(r"\d{7,}")


def sanitize(text: str) -> str:
    text = _CONTROL.sub(" ", text)
    text = _EMAIL.sub(r"\1***@\2***", text)
    text = _LONG_DIGITS.sub("[number]", text)
    return text.strip()[:500]


def record(
    event_type: str,
    description: str,
    *,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    commit: bool = True,
) -> AuditLog:
    if actor_user_id is None and has_request_context() and g.get("user") is not None:
        actor_user_id = g.user.id
    entry = AuditLog(
        actor_user_id=actor_user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        sanitized_description=sanitize(description),
        request_id=g.get("request_id") if has_request_context() else None,
        ip_hash=hash_ip(request.remote_addr) if has_request_context() else None,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    log.info("audit", extra={"event_type": event_type, "entity": entity_type})
    return entry


def serialize(entry: AuditLog) -> dict:
    return {
        "id": entry.id,
        "event_type": entry.event_type,
        "actor_user_id": entry.actor_user_id,
        "actor_role": entry.actor.role if entry.actor else None,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "description": entry.sanitized_description,
        "request_id": entry.request_id,
        "ip_hash": entry.ip_hash,
        "created_at": iso(entry.created_at),
    }


def iso(value) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None


def list_logs(*, event_type=None, actor_user_id=None, entity_type=None, date_from=None, date_to=None, page=1, per_page=25):
    query = db.select(AuditLog)
    if event_type:
        literal = event_type.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(AuditLog.event_type.like(f"{literal}%", escape="\\"))
    if actor_user_id:
        query = query.where(AuditLog.actor_user_id == actor_user_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if date_from:
        query = query.where(AuditLog.created_at >= date_from)
    if date_to:
        query = query.where(AuditLog.created_at <= date_to)
    query = query.order_by(AuditLog.id.desc())
    return db.paginate(query, page=page, per_page=per_page, max_per_page=100, error_out=False)
