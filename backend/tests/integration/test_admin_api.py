"""Administrator endpoints: protection, verification, elections, candidates, audit."""

from datetime import UTC, datetime, timedelta

import pytest

from app.extensions import db
from app.models import AuditLog, Candidate, Election
from tests.conftest import VOTER_PASSWORD

ADMIN_GETS = [
    "/api/v1/admin/dashboard",
    "/api/v1/admin/voters",
    "/api/v1/admin/elections",
    "/api/v1/admin/audit-logs",
]


def iso(delta_hours):
    return (datetime.now(UTC) + timedelta(hours=delta_hours)).isoformat()


def new_election(admin_client, **overrides):
    body = {"title": "New Demo Election", "type": "councillorship", "scope": "all_lgas", "start_at": iso(24), "end_at": iso(30)}
    body.update(overrides)
    return admin_client.post("/api/v1/admin/elections", body)


class TestProtection:
    @pytest.mark.parametrize("path", ADMIN_GETS)
    def test_anonymous_gets_401(self, client, world, path):
        assert client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ADMIN_GETS)
    def test_voter_gets_403_and_is_audited(self, voter_client, world, path):
        assert voter_client("yn1").get(path).status_code == 403
        assert db.session.query(AuditLog).filter_by(event_type="security.permission_denied").count() >= 1

    def test_voter_cannot_mutate(self, voter_client, world):
        c = voter_client("yn1")
        eid = world["election"].id
        assert c.post(f"/api/v1/admin/elections/{eid}/close").status_code == 403
        assert (
            c.patch(f"/api/v1/admin/voters/{world['voters']['pending'].id}/verification", {"action": "verify"}).status_code == 403
        )
        assert c.post(f"/api/v1/admin/elections/{eid}/publish-results").status_code == 403
        assert db.session.get(Election, eid).status == "open"

    def test_auditor_read_only(self, make_client, world):
        world["admin"].role = "auditor"
        db.session.commit()
        c = make_client()
        c.login("admin@example.com", "AdminPass123")
        assert c.get("/api/v1/admin/audit-logs").status_code == 200
        assert c.get("/api/v1/admin/elections").status_code == 403


class TestDashboardAndVoters:
    def test_dashboard_counts(self, admin_client, world):
        data = admin_client.get("/api/v1/admin/dashboard").get_json()["data"]
        assert data["voters"]["verified"] == 7 and data["voters"]["pending"] == 1
        assert data["open_elections"] == 1
        assert any(a["type"] == "verify_voters" for a in data["pending_actions"])
        assert data["participation"][0]["eligible_voters"] == 6  # Yola North x4, Yola South, Numan

    def test_voter_listing_masks_pii_and_filters(self, admin_client, world):
        resp = admin_client.get("/api/v1/admin/voters?status=pending")
        rows = resp.get_json()["data"]
        assert len(rows) == 1 and rows[0]["verification_status"] == "pending"
        text = resp.get_data(as_text=True)
        assert "v6@example.com" not in text and "+2348030000006" not in text and "TESTVOTER" not in text
        lga = world["lgas"]["Yola South"].id
        assert len(admin_client.get(f"/api/v1/admin/voters?lga_id={lga}").get_json()["data"]) == 1
        meta = admin_client.get("/api/v1/admin/voters?per_page=2").get_json()["meta"]
        assert meta["per_page"] == 2 and meta["total"] == 8

    def test_text_search_uses_post_body(self, admin_client, world):
        assert admin_client.get("/api/v1/admin/voters?q=v1@example.com").status_code == 422
        by_email = admin_client.post("/api/v1/admin/voters/search", {"q": "v1@example.com"}).get_json()["data"]
        assert [r["id"] for r in by_email] == [world["voters"]["yn1"].id]
        by_vid = admin_client.post("/api/v1/admin/voters/search", {"q": "testvoter00002"}).get_json()["data"]
        assert [r["id"] for r in by_vid] == [world["voters"]["yn2"].id]
        by_name = admin_client.post("/api/v1/admin/voters/search", {"q": "VoterC"}).get_json()["data"]
        assert [r["id"] for r in by_name] == [world["voters"]["yn3"].id]

    def test_invalid_filters(self, admin_client, world):
        assert admin_client.get("/api/v1/admin/voters?status=bogus").status_code == 422
        assert admin_client.get("/api/v1/admin/voters?lga_id=abc").status_code == 422
        assert admin_client.get("/api/v1/admin/voters?page=0").status_code == 422

    def test_verification_flow(self, admin_client, voter_client, world):
        pending = world["voters"]["pending"]
        path = f"/api/v1/admin/voters/{pending.id}/verification"
        assert admin_client.patch(path, {"action": "reactivate"}).status_code == 409
        assert admin_client.patch(path, {"action": "reject"}).status_code == 422  # reason needed
        resp = admin_client.patch(path, {"action": "verify"})
        assert resp.status_code == 200 and resp.get_json()["data"]["verification_status"] == "verified"
        assert db.session.get(type(pending), pending.id).verified_by == world["admin"].id
        assert voter_client("pending").get(f"/api/v1/elections/{world['election'].id}/ballot").status_code == 200
        assert db.session.query(AuditLog).filter_by(event_type="voter.verify").count() == 1

    def test_suspend_revokes_sessions_and_blocks_voting(self, admin_client, voter_client, world):
        c = voter_client("yn1")
        assert c.get("/api/v1/me").status_code == 200
        path = f"/api/v1/admin/voters/{world['voters']['yn1'].id}/verification"
        assert admin_client.patch(path, {"action": "suspend", "reason": "Duplicate identity under review"}).status_code == 200
        assert c.get("/api/v1/me").status_code == 401
        assert c.login("v1@example.com", VOTER_PASSWORD).status_code == 403
        assert admin_client.patch(path, {"action": "reactivate"}).status_code == 200
        assert c.login("v1@example.com", VOTER_PASSWORD).status_code == 200

    def test_unknown_voter(self, admin_client, world):
        assert admin_client.patch("/api/v1/admin/voters/99999/verification", {"action": "verify"}).status_code == 404


