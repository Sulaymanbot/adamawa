"""Ballot retrieval, vote submission, results and receipts over the HTTP API."""

from datetime import timedelta

from app.extensions import db
from app.models import AuditLog, Vote, utcnow


def url(world, suffix=""):
    return f"/api/v1/elections/{world['election'].id}{suffix}"


def vote(c, world, cand_key, headers=None):
    return c.post(url(world, "/votes"), {"candidate_id": world["candidates"][cand_key].id}, headers=headers)


class TestBallot:
    def test_eligible_voter_sees_only_own_lga_candidates(self, voter_client, world):
        c = voter_client("yn1")
        resp = c.get(url(world, "/ballot"))
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert [x["full_name"] for x in data["candidates"]] == ["Alpha Candidate", "Bravo Candidate"]
        assert data["can_vote"] and not data["has_voted"]
        assert "SIMULATED" in data["notice"]

    def test_ineligible_voters(self, voter_client, world):
        assert voter_client("pending").get(url(world, "/ballot")).get_json()["error"]["code"] == "not_verified"
        resp = voter_client("song").get(url(world, "/ballot"))
        assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "no_candidates"

    def test_single_lga_election_hidden_from_other_lgas(self, voter_client, world):
        e = world["election"]
        yola_north = world["lgas"]["Yola North"].id
        e.scope, e.lga_id = "single_lga", yola_north
        db.session.commit()
        assert voter_client("ys1").get(url(world, "/ballot")).status_code == 404
        assert all(x["id"] != e.id for x in voter_client("ys1").get("/api/v1/elections").get_json()["data"])

    def test_draft_election_not_visible_to_voters(self, voter_client, world):
        world["election"].status = "draft"
        db.session.commit()
        c = voter_client("yn1")
        assert c.get(url(world)).status_code == 404
        assert c.get("/api/v1/elections").get_json()["data"] == []

    def test_admin_cannot_fetch_ballot(self, admin_client, world):
        assert admin_client.get(url(world, "/ballot")).status_code == 403


class TestVoting:
    def test_successful_vote(self, voter_client, world):
        c = voter_client("yn1")
        resp = vote(c, world, "yn_a")
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["recorded"] and len(data["receipt_reference"]) == 19
        assert "candidate" not in str(data).lower() and "Alpha" not in str(data)
        status = c.get(url(world, "/participation-status")).get_json()["data"]
        assert status["has_voted"] and not status["can_vote"]
        assert "Alpha" not in str(status)
        listing = c.get("/api/v1/elections").get_json()["data"][0]
        assert listing["participation"]["has_voted"] and "receipt_reference" not in listing["participation"]

    def test_duplicate_vote_rejected(self, voter_client, world):
        c = voter_client("yn1")
        assert vote(c, world, "yn_a").status_code == 201
        resp = vote(c, world, "yn_b")
        assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "already_voted"
        assert db.session.query(Vote).count() == 1
        assert db.session.query(AuditLog).filter_by(event_type="vote.duplicate_rejected").count() == 1

    def test_idempotency_key_replay(self, voter_client, world):
        c = voter_client("yn1")
        first = vote(c, world, "yn_a", {"Idempotency-Key": "abc-123-def-456"})
        again = vote(c, world, "yn_a", {"Idempotency-Key": "abc-123-def-456"})
        assert first.status_code == 201 and again.status_code == 200
        assert again.get_json()["data"]["replayed"] is True
        assert again.get_json()["data"]["receipt_reference"] == first.get_json()["data"]["receipt_reference"]
        assert vote(c, world, "yn_a", {"Idempotency-Key": "bad key!"}).status_code == 422

    def test_vote_outside_window(self, voter_client, world):
        e = world["election"]
        e.start_at = utcnow() + timedelta(hours=1)
        e.end_at = utcnow() + timedelta(hours=3)
        db.session.commit()
        resp = vote(voter_client("yn1"), world, "yn_a")
        assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "voting_closed"
        assert "No vote was recorded" in resp.get_json()["error"]["message"]

    def test_vote_after_window_end(self, voter_client, world):
        e = world["election"]
        e.start_at = utcnow() - timedelta(hours=3)
        e.end_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
        assert vote(voter_client("yn1"), world, "yn_a").status_code == 409

    def test_vote_when_closed(self, voter_client, world):
        world["election"].status = "closed"
        db.session.commit()
        assert vote(voter_client("yn1"), world, "yn_a").status_code == 409

    def test_unverified_voter_cannot_vote(self, voter_client, world):
        resp = vote(voter_client("pending"), world, "yn_a")
        assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "not_verified"
        assert db.session.query(Vote).count() == 0

    def test_candidate_from_other_lga_or_inactive(self, voter_client, world):
        c = voter_client("yn1")
        assert vote(c, world, "ys_a").status_code == 422
        world["candidates"]["yn_b"].status = "inactive"
        db.session.commit()
        assert vote(c, world, "yn_b").status_code == 422
        assert c.post(url(world, "/votes"), {"candidate_id": 99999}).status_code == 422
        assert db.session.query(Vote).count() == 0

    def test_admin_cannot_vote(self, admin_client, world):
        assert vote(admin_client, world, "yn_a").status_code == 403

    def test_vote_audit_has_no_choice(self, voter_client, world):
        vote(voter_client("yn1"), world, "yn_b")
        entry = db.session.query(AuditLog).filter_by(event_type="vote.submitted").one()
        assert "Bravo" not in entry.sanitized_description
        assert str(world["candidates"]["yn_b"].id) not in (entry.entity_id or "") or entry.entity_type == "election"


