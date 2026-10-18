"""Elections and candidates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.base import TimestampMixin, in_check

ELECTION_TYPES = ("lg_chairmanship", "councillorship")
ELECTION_SCOPES = ("single_lga", "all_lgas")
ELECTION_STATUSES = ("draft", "scheduled", "open", "closed", "archived", "cancelled")
CANDIDATE_STATUSES = ("active", "inactive")


class Election(TimestampMixin, db.Model):
    __tablename__ = "elections"
    __table_args__ = (
        CheckConstraint(in_check("type", ELECTION_TYPES), name="type_valid"),
        CheckConstraint(in_check("scope", ELECTION_SCOPES), name="scope_valid"),
        CheckConstraint(in_check("status", ELECTION_STATUSES), name="status_valid"),
        CheckConstraint("end_at > start_at", name="window_valid"),
        CheckConstraint(
            "(scope = 'single_lga' AND lga_id IS NOT NULL) OR (scope = 'all_lgas' AND lga_id IS NULL)",
            name="scope_lga_consistent",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False, default="lg_chairmanship")
    description: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="all_lgas")
    lga_id: Mapped[int | None] = mapped_column(ForeignKey("local_government_areas.id"))
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    results_published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    lga = relationship("LocalGovernmentArea")
    candidates = relationship("Candidate", back_populates="election", order_by="Candidate.full_name")


class Candidate(TimestampMixin, db.Model):
    __tablename__ = "candidates"
    __table_args__ = (CheckConstraint(in_check("status", CANDIDATE_STATUSES), name="status_valid"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("elections.id", ondelete="CASCADE"), nullable=False, index=True)
    lga_id: Mapped[int] = mapped_column(ForeignKey("local_government_areas.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    party_affiliation: Mapped[str] = mapped_column(String(120), nullable=False)
    manifesto_summary: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    election = relationship("Election", back_populates="candidates")
    lga = relationship("LocalGovernmentArea")
