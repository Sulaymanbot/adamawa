"""Election lifecycle, eligibility and candidate management."""

from __future__ import annotations

from datetime import datetime

from flask import current_app, g

from app.errors import APIError
from app.extensions import db
from app.models import Candidate, Election, LocalGovernmentArea, Vote, Voter, utcnow
from app.schemas import CandidateCreate, CandidateUpdate, ElectionCreate, ElectionUpdate
from app.services import audit_service
from app.services.audit_service import iso

# action -> (allowed source statuses, target status)
TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "schedule": (frozenset({"draft"}), "scheduled"),
    "unschedule": (frozenset({"scheduled"}), "draft"),
    "open": (frozenset({"draft", "scheduled"}), "open"),
    "close": (frozenset({"open"}), "closed"),
    "archive": (frozenset({"closed", "cancelled"}), "archived"),
    "cancel": (frozenset({"draft", "scheduled", "open"}), "cancelled"),
}
EDITABLE_STATUSES = frozenset({"draft", "scheduled"})
VOTER_VISIBLE_STATUSES = ("scheduled", "open", "closed", "archived", "cancelled")
OVERRIDE_FIELDS = {"title", "description", "end_at"}


# ---------------------------------------------------------------- state rules


def can_transition(current: str, action: str) -> bool:
    allowed, _ = TRANSITIONS[action]
    return current in allowed


