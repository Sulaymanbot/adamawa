"""One-time passcodes (optional second factor, mock delivery only).

Codes are stored as keyed hashes, expire after OTP_TTL_SECONDS and allow at
most OTP_MAX_ATTEMPTS guesses. Delivery is mocked: in development the code is
printed to the server console; in tests it goes to an in-memory outbox. There
is no real SMS/email provider in this prototype.
"""

from __future__ import annotations

import hmac
import secrets
import sys
from datetime import timedelta

from flask import current_app

from app.errors import APIError
from app.extensions import db
from app.models import OtpChallenge, User, utcnow
from app.security.identifiers import keyed_hash


class MockOtpProvider:
    def send(self, user: User, code: str) -> None:
        env = current_app.config.get("APP_ENV")
        if env == "testing":
            current_app.extensions.setdefault("otp_outbox", []).append({"user_id": user.id, "code": code})
        elif env == "development":
            # Written straight to the dev console, never to the structured log.
            print(
                f"[DEV-ONLY MOCK OTP] user #{user.id}: {code} (expires in {current_app.config['OTP_TTL_SECONDS'] // 60} min)",
                file=sys.stderr,
                flush=True,
            )
        else:
            raise RuntimeError("No real OTP provider is configured; disable OTP_ENABLED outside development.")


provider = MockOtpProvider()


def _hash(challenge_salt: str, code: str) -> str:
    return keyed_hash(f"{challenge_salt}:{code}", "otp")


def issue(user: User, purpose: str = "login") -> None:
    now = utcnow()
    # Invalidate earlier unconsumed challenges for the same purpose.
    for old in db.session.execute(
        db.select(OtpChallenge).filter_by(user_id=user.id, purpose=purpose, consumed_at=None)
    ).scalars():
        old.consumed_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = OtpChallenge(
        user_id=user.id,
        purpose=purpose,
        code_hash="pending",
        expires_at=now + timedelta(seconds=current_app.config["OTP_TTL_SECONDS"]),
    )
    db.session.add(challenge)
    db.session.flush()
    challenge.code_hash = _hash(str(challenge.id), code)
    db.session.commit()
    provider.send(user, code)


def verify(user_id: int, code: str, purpose: str = "login") -> bool:
    now = utcnow()
    challenge = (
        db.session.execute(
            db.select(OtpChallenge).filter_by(user_id=user_id, purpose=purpose, consumed_at=None).order_by(OtpChallenge.id.desc())
        )
        .scalars()
        .first()
    )
    if challenge is None or challenge.expires_at <= now:
        raise APIError(400, "otp_expired", "This code has expired. Request a new code.")
    if challenge.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        challenge.consumed_at = now
        db.session.commit()
        raise APIError(400, "otp_locked", "Too many incorrect attempts. Request a new code.")
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.code_hash, _hash(str(challenge.id), code)):
        db.session.commit()
        return False
    challenge.consumed_at = now
    db.session.commit()
    return True
