"""Append-only audit log and OTP challenges."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import utcnow


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    sanitized_description: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)

    actor = relationship("User")


class AuditLogImmutableError(RuntimeError):
    pass


@event.listens_for(AuditLog, "before_update")
def _block_update(*_args):  # pragma: no cover - defensive
    raise AuditLogImmutableError("Audit log records are append-only")


@event.listens_for(AuditLog, "before_delete")
def _block_delete(*_args):  # pragma: no cover - defensive
    raise AuditLogImmutableError("Audit log records are append-only")


class OtpChallenge(db.Model):
    __tablename__ = "otp_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="login")
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
