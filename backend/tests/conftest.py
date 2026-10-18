"""Shared fixtures. Tests run on in-memory SQLite with freshly generated keys."""

from __future__ import annotations

import os

os.environ["ADV_SKIP_DOTENV"] = "1"  # never read the developer's backend/.env in tests

from datetime import timedelta  # noqa: E402

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Candidate, Election, utcnow  # noqa: E402
from app.services import seed_service  # noqa: E402

VOTER_PASSWORD = "VoterPass123"
ADMIN_PASSWORD = "AdminPass123"


class Client:
    """Test client wrapper that handles CSRF tokens and JSON envelopes."""

    def __init__(self, flask_client):
        self.c = flask_client
        self.csrf = None

    def refresh_csrf(self):
        self.csrf = self.c.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]

    def _send(self, method, path, json=None, headers=None, csrf=True):
        headers = dict(headers or {})
        if csrf:
            if self.csrf is None:
                self.refresh_csrf()
            headers["X-CSRFToken"] = self.csrf
        resp = getattr(self.c, method)(path, json=json, headers=headers)
        body = resp.get_json(silent=True) or {}
        data = body.get("data")
        if isinstance(data, dict) and data.get("csrf_token"):
            self.csrf = data["csrf_token"]
        return resp

    def get(self, path, **kw):
        return self.c.get(path, **kw)

    def post(self, path, json=None, headers=None, csrf=True):
        return self._send("post", path, json, headers, csrf)

    def patch(self, path, json=None, csrf=True):
        return self._send("patch", path, json, None, csrf)

    def delete(self, path, csrf=True):
        return self._send("delete", path, None, None, csrf)

    def login(self, email, password):
        return self.post("/api/v1/auth/login", {"email": email, "password": password})


@pytest.fixture
def app(request):
    overrides = getattr(request, "param", None)
    application = create_app("testing", overrides)

    # Tests hold one app context open, so every test-client request shares the
    # same `g`. In production each request gets a fresh context; emulate that
    # for the per-request values Flask-WTF caches on `g`.
    def _fresh_request_globals():
        from flask import g

        g.pop("csrf_token", None)

    application.before_request_funcs.setdefault(None, []).insert(0, _fresh_request_globals)
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def make_client(app):
    return lambda: Client(app.test_client())


@pytest.fixture
def client(make_client):
    return make_client()


@pytest.fixture
def world(app):
    """Locations, an admin, voters and one open all-LGA election with candidates."""
    lgas = seed_service.seed_locations()
    admin = seed_service.create_admin("admin@example.com", ADMIN_PASSWORD)
    from app.security.passwords import hash_password

    pw = hash_password(VOTER_PASSWORD)

    def voter(n, lga_name, status="verified"):
        lga = lgas[lga_name]
        ward = lga.wards[0]
        return seed_service.create_voter(
            email=f"v{n}@example.com",
            phone=f"+2348030000{n:03d}",
            voter_id=f"TESTVOTER{n:05d}",
            first_name="Test",
            surname=f"Voter{chr(64 + n)}",
            lga=lga,
            ward=ward,
            polling_unit=ward.polling_units[0],
            password_hash=pw,
            status=status,
            verified_by=admin.id,
        )

    voters = {
        "yn1": voter(1, "Yola North"),
        "yn2": voter(2, "Yola North"),
        "yn3": voter(3, "Yola North"),
        "yn4": voter(4, "Yola North"),
        "ys1": voter(5, "Yola South"),
        "pending": voter(6, "Yola North", "pending"),
        "numan": voter(7, "Numan"),
        "song": voter(8, "Song"),  # no candidates in Song
    }
    now = utcnow()
    election = Election(
        title="Test LG Chairmanship (SIMULATED)",
        type="lg_chairmanship",
        scope="all_lgas",
        start_at=now - timedelta(hours=1),
        end_at=now + timedelta(hours=5),
        status="open",
        created_by=admin.id,
    )
    db.session.add(election)
    db.session.flush()
    cands = {}
    for key, lga_name, name in [
        ("yn_a", "Yola North", "Alpha Candidate"),
        ("yn_b", "Yola North", "Bravo Candidate"),
        ("ys_a", "Yola South", "Charlie Candidate"),
        ("num_a", "Numan", "Delta Candidate"),
    ]:
        c = Candidate(
            election_id=election.id, lga_id=lgas[lga_name].id, full_name=name, party_affiliation="Demo Party", status="active"
        )
        db.session.add(c)
        cands[key] = c
    db.session.commit()
    return {"lgas": lgas, "admin": admin, "voters": voters, "election": election, "candidates": cands}


@pytest.fixture
def admin_client(make_client, world):
    c = make_client()
    assert c.login("admin@example.com", ADMIN_PASSWORD).status_code == 200
    return c


@pytest.fixture
def voter_client(make_client, world):
    def _login(key="yn1"):
        c = make_client()
        email = world["voters"][key].user.email
        resp = c.login(email, VOTER_PASSWORD)
        assert resp.status_code == 200, resp.get_json()
        return c

    return _login


def registration_payload(world, **overrides):
    lga = world["lgas"]["Yola North"]
    ward = lga.wards[0]
    data = {
        "surname": "Newvoter",
        "first_name": "Amina",
        "other_names": None,
        "email": "New.Voter@Example.com",
        "phone": "0803 555 1234",
        "voter_id": "newv-0000-1111",
        "lga_id": lga.id,
        "ward_id": ward.id,
        "polling_unit_id": ward.polling_units[0].id,
        "password": "StrongPass99",
        "confirm_password": "StrongPass99",
        "demo_acknowledged": True,
    }
    data.update(overrides)
    return data