class TestElections:
    def test_create_edit_and_lifecycle(self, admin_client, world):
        resp = new_election(admin_client)
        assert resp.status_code == 201
        e = resp.get_json()["data"]
        assert e["status"] == "draft" and e["editable"] and "schedule" in e["allowed_actions"]
        eid = e["id"]
        assert (
            admin_client.patch(f"/api/v1/admin/elections/{eid}", {"title": "Renamed Demo"}).get_json()["data"]["title"]
            == "Renamed Demo"
        )
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/schedule").get_json()["data"]["status"] == "scheduled"
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/open").status_code == 409  # no candidates
        lga = world["lgas"]["Yola North"].id
        assert (
            admin_client.post(
                f"/api/v1/admin/elections/{eid}/candidates", {"full_name": "Echo Candidate", "party_affiliation": "Demo Party"}
            ).status_code
            == 422
        )
        assert (
            admin_client.post(
                f"/api/v1/admin/elections/{eid}/candidates",
                {"full_name": "Echo Candidate", "party_affiliation": "Demo Party", "lga_id": lga},
            ).status_code
            == 201
        )
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/open").get_json()["data"]["status"] == "open"
        locked = admin_client.patch(f"/api/v1/admin/elections/{eid}", {"title": "Too late"})
        assert locked.status_code == 409 and locked.get_json()["error"]["code"] == "election_locked"
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/publish-results").status_code == 409
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/close").get_json()["data"]["status"] == "closed"
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/open").status_code == 409, "closed elections cannot reopen"
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/archive").get_json()["data"]["status"] == "archived"
        logged = {e.event_type for e in db.session.query(AuditLog).filter_by(entity_type="election", entity_id=str(eid))}
        assert {
            "election.created",
            "election.updated",
            "election.schedule",
            "election.open",
            "election.close",
            "election.archive",
        } <= logged

    def test_cancel_open_election_needs_reason(self, admin_client, world):
        eid = world["election"].id
        assert admin_client.post(f"/api/v1/admin/elections/{eid}/cancel").status_code == 422
        assert (
            admin_client.post(f"/api/v1/admin/elections/{eid}/cancel", {"reason": "Test cancellation"}).get_json()["data"][
                "status"
            ]
            == "cancelled"
        )

    def test_invalid_election_payloads(self, admin_client, world):
        assert new_election(admin_client, end_at=iso(1), start_at=iso(5)).status_code == 422
        assert new_election(admin_client, scope="single_lga").status_code == 422
        assert new_election(admin_client, scope="single_lga", lga_id=99999).status_code == 422
        assert new_election(admin_client, type="presidential").status_code == 422
        assert new_election(admin_client, status="open").status_code == 422  # unknown field

    def test_cannot_open_after_window(self, admin_client, world):
        e = new_election(admin_client, start_at=iso(-5), end_at=iso(-1)).get_json()["data"]
        db.session.add(
            Candidate(election_id=e["id"], lga_id=world["lgas"]["Numan"].id, full_name="Late Candidate", party_affiliation="DP")
        )
        db.session.commit()
        assert admin_client.post(f"/api/v1/admin/elections/{e['id']}/open").get_json()["error"]["code"] == "window_passed"

    def test_demo_override_allows_limited_edits(self, app, admin_client, world):
        eid = world["election"].id
        assert admin_client.patch(f"/api/v1/admin/elections/{eid}", {"title": "Edited"}).status_code == 409
        app.config["DEMO_ADMIN_OVERRIDE"] = True
        assert admin_client.patch(f"/api/v1/admin/elections/{eid}", {"title": "Edited"}).status_code == 200
        assert admin_client.patch(f"/api/v1/admin/elections/{eid}", {"scope": "single_lga"}).status_code == 409
        entry = db.session.query(AuditLog).filter_by(event_type="election.updated").one()
        assert entry.sanitized_description.startswith("[DEMO OVERRIDE]")


