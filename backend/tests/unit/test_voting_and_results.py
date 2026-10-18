"""One-vote enforcement and result aggregation at the service layer."""

import pytest
from flask import g
from sqlalchemy.exc import IntegrityError

from app.errors import APIError
from app.extensions import db
from app.models import Vote, utcnow
from app.services import crypto_service, results_service, voting_service


def cast(world, voter_key, cand_key, key=None):
    voter = world["voters"][voter_key]
    g.user = voter.user
    return voting_service.cast_vote(voter.user, world["election"].id, world["candidates"][cand_key].id, key)


@pytest.fixture
def ctx(app):
    with app.test_request_context():
        yield


def test_one_vote_per_voter(world, ctx):
    first = cast(world, "yn1", "yn_a")
    assert first.receipt_reference
    with pytest.raises(APIError) as exc:
        cast(world, "yn1", "yn_b")
    assert exc.value.code == "already_voted"
    assert db.session.query(Vote).count() == 1


def test_idempotent_retry_returns_same_receipt(world, ctx):
    first = cast(world, "yn1", "yn_a", key="retry-key-123")
    again = cast(world, "yn1", "yn_a", key="retry-key-123")
    assert again.replayed and again.receipt_reference == first.receipt_reference
    with pytest.raises(APIError):
        cast(world, "yn1", "yn_a", key="different-key-456")


def test_database_unique_constraint_is_second_layer(world, ctx):
    cast(world, "yn1", "yn_a")
    voter = world["voters"]["yn1"]
    ct, nonce, digest = crypto_service.encrypt_ballot(world["election"].id, 1, 1, "XXXX-XXXX-XXXX-XXXX")
    db.session.add(
        Vote(
            election_id=world["election"].id,
            voter_id=voter.id,
            encrypted_vote_payload=ct,
            payload_nonce=nonce,
            integrity_hash=digest,
            receipt_reference="XXXX-XXXX-XXXX-XXXX",
            cast_at=utcnow(),
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_candidate_from_other_lga_rejected(world, ctx):
    with pytest.raises(APIError) as exc:
        cast(world, "yn1", "ys_a")
    assert exc.value.code == "invalid_candidate"
    assert "No vote was recorded" in exc.value.message


def test_stored_vote_has_no_plaintext_choice(world, ctx):
    cast(world, "yn1", "yn_b")
    vote = db.session.query(Vote).one()
    cand_id = world["candidates"]["yn_b"].id
    columns = {c.name for c in Vote.__table__.columns}
    assert "candidate_id" not in columns
    assert f'"c":{cand_id}'.encode() not in vote.encrypted_vote_payload


def test_results_aggregation_and_threshold(world, ctx):
    for voter, cand in [("yn1", "yn_a"), ("yn2", "yn_a"), ("yn3", "yn_b"), ("ys1", "ys_a")]:
        cast(world, voter, cand)
    result = results_service.compute(world["election"])
    races = {r["lga"]["name"]: r for r in result["races"]}
    yn = races["Yola North"]
    assert yn["outcome"] == "winner" and yn["winner"]["full_name"] == "Alpha Candidate"
    assert [(c["full_name"], c["votes"], c["percentage"]) for c in yn["candidates"]] == [
        ("Alpha Candidate", 2, 66.7),
        ("Bravo Candidate", 1, 33.3),
    ]
    assert races["Yola South"]["outcome"] == "withheld"
    assert all(c["votes"] is None for c in races["Yola South"]["candidates"])
    assert races["Numan"]["outcome"] == "no_votes"
    assert result["summary"]["ballots_cast"] == 4 and result["summary"]["valid_votes"] == 4
    assert result["is_simulated"] is True


def test_tie_is_reported_without_winner(world, ctx, app):
    app.config["RESULTS_MIN_RACE_VOTES"] = 1
    cast(world, "yn1", "yn_a")
    cast(world, "yn2", "yn_b")
    yn = next(r for r in results_service.compute(world["election"])["races"] if r["lga"]["name"] == "Yola North")
    assert yn["outcome"] == "tie" and yn["winner"] is None
    assert "Tie" in yn["note"]


def test_tampered_ballot_counted_invalid(world, ctx, app):
    app.config["RESULTS_MIN_RACE_VOTES"] = 1
    cast(world, "yn1", "yn_a")
    cast(world, "yn2", "yn_a")
    vote = db.session.query(Vote).first()
    vote.encrypted_vote_payload = bytes([vote.encrypted_vote_payload[0] ^ 0x01]) + vote.encrypted_vote_payload[1:]
    db.session.commit()
    result = results_service.compute(world["election"])
    assert result["summary"]["invalid_ballots"] == 1
    assert result["summary"]["valid_votes"] == 1