class TestResults:
    def cast_three(self, voter_client, world):
        for key, cand in (("yn1", "yn_a"), ("yn2", "yn_a"), ("yn3", "yn_b")):
            assert vote(voter_client(key), world, cand).status_code == 201

    def test_results_hidden_until_closed_and_published(self, client, voter_client, admin_client, world):
        self.cast_three(voter_client, world)
        assert client.get(url(world, "/results")).status_code == 403
        admin_client.post(f"/api/v1/admin/elections/{world['election'].id}/close")
        resp = client.get(url(world, "/results"))
        assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "results_not_published"
        assert admin_client.post(f"/api/v1/admin/elections/{world['election'].id}/publish-results").status_code == 200
        resp = client.get(url(world, "/results"))
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        yn = next(r for r in data["races"] if r["lga"]["name"] == "Yola North")
        assert yn["total_valid_votes"] == 3 and yn["winner"]["full_name"] == "Alpha Candidate"
        assert "SIMULATED" in data["disclaimer"]
        assert [e["id"] for e in client.get("/api/v1/results").get_json()["data"]] == [world["election"].id]

    def test_scheduled_publication_time(self, client, voter_client, admin_client, world):
        self.cast_three(voter_client, world)
        eid = world["election"].id
        admin_client.post(f"/api/v1/admin/elections/{eid}/close")
        later = (utcnow() + timedelta(hours=2)).isoformat() + "+00:00"
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/publish-results", {"publish_at": later}).status_code == 200
        assert client.get(url(world, "/results")).status_code == 403

    def test_hide_results(self, client, voter_client, admin_client, world):
        eid = world["election"].id
        admin_client.post(f"/api/v1/admin/elections/{eid}/close")
        admin_client.post(f"/api/v1/admin/elections/{eid}/publish-results")
        assert client.get(url(world, "/results")).status_code == 200
        admin_client.post(f"/api/v1/admin/elections/{eid}/publish-results", {"hide": True})
        assert client.get(url(world, "/results")).status_code == 403

    def test_receipt_check(self, client, voter_client, world):
        receipt = vote(voter_client("yn1"), world, "yn_a").get_json()["data"]["receipt_reference"]
        resp = client.post("/api/v1/receipts/verify", {"receipt_reference": receipt.lower()})
        assert resp.status_code == 200 and resp.get_json()["data"]["recorded"] is True
        assert "Alpha" not in resp.get_data(as_text=True)
        assert client.post("/api/v1/receipts/verify", {"receipt_reference": "AAAA-BBBB-CCCC-DDDD"}).get_json()["data"] == {
            "recorded": False
        }
        assert client.post("/api/v1/receipts/verify", {"receipt_reference": "nope"}).status_code == 422
