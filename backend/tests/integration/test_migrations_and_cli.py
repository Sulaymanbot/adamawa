"""Migrations apply cleanly and CLI commands behave safely."""

import base64
import os
import secrets

import pytest
from flask_migrate import upgrade
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.models import Election, LocalGovernmentArea, User, Voter


@pytest.fixture
def file_app(tmp_path):
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'm.db'}"})
    with app.app_context():
        yield app
        db.session.remove()
        db.engine.dispose()


def test_migrations_create_full_schema(file_app):
    upgrade(directory=os.path.join(os.path.dirname(__file__), "..", "..", "migrations"))
    tables = set(inspect(db.engine).get_table_names())
    assert {
        "users",
        "voters",
        "admins",
        "local_government_areas",
        "wards",
        "polling_units",
        "elections",
        "candidates",
        "votes",
        "audit_logs",
        "otp_challenges",
        "user_sessions",
    } <= tables
    uniques = {tuple(u["column_names"]) for u in inspect(db.engine).get_unique_constraints("votes")}
    assert ("election_id", "voter_id") in uniques


def test_seed_and_demo_election_cli(file_app, monkeypatch):
    db.create_all()
    runner = file_app.test_cli_runner()
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminPass123")
    monkeypatch.setenv("DEMO_VOTER_PASSWORD", "VoterPass123")
    result = runner.invoke(args=["seed"])
    assert result.exit_code == 0, result.output
    assert "AdminPass123" not in result.output, "env-provided password must not be echoed"
    assert db.session.query(LocalGovernmentArea).count() == 21
    assert db.session.query(Voter).count() >= 20
    assert db.session.query(Voter).filter_by(verification_status="verified").count() == 20
    assert db.session.query(User).filter_by(role="admin").count() == 1
    assert runner.invoke(args=["seed"]).exit_code != 0, "seeding twice is refused"

    out = runner.invoke(args=["demo-election", "--open-now"])
    assert out.exit_code == 0 and "status=open" in out.output
    out = runner.invoke(args=["demo-election", "--close", "--publish"])
    assert out.exit_code == 0 and "published=True" in out.output
    e = db.session.query(Election).filter(Election.title.like("2026 Adamawa%")).one()
    assert e.status == "closed" and e.results_published_at is not None


def test_seed_generates_and_prints_password_once(file_app, monkeypatch):
    db.create_all()
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    result = file_app.test_cli_runner().invoke(args=["seed"])
    assert result.exit_code == 0
    assert "Admin pass  : Demo-" in result.output


def test_reset_demo_refused_outside_development(file_app):
    result = file_app.test_cli_runner().invoke(args=["reset-demo", "--yes"])
    assert result.exit_code != 0 and "FLASK_ENV=development" in result.output


def test_reset_demo_in_development(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", secrets.token_hex(32))
    monkeypatch.setenv("VOTE_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("IDENTIFIER_PEPPER", "pepper")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'dev.db'}")
    monkeypatch.setenv("ADMIN_PASSWORD", "AdminPass123")
    monkeypatch.setenv("DEMO_VOTER_PASSWORD", "VoterPass123")
    app = create_app("development", {"BCRYPT_ROUNDS": 4})
    with app.app_context():
        db.create_all()
        runner = app.test_cli_runner()
        assert runner.invoke(args=["seed"]).exit_code == 0
        assert runner.invoke(args=["reset-demo", "--yes"]).exit_code == 0
        assert db.session.query(User).count() == 0
        db.session.remove()
        db.engine.dispose()


def test_production_config_requires_secrets(monkeypatch):
    from app.config import ConfigError

    for key in ("SECRET_KEY", "VOTE_ENCRYPTION_KEY", "IDENTIFIER_PEPPER", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ConfigError):
        create_app("production")
