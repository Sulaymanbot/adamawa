"""Administrator endpoints. Every route enforces a permission server-side."""

from datetime import datetime

from flask import request

from app.api import api_v1, int_arg, page_meta
from app.errors import APIError, ok
from app.models.voter import VERIFICATION_STATUSES
from app.schemas import (
    CandidateCreate,
    CandidateUpdate,
    ElectionAction,
    ElectionCreate,
    ElectionUpdate,
    PublishRequest,
    VerificationRequest,
    VoterSearchRequest,
    parse_body,
    to_utc_naive,
)
from app.security.authz import api_auth
from app.services import (
    audit_service,
    dashboard_service,
    election_service,
    voter_service,
)


@api_v1.get("/admin/dashboard")
@api_auth("admin.dashboard")
def dashboard():
    return ok(dashboard_service.summary())


# ------------------------------------------------------------------ voters


@api_v1.get("/admin/voters")
@api_auth("voters.read")
def voters():
    """Filter-only listing. Free-text search (names, emails, voter IDs) must use
    POST /admin/voters/search so personal data never appears in URLs or access logs."""
    if "q" in request.args:
        raise APIError(
            422, "validation_error", "Use POST /admin/voters/search for text search so personal data is not put in the URL."
        )
    status = request.args.get("status") or None
    if status and status not in VERIFICATION_STATUSES:
        raise APIError(422, "validation_error", "Some fields are invalid.", [{"field": "status", "message": "Unknown status"}])
    pagination = voter_service.search(
        status=status,
        lga_id=int_arg("lga_id"),
        ward_id=int_arg("ward_id"),
        page=int_arg("page", 1, maximum=10_000),
        per_page=int_arg("per_page", 20, maximum=100),
    )
    return ok([voter_service.admin_row(v) for v in pagination.items], meta=page_meta(pagination))


@api_v1.post("/admin/voters/search")
@api_auth("voters.read")
def search_voters():
    data = parse_body(VoterSearchRequest)
    pagination = voter_service.search(
        status=data.status, lga_id=data.lga_id, ward_id=data.ward_id, q=data.q, page=data.page, per_page=data.per_page
    )
    return ok([voter_service.admin_row(v) for v in pagination.items], meta=page_meta(pagination))


@api_v1.patch("/admin/voters/<int:voter_id>/verification")
@api_auth("voters.verify")
def verification(voter_id: int):
    data = parse_body(VerificationRequest)
    voter = voter_service.change_verification(voter_id, data.action, data.reason)
    return ok(voter_service.admin_row(voter))


# ------------------------------------------------------------------ elections


@api_v1.get("/admin/elections")
@api_auth("elections.manage")
def admin_elections():
    return ok([election_service.serialize(e, admin=True) for e in election_service.list_all()])


@api_v1.post("/admin/elections")
@api_auth("elections.manage")
def create_election():
    election = election_service.create(parse_body(ElectionCreate))
    return ok(election_service.serialize(election, admin=True), 201)


@api_v1.get("/admin/elections/<int:election_id>")
@api_auth("elections.manage")
def admin_get_election(election_id: int):
    return ok(election_service.serialize(election_service.get(election_id), admin=True))


@api_v1.patch("/admin/elections/<int:election_id>")
@api_auth("elections.manage")
def update_election(election_id: int):
    election = election_service.update(election_id, parse_body(ElectionUpdate))
    return ok(election_service.serialize(election, admin=True))


@api_v1.post("/admin/elections/<int:election_id>/<any(schedule, unschedule, open, close, archive, cancel):action>")
@api_auth("elections.manage")
def election_action(election_id: int, action: str):
    data = parse_body(ElectionAction) if request.content_length else ElectionAction()
    election = election_service.transition(election_id, action, data.reason)
    return ok(election_service.serialize(election, admin=True))


@api_v1.post("/admin/elections/<int:election_id>/publish-results")
@api_auth("results.publish")
def publish_results(election_id: int):
    data = parse_body(PublishRequest) if request.content_length else PublishRequest()
    election = election_service.publish_results(election_id, data.publish_at, data.hide)
    return ok(election_service.serialize(election, admin=True))


# ------------------------------------------------------------------ candidates


@api_v1.get("/admin/elections/<int:election_id>/candidates")
@api_auth("candidates.manage")
def admin_candidates(election_id: int):
    return ok([election_service.serialize_candidate(c, admin=True) for c in election_service.list_candidates(election_id)])


@api_v1.post("/admin/elections/<int:election_id>/candidates")
@api_auth("candidates.manage")
def create_candidate(election_id: int):
    candidate = election_service.create_candidate(election_id, parse_body(CandidateCreate))
    return ok(election_service.serialize_candidate(candidate, admin=True), 201)


@api_v1.patch("/admin/candidates/<int:candidate_id>")
@api_auth("candidates.manage")
def update_candidate(candidate_id: int):
    candidate = election_service.update_candidate(candidate_id, parse_body(CandidateUpdate))
    return ok(election_service.serialize_candidate(candidate, admin=True))


@api_v1.delete("/admin/candidates/<int:candidate_id>")
@api_auth("candidates.manage")
def delete_candidate(candidate_id: int):
    election_service.delete_candidate(candidate_id)
    return ok({"deleted": True})


# ------------------------------------------------------------------ audit


def _date_arg(name: str):
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise APIError(
            422, "validation_error", "Some fields are invalid.", [{"field": name, "message": "Use an ISO date/time"}]
        ) from None
    if value.tzinfo is None:
        return value
    return to_utc_naive(value)


@api_v1.get("/admin/audit-logs")
@api_auth("audit.read")
def audit_logs():
    event_type = (request.args.get("event_type") or "").strip()[:60] or None
    entity_type = (request.args.get("entity_type") or "").strip()[:40] or None
    pagination = audit_service.list_logs(
        event_type=event_type,
        actor_user_id=int_arg("actor_user_id"),
        entity_type=entity_type,
        date_from=_date_arg("from"),
        date_to=_date_arg("to"),
        page=int_arg("page", 1, maximum=100_000),
        per_page=int_arg("per_page", 25, maximum=100),
    )
    return ok([audit_service.serialize(e) for e in pagination.items], meta=page_meta(pagination))
