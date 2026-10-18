"""Registration, login/logout, sessions and OTP over the HTTP API."""

from datetime import timedelta

from app.extensions import db
from app.models import AuditLog, User, UserSession, Voter
from tests.conftest import VOTER_PASSWORD, registration_payload


def events():
    return [e.event_type for e in db.session.query(AuditLog).order_by(AuditLog.id)]


class TestRegistration:
    def test_register_creates_pending_voter_with_normalised_hashed_data(self, client, world):
        resp = client.post("/api/v1/auth/register", registration_payload(world))
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["ok"] and body["data"]["verification_status"] == "pending"
        assert body["request_id"]
        user = db.session.query(User).filter_by(email="new.voter@example.com").one()
        assert user.phone == "+2348035551234"
        assert user.password_hash.startswith("$2b$") and "StrongPass99" not in user.password_hash
        voter = user.voter
        assert voter.voter_id_last4 == "1111"
        assert "NEWV00001111" not in voter.voter_id_hash
        assert "voter.registered" in events()

    def test_duplicates_rejected_after_normalisation(self, client, world):
        assert client.post("/api/v1/auth/register", registration_payload(world)).status_code == 201
        variants = [
            {"email": "  NEW.VOTER@example.com "},  # same email, different case
            {"email": "other@example.com", "phone": "+234 803 555 1234"},  # same phone, other format
            {"email": "other@example.com", "phone": "08099999999", "voter_id": "NEWV 0000 1111"},  # same voter id
        ]
        for override in variants:
            resp = client.post("/api/v1/auth/register", registration_payload(world, **override))
            assert resp.status_code == 409, override
            assert resp.get_json()["error"]["code"] == "duplicate_account"
        assert db.session.query(Voter).count() == len(world["voters"]) + 1

    def test_location_hierarchy_enforced(self, client, world):
        other_ward = world["lgas"]["Numan"].wards[0]
        resp = client.post("/api/v1/auth/register", registration_payload(world, ward_id=other_ward.id))
        assert resp.status_code == 422
        assert resp.get_json()["error"]["details"][0]["field"] == "polling_unit_id"

    def test_validation_errors_listed_per_field(self, client, world):
        resp = client.post("/api/v1/auth/register", {"surname": "", "email": "bad"})
        assert resp.status_code == 422
        fields = {d["field"] for d in resp.get_json()["error"]["details"]}
        assert {"surname", "email", "phone", "password", "lga_id"} <= fields

    def test_registered_voter_cannot_vote_until_verified(self, make_client, world):
        c = make_client()
        c.post("/api/v1/auth/register", registration_payload(world))
        assert c.login("new.voter@example.com", "StrongPass99").status_code == 200
        me = c.get("/api/v1/me").get_json()["data"]
        assert me["voter"]["verification_status"] == "pending"
        e = world["election"].id
        assert c.get(f"/api/v1/elections/{e}/ballot").status_code == 403


class TestLogin:
    def test_login_success_and_me(self, client, world):
        resp = client.login("v1@example.com", VOTER_PASSWORD)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["user"]["role"] == "voter" and data["redirect"] == "/dashboard"
        me = client.get("/api/v1/me").get_json()["data"]
        assert me["email_masked"] == "v***@e***.com"
        assert me["voter"]["voter_id_masked"].endswith("0001")
        assert "password_hash" not in str(me)
        assert "auth.login_success" in events()

    def test_generic_error_for_wrong_password_and_unknown_user(self, client, world):
        a = client.login("v1@example.com", "wrong-password-1")
        b = client.login("nobody@example.com", "wrong-password-1")
        assert a.status_code == b.status_code == 401
        assert a.get_json()["error"]["message"] == b.get_json()["error"]["message"] == "Email or password is incorrect."
        assert events().count("auth.login_failed") == 2

    def test_suspended_account_cannot_login(self, client, world):
        world["voters"]["yn1"].user.status = "suspended"
        db.session.commit()
        resp = client.login("v1@example.com", VOTER_PASSWORD)
        assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "account_inactive"

    def test_logout_revokes_server_session(self, client, world):
        client.login("v1@example.com", VOTER_PASSWORD)
        assert client.get("/api/v1/me").status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/me").status_code == 401
        assert db.session.query(UserSession).filter(UserSession.revoked_at.is_(None)).count() == 0

    def test_idle_session_expires(self, client, world):
        client.login("v1@example.com", VOTER_PASSWORD)
        s = db.session.query(UserSession).one()
        s.last_seen_at = s.last_seen_at - timedelta(minutes=31)
        db.session.commit()
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401 and resp.get_json()["error"]["code"] == "session_expired"

    def test_absolute_session_expiry(self, client, world):
        client.login("v1@example.com", VOTER_PASSWORD)
        s = db.session.query(UserSession).one()
        s.expires_at = s.created_at
        db.session.commit()
        assert client.get("/api/v1/me").status_code == 401

    def test_protected_routes_need_auth(self, client, world):
        for path in ("/api/v1/me", "/api/v1/elections", f"/api/v1/elections/{world['election'].id}/ballot"):
            resp = client.get(path)
            assert resp.status_code == 401, path
            assert resp.get_json()["error"]["code"] == "unauthenticated"


class TestOtp:
    def test_otp_flow(self, app, client, world):
        app.config["OTP_ENABLED"] = True
        resp = client.login("v1@example.com", VOTER_PASSWORD)
        assert resp.get_json()["data"]["otp_required"] is True
        assert client.get("/api/v1/me").status_code == 401, "password alone must not create a session"
        code = app.extensions["otp_outbox"][-1]["code"]
        wrong = "000000" if code != "000000" else "111111"
        bad = client.post("/api/v1/auth/otp/verify", {"code": wrong})
        assert bad.status_code == 401 and bad.get_json()["error"]["code"] == "otp_invalid"
        ok = client.post("/api/v1/auth/otp/verify", {"code": code})
        assert ok.status_code == 200
        assert client.get("/api/v1/me").status_code == 200
        # Codes are single use and stored hashed.
        from app.models import OtpChallenge

        ch = db.session.query(OtpChallenge).order_by(OtpChallenge.id.desc()).first()
        assert ch.consumed_at is not None and code not in ch.code_hash

    def test_otp_attempt_limit(self, app, client, world):
        app.config["OTP_ENABLED"] = True
        client.login("v1@example.com", VOTER_PASSWORD)
        code = app.extensions["otp_outbox"][-1]["code"]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(app.config["OTP_MAX_ATTEMPTS"]):
            client.post("/api/v1/auth/otp/verify", {"code": wrong})
        locked = client.post("/api/v1/auth/otp/verify", {"code": code})
        assert locked.status_code == 400 and locked.get_json()["error"]["code"] == "otp_locked"

    def test_otp_resend_invalidates_previous_code(self, app, client, world):
        app.config["OTP_ENABLED"] = True
        client.login("v1@example.com", VOTER_PASSWORD)
        first = app.extensions["otp_outbox"][-1]["code"]
        assert client.post("/api/v1/auth/otp/request").status_code == 200
        second = app.extensions["otp_outbox"][-1]["code"]
        if first != second:
            assert client.post("/api/v1/auth/otp/verify", {"code": first}).status_code in (400, 401)
        assert client.post("/api/v1/auth/otp/verify", {"code": second}).status_code == 200

    def test_otp_without_pending_login(self, client, world):
        resp = client.post("/api/v1/auth/otp/verify", {"code": "123456"})
        assert resp.status_code == 401 and resp.get_json()["error"]["code"] == "otp_session_missing"