class TestCandidates:
    def test_candidate_rules_follow_election_state(self, admin_client, world):
        cand = world["candidates"]["yn_a"]
        # Election is open: candidates are locked.
        assert admin_client.patch(f"/api/v1/admin/candidates/{cand.id}", {"full_name": "Renamed"}).status_code == 409
        assert admin_client.delete(f"/api/v1/admin/candidates/{cand.id}").status_code == 409
        assert (
            admin_client.post(
                f"/api/v1/admin/elections/{world['election'].id}/candidates",
                {"full_name": "New Person", "party_affiliation": "DP", "lga_id": world["lgas"]["Numan"].id},
            ).status_code
            == 409
        )

    def test_candidate_crud_in_draft(self, admin_client, world):
        eid = new_election(admin_client, scope="single_lga", lga_id=world["lgas"]["Numan"].id).get_json()["data"]["id"]
        resp = admin_client.post(
            f"/api/v1/admin/elections/{eid}/candidates",
            {"full_name": "Foxtrot Candidate", "party_affiliation": "DP", "manifesto_summary": "Roads"},
        )
        assert resp.status_code == 201 and resp.get_json()["data"]["lga"]["name"] == "Numan"
        cid = resp.get_json()["data"]["id"]
        wrong = admin_client.post(
            f"/api/v1/admin/elections/{eid}/candidates",
            {"full_name": "Wrong Lga", "party_affiliation": "DP", "lga_id": world["lgas"]["Song"].id},
        )
        assert wrong.status_code == 422
        assert (
            admin_client.patch(f"/api/v1/admin/candidates/{cid}", {"status": "inactive"}).get_json()["data"]["status"]
            == "inactive"
        )
        assert len(admin_client.get(f"/api/v1/admin/elections/{eid}/candidates").get_json()["data"]) == 1
        assert admin_client.delete(f"/api/v1/admin/candidates/{cid}").status_code == 200
        assert admin_client.get(f"/api/v1/admin/elections/{eid}/candidates").get_json()["data"] == []
        assert admin_client.delete(f"/api/v1/admin/candidates/{cid}").status_code == 404

    def test_override_allows_deactivation_only(self, app, admin_client, world):
        app.config["DEMO_ADMIN_OVERRIDE"] = True
        cand = world["candidates"]["yn_a"]
        assert admin_client.patch(f"/api/v1/admin/candidates/{cand.id}", {"status": "inactive"}).status_code == 200
        assert admin_client.patch(f"/api/v1/admin/candidates/{cand.id}", {"full_name": "Renamed"}).status_code == 409


class TestAuditLog:
    def test_paginated_and_filterable(self, admin_client, voter_client, world):
        voter_client("yn1")
        admin_client.post(f"/api/v1/admin/elections/{world['election'].id}/close")
        resp = admin_client.get("/api/v1/admin/audit-logs?event_type=auth.&per_page=5")
        body = resp.get_json()
        assert resp.status_code == 200 and body["meta"]["per_page"] == 5
        assert all(e["event_type"].startswith("auth.") for e in body["data"])
        closed = admin_client.get("/api/v1/admin/audit-logs?entity_type=election").get_json()["data"]
        assert closed[0]["event_type"] == "election.close" and closed[0]["request_id"]
        assert admin_client.get("/api/v1/admin/audit-logs?from=not-a-date").status_code == 422
        entry = closed[0]
        assert set(entry) >= {"event_type", "actor_user_id", "created_at", "request_id", "description", "ip_hash"}
        assert entry["ip_hash"] != "127.0.0.1"
