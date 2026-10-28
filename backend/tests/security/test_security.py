"""Security tests: injection, CSRF, rate limits, access control, sessions,
sensitive-data exposure and malformed input."""

import logging

import pytest

from app.extensions import db
from app.models import AuditLog, User, Vote, Voter
from app.models.audit import AuditLogImmutableError
from tests.conftest import VOTER_PASSWORD, registration_payload


def audit_count(event):
    return db.session.query(AuditLog).filter_by(event_type=event).count()


class TestInjection:
    @pytest.mark.parametrize("payload", ["' OR '1'='1", "admin@example.com' --", '" OR 1=1 #', "x'; DROP TABLE users; --"])
    def test_login_sql_injection(self, client, world, payload):
        resp = client.login(payload, payload)
        assert resp.status_code == 401
        assert db.session.query(User).count() == 9

    def test_search_sql_injection(self, admin_client, world):
        for q in ["' OR 1=1 --", "%", "_", "'; DROP TABLE voters; --"]:
            resp = admin_client.post("/api/v1/admin/voters/search", {"q": q})
            assert resp.status_code == 200
            assert resp.get_json()["data"] == []
        assert db.session.query(Voter).count() == 8

    def test_injection_in_registration_names_rejected(self, client, world):
        resp = client.post("/api/v1/auth/register", registration_payload(world, surname="x' OR 1=1; --"))
        assert resp.status_code == 422

    def test_non_integer_path_params(self, voter_client, world):
        c = voter_client("yn1")
        assert c.get("/api/v1/elections/1 OR 1=1/ballot").status_code == 404
        assert c.post("/api/v1/elections/1;DROP/votes", {"candidate_id": 1}).status_code == 404


class TestCsrf:
    def test_post_without_token_rejected(self, client, world):
        resp = client.post("/api/v1/auth/login", {"email": "v1@example.com", "password": VOTER_PASSWORD}, csrf=False)
        assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "csrf_failed"
        assert audit_count("security.csrf_rejected") == 1

    def test_forged_token_rejected(self, voter_client, world):
        c = voter_client("yn1")
        c.csrf = "forged.token.value"
        resp = c.post(f"/api/v1/elections/{world['election'].id}/votes", {"candidate_id": world["candidates"]["yn_a"].id})
        assert resp.status_code == 400
        assert db.session.query(Vote).count() == 0

    def test_token_from_other_session_rejected(self, make_client, world):
        attacker, victim = make_client(), make_client()
        attacker.refresh_csrf()
        victim.login("v1@example.com", VOTER_PASSWORD)
        victim.csrf = attacker.csrf
        resp = victim.post(f"/api/v1/elections/{world['election'].id}/votes", {"candidate_id": world["candidates"]["yn_a"].id})
        assert resp.status_code == 400


RATE_LIMITED = {"RATELIMIT_ENABLED": True, "LOGIN_RATE_LIMIT": "3 per minute", "VOTE_RATE_LIMIT": "2 per minute"}


@pytest.mark.parametrize("app", [RATE_LIMITED], indirect=True)
class TestRateLimiting:
    def test_login_rate_limit(self, client, world):
        codes = [client.login("v1@example.com", "wrong-password-1").status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429]
        resp = client.login("v1@example.com", VOTER_PASSWORD)
        assert resp.status_code == 429, "correct password is also blocked while limited"
        assert resp.get_json()["error"]["code"] == "rate_limited"
        assert audit_count("security.rate_limited") >= 1

    def test_vote_rate_limit(self, voter_client, world):
        c = voter_client("yn1")
        url = f"/api/v1/elections/{world['election'].id}/votes"
        codes = [c.post(url, {"candidate_id": 99999}).status_code for _ in range(3)]
        assert codes == [422, 422, 429]


