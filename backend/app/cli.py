"""Flask CLI commands: seed, reset-demo, demo-election, create-admin, openapi."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

import click
from flask import Flask, current_app

from app.extensions import db
from app.models import Election, utcnow
from app.services import audit_service, seed_service

DEMO_ELECTION_TITLE = "2026 Adamawa LG Chairmanship Election (SIMULATED)"


def _require_dev(action: str) -> None:
    if current_app.config["APP_ENV"] not in {"development", "testing"}:
        raise click.ClickException(f"`{action}` only runs when FLASK_ENV=development.")


def register_cli(app: Flask) -> None:
    @app.cli.command("seed")
    def seed():
        """Create demo LGAs, wards, polling units, admin, 24 voters and a demo election."""
        _require_dev("seed")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        admin_password = os.environ.get("ADMIN_PASSWORD") or seed_service.generate_password()
        voter_password = os.environ.get("DEMO_VOTER_PASSWORD") or seed_service.generate_password()
        try:
            result = seed_service.seed_demo(admin_email=admin_email, admin_password=admin_password, voter_password=voter_password)
        except RuntimeError as exc:
            raise click.ClickException(str(exc)) from None
        audit_service.record("system.seeded", "Demo data seeded via CLI", actor_user_id=result["admin"].id)
        click.secho("\nDEMO DATA CREATED (fictional – simulated election only)", fg="yellow", bold=True)
        click.echo(f"  LGAs: 21   demo voters: {len(result['voters'])}   demo election id: {result['election'].id}")
        click.echo("\nThese credentials are shown ONCE. Copy them now.")
        click.echo(f"  Admin login : {admin_email}")
        click.echo(
            f"  Admin pass  : {admin_password if not os.environ.get('ADMIN_PASSWORD') else '(from ADMIN_PASSWORD in .env)'}"
        )
        click.echo("  Voter logins: voter01@example.com … voter24@example.com")
        click.echo("               (voter21–23 pending, voter24 rejected, others verified)")
        shown_voter_pw = "(from DEMO_VOTER_PASSWORD in .env)" if os.environ.get("DEMO_VOTER_PASSWORD") else voter_password
        click.echo(f"  Voter pass  : {shown_voter_pw}")
        click.echo("\nThe demo election is scheduled for tomorrow. Open it now with:")
        click.echo("  flask demo-election --open-now\n")

    @app.cli.command("seed-test-users")
    @click.option("--if-empty", "if_empty", is_flag=True, help="Do nothing (exit 0) if users already exist.")
    def seed_test_users(if_empty: bool):
        """Create only LGAs (with wards/polling units), 1 admin and 5 verified voters. No elections."""
        from app.models import User
        from app.schemas import validate_password_strength
        from app.security.passwords import hash_password

        is_dev = current_app.config["APP_ENV"] in {"development", "testing"}
        if not is_dev and not current_app.config.get("ALLOW_DEMO_SEED"):
            raise click.ClickException("seed-test-users is disabled here. Set ALLOW_DEMO_SEED=true to allow it.")
        if db.session.execute(db.select(User.id)).first():
            if if_empty:
                click.echo("Users already exist; skipping test-user seed.")
                return
            raise click.ClickException("Database is not empty. Run `flask reset-demo --yes` first.")
        admin_password = os.environ.get("TEST_ADMIN_PASSWORD") or ("Admin12345" if is_dev else None)
        voter_password = os.environ.get("TEST_VOTER_PASSWORD") or ("Voter12345" if is_dev else None)
        if not admin_password or not voter_password:
            raise click.ClickException(
                "Set TEST_ADMIN_PASSWORD and TEST_VOTER_PASSWORD (public servers must not use default passwords)."
            )
        for pw in (admin_password, voter_password):
            try:
                validate_password_strength(pw)
            except ValueError as exc:
                raise click.ClickException(f"Test password rejected: {exc}") from None
        lgas = seed_service.seed_locations()
        admin = seed_service.create_admin("admin@example.com", admin_password, "Test Officer")
        voter_hash = hash_password(voter_password)
        people = [
            ("Aisha", "Bello", "Yola North"),
            ("Musa", "Garba", "Yola North"),
            ("Grace", "Yohanna", "Yola North"),
            ("Ibrahim", "Lawan", "Yola South"),
            ("Fatima", "Usman", "Mubi North"),
        ]
        for i, (first, last, lga_name) in enumerate(people, start=1):
            lga = lgas[lga_name]
            ward = lga.wards[0]
            seed_service.create_voter(
                email=f"voter{i}@example.com",
                phone=f"+2348030000{i:03d}",
                voter_id=f"TESTVOTER{i:05d}",
                first_name=first,
                surname=last,
                lga=lga,
                ward=ward,
                polling_unit=ward.polling_units[0],
                password_hash=voter_hash,
                status="verified",
                verified_by=admin.id,
            )
        audit_service.record("system.seeded", "Test users seeded via CLI", actor_user_id=admin.id, commit=False)
        db.session.commit()
        click.echo(f"Created 21 LGAs, 1 admin and {len(people)} verified voters (no elections).")

    @app.cli.command("reset-demo")
    @click.option("--yes", is_flag=True, help="Confirm you want to DELETE ALL DATA.")
    def reset_demo(yes: bool):
        """DESTRUCTIVE: delete all data in the local database (development only)."""
        if current_app.config["APP_ENV"] != "development":
            raise click.ClickException("reset-demo refuses to run unless FLASK_ENV=development.")
        if not yes:
            click.confirm("This DELETES ALL DATA in the local database. Continue?", abort=True)
        seed_service.wipe_all_data()
        click.secho("All data deleted. Run `flask seed` to recreate demo data.", fg="red")

    @app.cli.command("demo-election")
    @click.option("--open-now", "open_now", is_flag=True, help="Open voting now for --hours hours.")
    @click.option("--close", "close", is_flag=True, help="Close voting now.")
    @click.option("--publish", "publish", is_flag=True, help="Publish results (election must be closed).")
    @click.option("--hours", default=2, show_default=True, type=int)
    @click.option("--election-id", type=int, default=None, help="Defaults to the seeded demo election.")
    def demo_election(open_now: bool, close: bool, publish: bool, hours: int, election_id: int | None):
        """Control the demo election's schedule from the command line."""
        _require_dev("demo-election")
        if election_id:
            election = db.session.get(Election, election_id)
        else:
            election = db.session.execute(db.select(Election).filter_by(title=DEMO_ELECTION_TITLE)).scalars().first()
        if election is None:
            raise click.ClickException("Demo election not found. Run `flask seed` first.")
        now = utcnow()
        if open_now:
            election.start_at = now - timedelta(minutes=1)
            election.end_at = now + timedelta(hours=hours)
            election.status = "open"
            election.results_published_at = None
            audit_service.record(
                "election.open",
                f"[CLI] Election #{election.id} opened for {hours}h",
                entity_type="election",
                entity_id=election.id,
                commit=False,
            )
        if close:
            election.status = "closed"
            election.end_at = min(election.end_at, now)
            if election.start_at >= election.end_at:
                election.start_at = election.end_at - timedelta(minutes=1)
            audit_service.record(
                "election.close",
                f"[CLI] Election #{election.id} closed",
                entity_type="election",
                entity_id=election.id,
                commit=False,
            )
        if publish:
            if election.status != "closed":
                raise click.ClickException("Close the election before publishing results.")
            election.results_published_at = now
            audit_service.record(
                "election.results_published",
                f"[CLI] Results published for election #{election.id}",
                entity_type="election",
                entity_id=election.id,
                commit=False,
            )
        db.session.commit()
        click.echo(
            f"Election #{election.id}: status={election.status} start={election.start_at:%Y-%m-%d %H:%M}Z "
            f"end={election.end_at:%Y-%m-%d %H:%M}Z published={election.results_published_at is not None}"
        )

    @app.cli.command("create-admin")
    @click.option("--email", required=True)
    @click.option("--name", "full_name", default="Electoral Officer")
    @click.password_option()
    def create_admin(email: str, full_name: str, password: str):
        """Create an administrator account."""
        from app.schemas import validate_password_strength

        try:
            validate_password_strength(password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from None
        user = seed_service.create_admin(email, password, full_name)
        audit_service.record(
            "admin.created", f"Administrator #{user.id} created via CLI", entity_type="user", entity_id=user.id, commit=False
        )
        db.session.commit()
        click.echo(f"Admin #{user.id} created.")

    @app.cli.command("openapi")
    @click.option("--out", default=str(Path(__file__).resolve().parents[2] / "docs" / "openapi.json"))
    def openapi(out: str):
        """Write the OpenAPI document to docs/openapi.json."""
        from app.api.docs import build_spec

        Path(out).write_text(json.dumps(build_spec(), indent=2))
        click.echo(f"Wrote {out}")
