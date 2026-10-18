"""Voter profile (Chapter 3 'Voter' entity)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, in_check

VERIFICATION_STATUSES = ("pending", "verified", "rejected", "suspended")


class Voter(TimestampMixin, db.Model):
    __tablename__ = "voters"
    __table_args__ = (CheckConstraint(in_check("verification_status", VERIFICATION_STATUSES), name="verification_status_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    # The simulated voter identification number is never stored in plaintext:
    # only a keyed HMAC (for uniqueness/lookup) and the last 4 chars (for masking).
    voter_id_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    voter_id_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    surname: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(120))
    lga_id: Mapped[int] = mapped_column(ForeignKey("local_government_areas.id"), nullable=False, index=True)
    ward_id: Mapped[int] = mapped_column(ForeignKey("wards.id"), nullable=False, index=True)
    polling_unit_id: Mapped[int] = mapped_column(ForeignKey("polling_units.id"), nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    verification_reason: Mapped[str | None] = mapped_column(String(300))
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    user = relationship("User", back_populates="voter", foreign_keys=[user_id])
    lga = relationship("LocalGovernmentArea")
    ward = relationship("Ward")
    polling_unit = relationship("PollingUnit")

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.other_names or "", self.surname]
        return " ".join(p for p in parts if p)