class TestAccessControl:
    def test_voter_cannot_escalate_via_registration(self, client, world):
        resp = client.post("/api/v1/auth/register", {**registration_payload(world), "role": "admin"})
        assert resp.status_code == 422
        assert db.session.query(User).filter_by(role="admin").count() == 1

    def test_voter_cannot_vote_in_out_of_scope_election(self, voter_client, world):
        e = world["election"]
        yola_south = world["lgas"]["Yola South"].id
        e.scope, e.lga_id = "single_lga", yola_south
        db.session.commit()
        resp = voter_client("yn1").post(f"/api/v1/elections/{e.id}/votes", {"candidate_id": world["candidates"]["ys_a"].id})
        assert resp.status_code == 404
        assert db.session.query(Vote).count() == 0

    def test_admin_pages_forbidden_for_voters(self, voter_client, world):
        c = voter_client("yn1")
        for path in ("/admin", "/admin/voters", "/admin/elections", "/admin/audit-logs"):
            assert c.get(path).status_code == 403, path

    def test_audit_log_is_append_only(self, world, client):
        client.login("v1@example.com", VOTER_PASSWORD)
        entry = db.session.query(AuditLog).first()
        entry.sanitized_description = "tampered"
        with pytest.raises(AuditLogImmutableError):
            db.session.commit()
        db.session.rollback()
        with pytest.raises(AuditLogImmutableError):
            db.session.delete(db.session.query(AuditLog).first())
            db.session.commit()
        db.session.rollback()


class TestSessions:
    def test_session_fixation_prevented(self, make_client, world):
        victim = make_client()
        victim.refresh_csrf()
        pre_login = victim.c.get_cookie("adv_session").value
        victim.login("v1@example.com", VOTER_PASSWORD)
        post_login = victim.c.get_cookie("adv_session").value
        assert pre_login != post_login
        attacker = make_client()
        attacker.c.set_cookie("adv_session", pre_login)
        assert attacker.get("/api/v1/me").status_code == 401

    def test_stolen_cookie_useless_after_logout(self, make_client, world):
        victim = make_client()
        victim.login("v1@example.com", VOTER_PASSWORD)
        stolen = victim.c.get_cookie("adv_session").value
        victim.post("/api/v1/auth/logout")
        attacker = make_client()
        attacker.c.set_cookie("adv_session", stolen)
        assert attacker.get("/api/v1/me").status_code == 401

    def test_tampered_cookie_rejected(self, make_client, world):
        c = make_client()
        c.login("v1@example.com", VOTER_PASSWORD)
        value = c.c.get_cookie("adv_session").value
        c.c.set_cookie("adv_session", value[:-2] + ("AA" if not value.endswith("AA") else "BB"))
        assert c.get("/api/v1/me").status_code == 401

    def test_cookie_flags(self, client, world):
        resp = client.login("v1@example.com", VOTER_PASSWORD)
        cookie = resp.headers.get("Set-Cookie")
        assert "HttpOnly" in cookie and "SameSite=Lax" in cookie

    def test_session_cookie_contains_no_user_data(self, client, world):
        client.login("v1@example.com", VOTER_PASSWORD)
        import base64
        import zlib

        raw = client.c.get_cookie("adv_session").value
        payload = raw.lstrip(".").split(".")[0]
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        if raw.startswith("."):
            decoded = zlib.decompress(decoded)
        text = decoded.decode()
        assert "v1@example.com" not in text and "voter" not in text and "sid" in text


