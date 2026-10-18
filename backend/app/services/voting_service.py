"""Secure vote submission.

Every check happens on the server inside a single transaction, immediately
before the encrypted ballot is written:

1. lock the voter row (SELECT ... FOR UPDATE on MySQL) so concurrent
   submissions by the same voter are serialised;
2. re-check account status, verification, scope and the voting window;
3. check for an existing ballot (application-level one-vote rule) and honour
   an idempotent retry;
4. validate the candidate against the election and the voter's LGA;
5. encrypt and insert. The UNIQUE(election_id, voter_id) constraint is the
   database-level backstop if two transactions still race.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.errors import APIError
from app.extensions import db
from app.models import Candidate, Election, User, Vote, Voter, utcnow
from app.services import audit_service, crypto_service, election_service

RECEIPT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
NOT_RECORDED = " No vote was recorded."

_REASON_MESSAGES = {
    "not_a_voter": "Only registered voters can vote.",
    "account_inactive": "Your account is not active.",
    "not_verified": "Your registration has not been verified yet, so you cannot vote.",
    "out_of_scope": "You are not eligible to vote in this election.",
    "no_candidates": "There are no candidates on the ballot for your LGA.",
}


@dataclass
class VoteResult:
    receipt_reference: str
    cast_at: str
    replayed: bool = False


def new_receipt() -> str:
    raw = "".join(secrets.choice(RECEIPT_ALPHABET) for _ in range(16))
    return "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def _idem_hash(key: str | None, voter_id: int, election_id: int) -> str | None:
    if not key:
        return None
    return hashlib.sha256(f"{voter_id}:{election_id}:{key}".encode()).hexdigest()


def _reject(election_id: int, code: str, status: int, message: str):
    audit_service.record(
        "vote.rejected",
        f"Vote rejected for election #{election_id}: {code}",
        entity_type="election",
        entity_id=election_id,
    )
    raise APIError(status, code, message + NOT_RECORDED)


def cast_vote(user: User, election_id: int, candidate_id: int, idempotency_key: str | None) -> VoteResult:
    if user.voter is None:
        raise APIError(403, "not_a_voter", "Only registered voters can vote." + NOT_RECORDED)
    voter_pk = user.voter.id

    # Step 1: serialise per voter.
    voter = db.session.execute(db.select(Voter).where(Voter.id == voter_pk).with_for_update()).scalar_one()
    election = db.session.execute(
        db.select(Election).where(Election.id == election_id).with_for_update(read=True)
    ).scalar_one_or_none()
    if (
        election is None
        or not election_service.in_scope(election, voter)
        or election.status not in election_service.VOTER_VISIBLE_STATUSES
    ):
        db.session.rollback()
        raise APIError(404, "not_found", "Election not found." + NOT_RECORDED)

    # Step 2: eligibility and window.
    eligible, reason = election_service.eligibility(election, voter)
    if not eligible:
        db.session.rollback()
        _reject(election.id, reason, 403, _REASON_MESSAGES.get(reason, "You are not eligible to vote."))
    if not election_service.voting_open(election):
        db.session.rollback()
        _reject(election.id, "voting_closed", 409, "Voting is not open for this election right now.")

    # Step 3: one vote per voter (+ idempotent retry).
    idem = _idem_hash(idempotency_key, voter.id, election.id)
    existing = db.session.execute(db.select(Vote).filter_by(election_id=election.id, voter_id=voter.id)).scalar_one_or_none()
    if existing is not None:
        db.session.rollback()
        if idem and existing.idempotency_key_hash == idem:
            return VoteResult(existing.receipt_reference, audit_service.iso(existing.cast_at), replayed=True)
        audit_service.record(
            "vote.duplicate_rejected",
            f"Duplicate vote attempt rejected for election #{election.id}",
            entity_type="election",
            entity_id=election.id,
        )
        raise APIError(409, "already_voted", "You have already voted in this election. Your original vote stands.")

    # Step 4: candidate must be active, in this election and in the voter's LGA.
    candidate = db.session.get(Candidate, candidate_id)
    if (
        candidate is None
        or candidate.election_id != election.id
        or candidate.status != "active"
        or candidate.lga_id != voter.lga_id
    ):
        db.session.rollback()
        _reject(election.id, "invalid_candidate", 422, "The selected candidate is not on your ballot.")

    # Step 5: encrypt and insert.
    receipt = new_receipt()
    ciphertext, nonce, digest = crypto_service.encrypt_ballot(election.id, candidate.id, candidate.lga_id, receipt)
    now = utcnow()
    vote = Vote(
        election_id=election.id,
        voter_id=voter.id,
        encrypted_vote_payload=ciphertext,
        payload_nonce=nonce,
        integrity_hash=digest,
        receipt_reference=receipt,
        idempotency_key_hash=idem,
        key_version=crypto_service.KEY_VERSION,
        cast_at=now,
        created_at=now,
    )
    db.session.add(vote)
    audit_service.record(
        "vote.submitted",
        f"Vote recorded for election #{election.id}",
        entity_type="election",
        entity_id=election.id,
        commit=False,
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        audit_service.record(
            "vote.duplicate_rejected",
            f"Concurrent duplicate vote blocked by database constraint for election #{election.id}",
            entity_type="election",
            entity_id=election.id,
        )
        raise APIError(409, "already_voted", "You have already voted in this election. Your original vote stands.") from None
    return VoteResult(receipt, audit_service.iso(now))


def participation_status(election: Election, voter: Voter) -> dict:
    vote = db.session.execute(db.select(Vote).filter_by(election_id=election.id, voter_id=voter.id)).scalar_one_or_none()
    eligible, reason = election_service.eligibility(election, voter)
    return {
        "election_id": election.id,
        "has_voted": vote is not None,
        "receipt_reference": vote.receipt_reference if vote else None,
        "cast_at": audit_service.iso(vote.cast_at) if vote else None,
        "eligible": eligible,
        "ineligible_reason": reason,
        "can_vote": eligible and vote is None and election_service.voting_open(election),
    }


def check_receipt(reference: str) -> dict:
    """Public check that a receipt exists in the ballot box (does not reveal the choice)."""
    vote = db.session.execute(db.select(Vote).filter_by(receipt_reference=reference)).scalar_one_or_none()
    if vote is None:
        return {"recorded": False}
    election = db.session.get(Election, vote.election_id)
    return {
        "recorded": True,
        "election_title": election.title,
        "cast_date": vote.cast_at.date().isoformat(),
    }