def voting_open(election: Election, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return election.status == "open" and election.start_at <= now < election.end_at


def results_visible(election: Election, now: datetime | None = None) -> bool:
    now = now or utcnow()
    return (
        election.status in {"closed", "archived"}
        and election.results_published_at is not None
        and election.results_published_at <= now
    )


def phase(election: Election, now: datetime | None = None) -> str:
    """Human-facing phase derived from status + clock."""
    now = now or utcnow()
    if election.status == "open":
        if now < election.start_at:
            return "opening_soon"
        if now >= election.end_at:
            return "voting_ended"
        return "voting_open"
    return election.status


def in_scope(election: Election, voter: Voter) -> bool:
    return election.scope == "all_lgas" or election.lga_id == voter.lga_id


def eligibility(election: Election, voter: Voter | None) -> tuple[bool, str | None]:
    """Is this voter eligible to take part in this election at all (ignoring the clock)?"""
    if voter is None:
        return False, "not_a_voter"
    if voter.user.status != "active":
        return False, "account_inactive"
    if voter.verification_status != "verified":
        return False, "not_verified"
    if not in_scope(election, voter):
        return False, "out_of_scope"
    if not active_candidates_for(election, voter.lga_id):
        return False, "no_candidates"
    return True, None


def active_candidates_for(election: Election, lga_id: int) -> list[Candidate]:
    return (
        db.session.execute(
            db.select(Candidate).filter_by(election_id=election.id, lga_id=lga_id, status="active").order_by(Candidate.full_name)
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------- queries


def get(election_id: int) -> Election:
    election = db.session.get(Election, election_id)
    if election is None:
        raise APIError(404, "not_found", "Election not found.")
    return election


def get_for_voter(election_id: int, voter: Voter) -> Election:
    election = db.session.get(Election, election_id)
    if election is None or election.status not in VOTER_VISIBLE_STATUSES or not in_scope(election, voter):
        raise APIError(404, "not_found", "Election not found.")
    return election


def list_for_voter(voter: Voter) -> list[Election]:
    elections = (
        db.session.execute(
            db.select(Election).where(Election.status.in_(VOTER_VISIBLE_STATUSES)).order_by(Election.start_at.desc())
        )
        .scalars()
        .all()
    )
    return [e for e in elections if in_scope(e, voter)]


def list_all() -> list[Election]:
    return db.session.execute(db.select(Election).order_by(Election.id.desc())).scalars().all()


def has_voted(election_id: int, voter_id: int) -> bool:
    return db.session.execute(db.select(Vote.id).filter_by(election_id=election_id, voter_id=voter_id)).first() is not None


def votes_cast(election_id: int) -> int:
    return db.session.execute(db.select(db.func.count(Vote.id)).filter_by(election_id=election_id)).scalar_one()


def eligible_voter_count(election: Election) -> int:
    lga_ids = db.select(Candidate.lga_id).filter_by(election_id=election.id, status="active").distinct()
    query = db.select(db.func.count(Voter.id)).where(Voter.verification_status == "verified", Voter.lga_id.in_(lga_ids))
    if election.scope == "single_lga":
        query = query.where(Voter.lga_id == election.lga_id)
    return db.session.execute(query).scalar_one()


def published_elections() -> list[Election]:
    now = utcnow()
    elections = (
        db.session.execute(
            db.select(Election)
            .where(Election.status.in_(("closed", "archived")), Election.results_published_at.is_not(None))
            .order_by(Election.end_at.desc())
        )
        .scalars()
        .all()
    )
    return [e for e in elections if results_visible(e, now)]


# ---------------------------------------------------------------- serialisers


def serialize(election: Election, *, admin: bool = False) -> dict:
    data = {
        "id": election.id,
        "title": election.title,
        "type": election.type,
        "description": election.description,
        "scope": election.scope,
        "lga": {"id": election.lga.id, "name": election.lga.name} if election.lga else None,
        "start_at": iso(election.start_at),
        "end_at": iso(election.end_at),
        "status": election.status,
        "phase": phase(election),
        "voting_open": voting_open(election),
        "results_available": results_visible(election),
        "is_simulated": True,
    }
    if admin:
        data.update(
            {
                "results_published_at": iso(election.results_published_at),
                "created_at": iso(election.created_at),
                "updated_at": iso(election.updated_at),
                "votes_cast": votes_cast(election.id),
                "eligible_voters": eligible_voter_count(election),
                "candidate_count": sum(1 for c in election.candidates if c.status == "active"),
                "allowed_actions": [a for a in TRANSITIONS if can_transition(election.status, a)],
                "editable": election.status in EDITABLE_STATUSES,
            }
        )
    return data


def serialize_candidate(candidate: Candidate, *, admin: bool = False) -> dict:
    data = {
        "id": candidate.id,
        "full_name": candidate.full_name,
        "party_affiliation": candidate.party_affiliation,
        "manifesto_summary": candidate.manifesto_summary,
        "photo_url": candidate.photo_url,
        "lga": {"id": candidate.lga_id, "name": candidate.lga.name},
    }
    if admin:
        data["status"] = candidate.status
        data["election_id"] = candidate.election_id
    return data


# ---------------------------------------------------------------- admin: elections


def _override_enabled() -> bool:
    return bool(current_app.config.get("DEMO_ADMIN_OVERRIDE"))


def _require_lga(lga_id: int | None) -> None:
    if lga_id is not None and db.session.get(LocalGovernmentArea, lga_id) is None:
        raise APIError(422, "validation_error", "Some fields are invalid.", [{"field": "lga_id", "message": "Unknown LGA"}])


def create(data: ElectionCreate) -> Election:
    _require_lga(data.lga_id)
    election = Election(
        title=data.title,
        type=data.type,
        description=data.description,
        scope=data.scope,
        lga_id=data.lga_id,
        start_at=data.start_at,
        end_at=data.end_at,
        status="draft",
        created_by=g.user.id,
    )
    db.session.add(election)
    db.session.flush()
    audit_service.record(
        "election.created",
        f"Election #{election.id} '{election.title}' created as draft",
        entity_type="election",
        entity_id=election.id,
        commit=False,
    )
    db.session.commit()
    return election


def update(election_id: int, data: ElectionUpdate) -> Election:
    election = get(election_id)
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise APIError(422, "validation_error", "No changes were provided.")
    override = False
    if election.status not in EDITABLE_STATUSES:
        if not _override_enabled():
            raise APIError(409, "election_locked", "This election can no longer be edited because voting has started or ended.")
        if set(changes) - OVERRIDE_FIELDS:
            raise APIError(
                409,
                "election_locked",
                "Only title, description and closing time can be changed after voting starts, even with the demo override.",
            )
        override = True
    if "lga_id" in changes:
        _require_lga(changes["lga_id"])
    for field, value in changes.items():
        setattr(election, field, value)
    if election.scope == "all_lgas":
        election.lga_id = None
    if election.scope == "single_lga" and election.lga_id is None:
        raise APIError(422, "validation_error", "Choose the LGA for a single-LGA election.")
    if election.end_at <= election.start_at:
        raise APIError(422, "validation_error", "Closing time must be after opening time.")
    audit_service.record(
        "election.updated",
        f"{'[DEMO OVERRIDE] ' if override else ''}Election #{election.id} updated: {', '.join(sorted(changes))}",
        entity_type="election",
        entity_id=election.id,
        commit=False,
    )
    db.session.commit()
    return election


def transition(election_id: int, action: str, reason: str | None = None) -> Election:
    election = get(election_id)
    if not can_transition(election.status, action):
        raise APIError(409, "invalid_transition", f"Cannot {action} an election that is '{election.status}'.")
    if action == "open":
        if utcnow() >= election.end_at:
            raise APIError(409, "window_passed", "The closing time has already passed. Edit the schedule first.")
        if not db.session.execute(db.select(Candidate.id).filter_by(election_id=election.id, status="active")).first():
            raise APIError(409, "no_candidates", "Add at least one active candidate before opening the election.")
    if action == "cancel" and election.status == "open" and not reason:
        raise APIError(422, "validation_error", "A reason is required to cancel an election that is open.")
    old = election.status
    election.status = TRANSITIONS[action][1]
    audit_service.record(
        f"election.{action}",
        f"Election #{election.id} {old} -> {election.status}" + (f". Reason: {reason}" if reason else ""),
        entity_type="election",
        entity_id=election.id,
        commit=False,
    )
    db.session.commit()
    return election


def publish_results(election_id: int, publish_at: datetime | None, hide: bool) -> Election:
    election = get(election_id)
    if election.status != "closed":
        raise APIError(409, "invalid_transition", "Results can only be published or hidden after the election is closed.")
    if hide:
        election.results_published_at = None
        event, desc = "election.results_hidden", f"Results for election #{election.id} hidden"
    else:
        election.results_published_at = publish_at or utcnow()
        event = "election.results_published"
        desc = f"Results for election #{election.id} published (visible from {iso(election.results_published_at)})"
    audit_service.record(event, desc, entity_type="election", entity_id=election.id, commit=False)
    db.session.commit()
    return election


# ---------------------------------------------------------------- admin: candidates


def _candidate_lga(election: Election, lga_id: int | None) -> int:
    if election.scope == "single_lga":
        if lga_id not in (None, election.lga_id):
            raise APIError(
                422,
                "validation_error",
                "Some fields are invalid.",
                [{"field": "lga_id", "message": "Candidate must be in the election's LGA"}],
            )
        return election.lga_id
    if lga_id is None:
        raise APIError(
            422, "validation_error", "Some fields are invalid.", [{"field": "lga_id", "message": "Choose the candidate's LGA"}]
        )
    _require_lga(lga_id)
    return lga_id


def _assert_candidates_editable(election: Election, *, allow_override: bool) -> bool:
    if election.status in EDITABLE_STATUSES:
        return False
    if allow_override and _override_enabled() and election.status == "open":
        return True
    raise APIError(409, "election_locked", "Candidates cannot be changed after voting has started.")


def list_candidates(election_id: int) -> list[Candidate]:
    get(election_id)
    return (
        db.session.execute(
            db.select(Candidate).filter_by(election_id=election_id).order_by(Candidate.lga_id, Candidate.full_name)
        )
        .scalars()
        .all()
    )


def create_candidate(election_id: int, data: CandidateCreate) -> Candidate:
    election = get(election_id)
    _assert_candidates_editable(election, allow_override=False)
    candidate = Candidate(
        election_id=election.id,
        lga_id=_candidate_lga(election, data.lga_id),
        full_name=data.full_name,
        party_affiliation=data.party_affiliation,
        manifesto_summary=data.manifesto_summary,
        photo_url=data.photo_url,
        status="active",
    )
    db.session.add(candidate)
    db.session.flush()
    audit_service.record(
        "candidate.created",
        f"Candidate #{candidate.id} added to election #{election.id}",
        entity_type="candidate",
        entity_id=candidate.id,
        commit=False,
    )
    db.session.commit()
    return candidate


def update_candidate(candidate_id: int, data: CandidateUpdate) -> Candidate:
    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None:
        raise APIError(404, "not_found", "Candidate not found.")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise APIError(422, "validation_error", "No changes were provided.")
    election = candidate.election
    override = False
    if election.status not in EDITABLE_STATUSES:
        # With the demo override only a status change (e.g. deactivate) is allowed while open.
        if set(changes) != {"status"}:
            raise APIError(409, "election_locked", "Candidates cannot be changed after voting has started.")
        override = _assert_candidates_editable(election, allow_override=True)
    if "lga_id" in changes:
        changes["lga_id"] = _candidate_lga(election, changes["lga_id"])
    for field, value in changes.items():
        setattr(candidate, field, value)
    audit_service.record(
        "candidate.updated",
        f"{'[DEMO OVERRIDE] ' if override else ''}Candidate #{candidate.id} updated: {', '.join(sorted(changes))}",
        entity_type="candidate",
        entity_id=candidate.id,
        commit=False,
    )
    db.session.commit()
    return candidate


def delete_candidate(candidate_id: int) -> None:
    candidate = db.session.get(Candidate, candidate_id)
    if candidate is None:
        raise APIError(404, "not_found", "Candidate not found.")
    if candidate.election.status not in EDITABLE_STATUSES:
        raise APIError(
            409, "election_locked", "Candidates cannot be removed after voting has started. Deactivate before opening instead."
        )
    audit_service.record(
        "candidate.deleted",
        f"Candidate #{candidate.id} removed from election #{candidate.election_id}",
        entity_type="candidate",
        entity_id=candidate.id,
        commit=False,
    )
    db.session.delete(candidate)
    db.session.commit()