class TestSensitiveData:
    def test_no_secrets_in_logs(self, make_client, world, caplog):
        caplog.set_level(logging.DEBUG)
        c = make_client()
        c.post("/api/v1/auth/register", registration_payload(world))
        c.login("new.voter@example.com", "StrongPass99")
        v = make_client()
        v.login("v1@example.com", VOTER_PASSWORD)
        receipt = v.post(
            f"/api/v1/elections/{world['election'].id}/votes", {"candidate_id": world["candidates"]["yn_b"].id}
        ).get_json()["data"]["receipt_reference"]
        logs = caplog.text + " ".join(str(r.__dict__) for r in caplog.records)
        for secret in (
            "StrongPass99",
            VOTER_PASSWORD,
            "NEWV00001111",
            "newv-0000-1111",
            "Bravo Candidate",
            receipt,
            "+2348035551234",
        ):
            assert secret not in logs, secret

    def test_responses_never_include_hashes_or_ballots(self, admin_client, voter_client, world):
        voter_client("yn1").post(
            f"/api/v1/elections/{world['election'].id}/votes", {"candidate_id": world["candidates"]["yn_a"].id}
        )
        texts = [
            admin_client.get("/api/v1/admin/voters").get_data(as_text=True),
            admin_client.get("/api/v1/admin/dashboard").get_data(as_text=True),
            admin_client.get("/api/v1/admin/elections").get_data(as_text=True),
            admin_client.get("/api/v1/admin/audit-logs").get_data(as_text=True),
        ]
        for text in texts:
            assert "password_hash" not in text and "$2b$" not in text
            assert "voter_id_hash" not in text and "encrypted_vote_payload" not in text
            assert "Alpha Candidate" not in text  # no ballot choice anywhere in admin views

    def test_audit_descriptions_sanitised(self, app, world):
        from app.services import audit_service

        with app.test_request_context():
            entry = audit_service.record("test.event", "Contact aisha@example.com on 08031234567\x00\nnow" + "x" * 600)
        assert "aisha@example.com" not in entry.sanitized_description
        assert "08031234567" not in entry.sanitized_description
        assert "\x00" not in entry.sanitized_description and len(entry.sanitized_description) <= 500


class TestMalformedInput:
    def test_non_json_body(self, client, world):
        client.refresh_csrf()
        resp = client.c.post(
            "/api/v1/auth/login",
            data="email=x",
            headers={"X-CSRFToken": client.csrf, "Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 415

    def test_invalid_json(self, client, world):
        client.refresh_csrf()
        resp = client.c.post(
            "/api/v1/auth/login", data="{not json", headers={"X-CSRFToken": client.csrf, "Content-Type": "application/json"}
        )
        assert resp.status_code == 400 and resp.get_json()["error"]["code"] == "malformed_json"

    def test_json_array_body(self, client, world):
        assert client.post("/api/v1/auth/login", ["a", "b"]).status_code == 400

    def test_oversized_body(self, client, world):
        resp = client.post("/api/v1/auth/register", {"surname": "x" * 70000})
        assert resp.status_code == 413

    def test_wrong_types(self, voter_client, world):
        c = voter_client("yn1")
        url = f"/api/v1/elections/{world['election'].id}/votes"
        for body in ({"candidate_id": "1"}, {"candidate_id": None}, {}, {"candidate_id": [1]}, {"candidate_id": 2**40}):
            assert c.post(url, body).status_code == 422, body

    def test_unexpected_error_is_generic(self, admin_client, world, monkeypatch):
        from app.services import dashboard_service

        def boom():
            raise RuntimeError("secret internal detail")

        monkeypatch.setattr(dashboard_service, "summary", boom)
        resp = admin_client.get("/api/v1/admin/dashboard")
        assert resp.status_code == 500
        assert "secret internal detail" not in resp.get_data(as_text=True)
        assert resp.get_json()["error"]["code"] == "server_error"


class TestHeaders:
    def test_security_headers(self, client, world):
        for path in ("/", "/api/v1/locations/lgas"):
            resp = client.get(path)
            assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
            assert "frame-ancestors 'none'" in resp.headers["Content-Security-Policy"]
            assert resp.headers["X-Frame-Options"] == "DENY"
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert resp.headers["Referrer-Policy"] == "same-origin"
            assert resp.headers["Cache-Control"] == "no-store"
            assert resp.headers["X-Request-ID"]

    def test_cors_only_for_allowed_origins(self, app, client, world):
        resp = client.get("/api/v1/locations/lgas", headers={"Origin": "https://evil.example"})
        assert "Access-Control-Allow-Origin" not in resp.headers
        app.config["CORS_ORIGINS"] = ["https://trusted.example"]
        resp = client.get("/api/v1/locations/lgas", headers={"Origin": "https://trusted.example"})
        assert resp.headers["Access-Control-Allow-Origin"] == "https://trusted.example"

    def test_open_redirect_blocked(self, client, world):
        page = client.get("/login?next=//evil.example/phish").get_data(as_text=True)
        assert "evil.example" not in page
        page = client.get("/login?next=/dashboard").get_data(as_text=True)
        assert 'data-next="/dashboard"' in page
