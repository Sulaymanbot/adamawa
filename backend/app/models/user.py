"""Users, administrator profiles and server-side sessions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, in_check, utcnow

ROLES = ("voter", "admin", "super_admin", "auditor")
ADMIN_ROLES = ("admin", "super_admin")
USER_STATUSES = ("active", "suspended", "disabled")


class User(TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(in_check("role", ROLES), name="role_valid"),
        CheckConstraint(in_check("status", USER_STATUSES), name="status_valid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="voter", index=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    voter = relationship("Voter", back_populates="user", uselist=False, foreign_keys="Voter.user_id")
    admin_profile = relationship("Admin", back_populates="user", uselist=False)

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES

    @property
    def display_name(self) -> str:
        if self.voter is not None:
            return f"{self.voter.first_name} {self.voter.surname}"
        if self.admin_profile is not None:
            return self.admin_profile.full_name
        return "User"


class Admin(TimestampMixin, db.Model):
    """Administrator profile (Chapter 3 'Administrator' entity), linked to a user."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    user = relationship("User", back_populates="admin_profile")


class UserSession(db.Model):
    """Server-side session record so logout / expiry can be enforced centrally."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    user = relationship("User")
