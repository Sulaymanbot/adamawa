"""Voter-facing election, ballot, vote and results endpoints."""

import re

from flask import g, request

from app.api import api_v1, rate, user_or_ip
from app.errors import APIError, ok
from app.extensions import limiter
from app.schemas import ReceiptCheckRequest, VoteRequest, parse_body
from app.security.authz import api_auth
from app.services import election_service, results_service, voting_service

IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def _voter():
    return g.user.voter


@api_v1.get("/elections")
@api_auth("voter.self")
def list_elections():
    voter = _voter()
    items = []
    for election in election_service.list_for_voter(voter):
        data = election_service.serialize(election)
        data["participation"] = voting_service.participation_status(election, voter)
        data["participation"].pop("receipt_reference")
        items.append(data)
    return ok(items)


@api_v1.get("/elections/<int:election_id>")
@api_auth("voter.self")
def get_election(election_id: int):
    election = election_service.get_for_voter(election_id, _voter())
    return ok(election_service.serialize(election))


@api_v1.get("/elections/<int:election_id>/ballot")
@api_auth("voter.self")
def ballot(election_id: int):
    voter = _voter()
    election = election_service.get_for_voter(election_id, voter)
    eligible, reason = election_service.eligibility(election, voter)
    if not eligible:
        messages = {
            "not_verified": "You can vote once an officer verifies your account.",
            "account_inactive": "Your account is not active.",
            "no_candidates": "No candidates in your LGA for this election.",
        }
        raise APIError(403, reason, messages.get(reason, "You are not eligible to vote in this election."))
    status = voting_service.participation_status(election, voter)
    candidates = election_service.active_candidates_for(election, voter.lga_id)
    return ok(
        {
            "election": election_service.serialize(election),
            "race": {"lga": voter.lga.name},
            "instructions": ["Choose one candidate.", "Check your choice.", "Submit. You can't change it after."],
            "candidates": [election_service.serialize_candidate(c) for c in candidates],
            "has_voted": status["has_voted"],
            "can_vote": status["can_vote"],
            "notice": "SIMULATED ELECTION – academic prototype. Not an official ballot.",
        }
    )


@api_v1.post("/elections/<int:election_id>/votes")
@api_auth("ballot.cast")
@limiter.limit(rate("VOTE_RATE_LIMIT"), key_func=user_or_ip)
def cast_vote(election_id: int):
    data = parse_body(VoteRequest)
    key = request.headers.get("Idempotency-Key")
    if key is not None and not IDEMPOTENCY_RE.match(key):
        raise APIError(422, "validation_error", "Invalid Idempotency-Key header.")
    result = voting_service.cast_vote(g.user, election_id, data.candidate_id, key)
    return ok(
        {
            "recorded": True,
            "receipt_reference": result.receipt_reference,
            "cast_at": result.cast_at,
            "replayed": result.replayed,
            "message": "Vote recorded. Keep your receipt code; it doesn't show your choice.",
        },
        200 if result.replayed else 201,
    )


@api_v1.get("/elections/<int:election_id>/participation-status")
@api_auth("voter.self")
def participation(election_id: int):
    voter = _voter()
    election = election_service.get_for_voter(election_id, voter)
    return ok(voting_service.participation_status(election, voter))


@api_v1.get("/elections/<int:election_id>/results")
def results(election_id: int):
    return ok(results_service.results_for_public(election_id))


@api_v1.get("/results")
def published_results():
    return ok([election_service.serialize(e) for e in election_service.published_elections()])


@api_v1.post("/receipts/verify")
@limiter.limit(rate("OTP_RATE_LIMIT"))
def verify_receipt():
    data = parse_body(ReceiptCheckRequest)
    return ok(voting_service.check_receipt(data.receipt_reference))
