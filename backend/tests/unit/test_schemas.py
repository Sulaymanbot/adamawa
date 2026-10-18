"""Input validation and normalisation in request schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    CandidateCreate,
    ElectionCreate,
    RegisterRequest,
    VerificationRequest,
    VoteRequest,
)

BASE = {
    "surname": "Bello",
    "first_name": "Aisha",
    "email": "  Aisha@Example.com ",
    "phone": "0803 123 4567",
    "voter_id": "demo-1234-5678",
    "lga_id": 1,
    "ward_id": 2,
    "polling_unit_id": 3,
    "password": "StrongPass99",
    "confirm_password": "StrongPass99",
    "demo_acknowledged": True,
}


def fields(exc: ValidationError) -> set[str]:
    return {".".join(str(p) for p in e["loc"]) for e in exc.errors()}


def test_register_normalises_input():
    req = RegisterRequest.model_validate(BASE)
    assert req.email == "aisha@example.com"
    assert req.phone == "+2348031234567"
    assert req.voter_id == "DEMO12345678"


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"password": "short1", "confirm_password": "short1"}, "password"),
        ({"password": "onlyletterspassword", "confirm_password": "onlyletterspassword"}, "password"),
        ({"surname": "Bello<script>"}, "surname"),
        ({"surname": "Robert'); DROP TABLE users;--"}, "surname"),
        ({"email": "not-an-email"}, "email"),
        ({"phone": "12345"}, "phone"),
        ({"voter_id": "x"}, "voter_id"),
        ({"lga_id": "1"}, "lga_id"),
        ({"lga_id": -1}, "lga_id"),
        ({"demo_acknowledged": False}, "demo_acknowledged"),
    ],
)
def test_register_rejects_invalid(override, field):
    with pytest.raises(ValidationError) as exc:
        RegisterRequest.model_validate({**BASE, **override})
    assert field in fields(exc.value)


def test_register_password_mismatch():
    with pytest.raises(ValidationError) as exc:
        RegisterRequest.model_validate({**BASE, "confirm_password": "Different99x"})
    assert "Passwords do not match" in str(exc.value)


def test_unknown_fields_rejected():
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate({**BASE, "role": "admin"})
    with pytest.raises(ValidationError):
        VoteRequest.model_validate({"candidate_id": 1, "voter_id": 5})


def test_vote_request_requires_strict_int():
    assert VoteRequest.model_validate({"candidate_id": 3}).candidate_id == 3
    for bad in ("3", 3.5, None, True, [3]):
        with pytest.raises(ValidationError):
            VoteRequest.model_validate({"candidate_id": bad})


def test_verification_reason_required_for_reject_and_suspend():
    with pytest.raises(ValidationError):
        VerificationRequest.model_validate({"action": "reject"})
    with pytest.raises(ValidationError):
        VerificationRequest.model_validate({"action": "suspend", "reason": "   "})
    assert VerificationRequest.model_validate({"action": "verify"}).reason is None


def test_election_times_converted_to_utc_and_ordered():
    e = ElectionCreate.model_validate(
        {"title": "Demo", "start_at": "2026-10-02T09:00:00+01:00", "end_at": "2026-10-02T17:00:00+01:00"}
    )
    assert e.start_at == datetime(2026, 10, 2, 8, 0)
    assert e.start_at.tzinfo is None
    with pytest.raises(ValidationError):
        ElectionCreate.model_validate(
            {"title": "Demo", "start_at": "2026-10-02T17:00:00+01:00", "end_at": "2026-10-02T09:00:00+01:00"}
        )
    with pytest.raises(ValidationError):  # naive timestamps are ambiguous
        ElectionCreate.model_validate({"title": "Demo", "start_at": "2026-10-02T09:00:00", "end_at": "2026-10-02T17:00:00"})


def test_single_lga_requires_lga_and_all_lgas_clears_it():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ElectionCreate.model_validate(
            {"title": "Demo", "scope": "single_lga", "start_at": now, "end_at": now.replace(year=now.year + 1)}
        )
    e = ElectionCreate.model_validate(
        {"title": "Demo", "scope": "all_lgas", "lga_id": 3, "start_at": now, "end_at": now.replace(year=now.year + 1)}
    )
    assert e.lga_id is None


def test_candidate_photo_url_restricted():
    with pytest.raises(ValidationError):
        CandidateCreate.model_validate({"full_name": "A Person", "party_affiliation": "DP", "photo_url": "javascript:alert(1)"})
    ok = CandidateCreate.model_validate({"full_name": "A Person", "party_affiliation": "DP", "photo_url": "/static/img/x.png"})
    assert ok.photo_url == "/static/img/x.png"


def test_control_characters_stripped():
    c = CandidateCreate.model_validate({"full_name": "A\x00 Person\x07", "party_affiliation": "DP"})
    assert c.full_name == "A Person"
