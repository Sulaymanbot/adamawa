"""Voter profiles and administrator verification workflow."""

from __future__ import annotations

import contextlib

from flask import g

from app.errors import APIError
from app.extensions import db
from app.models import User, Voter, utcnow
from app.security import sessions
from app.security.identifiers import (
    hash_voter_id,
    mask_email,
    mask_phone,
    mask_voter_id,
    normalize_voter_id,
)
from app.services import audit_service
from app.services.audit_service import iso

# action -> (allowed current statuses, new status)
VERIFICATION_TRANSITIONS = {
    "verify": ({"pending", "rejected"}, "verified"),
    "reject": ({"pending"}, "rejected"),
    "suspend": ({"verified", "pending"}, "suspended"),
    "reactivate": ({"suspended"}, "verified"),
}


def profile(user: User) -> dict:
    """Minimal, masked view of the signed-in voter."""
    data = {
        "id": user.id,
        "role": user.role,
        "display_name": user.display_name,
        "email_masked": mask_email(user.email),
        "phone_masked": mask_phone(user.phone),
    }
    voter = user.voter
    if voter is not None:
        data["voter"] = {
            "voter_id_masked": mask_voter_id(voter.voter_id_last4),
            "full_name": voter.full_name,
            "verification_status": voter.verification_status,
            "verification_reason": voter.verification_reason if voter.verification_status in {"rejected", "suspended"} else None,
            "lga": voter.lga.name,
            "ward": voter.ward.name,
            "polling_unit": voter.polling_unit.name,
            "registered_at": iso(voter.created_at),
        }
    return data


def admin_row(voter: Voter) -> dict:
    return {
        "id": voter.id,
        "full_name": voter.full_name,
        "voter_id_masked": mask_voter_id(voter.voter_id_last4),
        "email_masked": mask_email(voter.user.email),
        "phone_masked": mask_phone(voter.user.phone),
        "lga": {"id": voter.lga_id, "name": voter.lga.name},
        "ward": {"id": voter.ward_id, "name": voter.ward.name},
        "polling_unit": {"id": voter.polling_unit_id, "name": voter.polling_unit.name},
        "verification_status": voter.verification_status,
        "verification_reason": voter.verification_reason,
        "verified_at": iso(voter.verified_at),
        "registered_at": iso(voter.created_at),
    }


def search(*, status=None, lga_id=None, ward_id=None, q=None, page=1, per_page=20):
    query = db.select(Voter).join(User, Voter.user_id == User.id)
    if status:
        query = query.where(Voter.verification_status == status)
    if lga_id:
        query = query.where(Voter.lga_id == lga_id)
    if ward_id:
        query = query.where(Voter.ward_id == ward_id)
    if q:
        q = q.strip()[:80]
        # Escape LIKE wildcards so user input is matched literally.
        prefix = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        conditions = [
            Voter.surname.ilike(prefix, escape="\\"),
            Voter.first_name.ilike(prefix, escape="\\"),
            User.email == q.lower(),
        ]
        with contextlib.suppress(ValueError):  # not shaped like a voter ID
            conditions.append(Voter.voter_id_hash == hash_voter_id(normalize_voter_id(q)))
        query = query.where(db.or_(*conditions))
    query = query.order_by(Voter.created_at.desc(), Voter.id.desc())
    return db.paginate(query, page=page, per_page=per_page, max_per_page=100, error_out=False)


def change_verification(voter_id: int, action: str, reason: str | None) -> Voter:
    voter = db.session.get(Voter, voter_id)
    if voter is None:
        raise APIError(404, "not_found", "Voter not found.")
    allowed, new_status = VERIFICATION_TRANSITIONS[action]
    if voter.verification_status not in allowed:
        raise APIError(
            409,
            "invalid_transition",
            f"Cannot {action} a voter whose status is '{voter.verification_status}'.",
        )
    old = voter.verification_status
    voter.verification_status = new_status
    voter.verification_reason = reason
    if new_status == "verified":
        voter.verified_by = g.user.id
        voter.verified_at = utcnow()
    if new_status == "suspended":
        voter.user.status = "suspended"
        sessions.revoke_all_sessions(voter.user_id)
    elif voter.user.status == "suspended" and new_status == "verified":
        voter.user.status = "active"
    audit_service.record(
        f"voter.{action}",
        f"Voter #{voter.id} status {old} -> {new_status}" + (f". Reason: {reason}" if reason else ""),
        entity_type="voter",
        entity_id=voter.id,
        commit=False,
    )
    db.session.commit()
    return voter
