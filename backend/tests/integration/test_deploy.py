"""Hosting/deployment behaviour: health check, proxy handling, DB URL, demo seeding guard."""

import base64
import os
import secrets

import pytest

from app import create_app
from app.config import engine_options, normalize_database_url
from app.extensions import db
from app.models import User


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200 and resp.get_json() == {"status": "ok"}


def test_mysql_url_normalised():
    assert normalize_database_url("mysql://u:p@h:3306/d") == "mysql+pymysql://u:p@h:3306/d"
    assert normalize_database_url("mysql+pymysql://u:p@h/d") == "mysql+pymysql://u:p@h/d"
    assert normalize_database_url(None) is None


def test_ca_pem_written_and_used(monkeypatch):
    monkeypatch.delenv("DB_SSL_CA", raising=False)
    monkeypatch.setenv("DB_SSL_CA_PEM", "-----BEGIN CERTIFICATE-----\\nABC\\n-----END CERTIFICATE-----")
    opts = engine_options()
    ssl = opts["connect_args"]["ssl"]
    assert ssl["check_hostname"] is True
    with open(ssl["ca"]) as fh:
        assert fh.read().startswith("-----BEGIN CERTIFICATE-----\nABC\n")


def test_no_tls_args_without_ca(monkeypatch):
    monkeypatch.delenv("DB_SSL_CA", raising=False)
    monkeypatch.delenv("DB_SSL_CA_PEM", raising=False)
    assert "connect_args" not in engine_options()


@pytest.fixture
def prod_app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("VOTE_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("IDENTIFIER_PEPPER", "pepper")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'prod.db'}")
    for key in ("TEST_ADMIN_PASSWORD", "TEST_VOTER_PASSWORD", "DB_SSL_CA", "DB_SSL_CA_PEM"):
        monkeypatch.delenv(key, raising=False)

    def make(**overrides):
        app = create_app("production", {"BCRYPT_ROUNDS": 4, **overrides})
        ctx = app.app_context()
        ctx.push()
        db.create_all()
        return app, ctx

    made = []
    yield lambda **o: made.append(make(**o)) or made[-1][0]
    for _, ctx in made:
        db.session.remove()
        db.engine.dispose()
        ctx.pop()


def test_seed_blocked_in_production_without_flag(prod_app):
    app = prod_app()
    result = app.test_cli_runner().invoke(args=["seed-test-users"])
    assert result.exit_code != 0 and "ALLOW_DEMO_SEED" in result.output


def test_seed_requires_explicit_passwords_in_production(prod_app):
    app = prod_app(ALLOW_DEMO_SEED=True)
    result = app.test_cli_runner().invoke(args=["seed-test-users"])
    assert result.exit_code != 0 and "TEST_ADMIN_PASSWORD" in result.output
    assert db.session.query(User).count() == 0


def test_seed_with_passwords_and_if_empty_is_idempotent(prod_app, monkeypatch):
    monkeypatch.setenv("TEST_ADMIN_PASSWORD", "StrongAdmin2026")
    monkeypatch.setenv("TEST_VOTER_PASSWORD", "StrongVoter2026")
    app = prod_app(ALLOW_DEMO_SEED=True)
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed-test-users", "--if-empty"]).exit_code == 0
    assert db.session.query(User).count() == 6
    again = runner.invoke(args=["seed-test-users", "--if-empty"])
    assert again.exit_code == 0 and "skipping" in again.output
    assert db.session.query(User).count() == 6


def test_weak_seed_password_rejected(prod_app, monkeypatch):
    monkeypatch.setenv("TEST_ADMIN_PASSWORD", "short")
    monkeypatch.setenv("TEST_VOTER_PASSWORD", "StrongVoter2026")
    app = prod_app(ALLOW_DEMO_SEED=True)
    assert app.test_cli_runner().invoke(args=["seed-test-users"]).exit_code != 0


def test_proxy_headers_trusted_only_when_enabled(prod_app):
    app = prod_app(TRUST_PROXY=True)
    resp = app.test_client().get("/healthz", headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.9"})
    assert resp.status_code == 200
    assert resp.headers.get("Strict-Transport-Security")
