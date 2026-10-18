"""Encrypted ballots.

Only ciphertext is stored. The candidate choice is never kept in a plaintext
column. A unique (election_id, voter_id) constraint is the database-level
second layer against double voting.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.base import utcnow


class Vote(db.Model):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("election_id", "voter_id", name="uq_votes_election_voter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    election_id: Mapped[int] = mapped_column(ForeignKey("elections.id"), nullable=False, index=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id"), nullable=False, index=True)
    encrypted_vote_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    receipt_reference: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    # Hash of the client's Idempotency-Key, so a retried submission returns the
    # original receipt instead of an error.
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cast_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
