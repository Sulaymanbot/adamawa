"""Server-side session lifecycle.

The Flask session cookie is signed and only carries an opaque random token.
The token's SHA-256 hash is stored in user_sessions, so sessions can be revoked
on logout and expire on idle/absolute timeouts regardless of the cookie.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from flask import current_app, g, session

from app.extensions import db
from app.models import User, UserSession, utcnow


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(user: User) -> None:
    """Create a fresh session. Clearing first prevents session fixation."""
    session.clear()
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.session.add(
        UserSession(
            token_hash=_hash(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=current_app.config["SESSION_ABSOLUTE_HOURS"]),
        )
    )
    user.last_login_at = now
    db.session.commit()
    session.permanent = True
    session["sid"] = token
    g.user = user


def end_session() -> None:
    token = session.get("sid")
    if token:
        record = db.session.execute(db.select(UserSession).filter_by(token_hash=_hash(token))).scalar_one_or_none()
        if record and record.revoked_at is None:
            record.revoked_at = utcnow()
            db.session.commit()
    session.clear()
    g.user = None


def load_current_user() -> None:
    """before_request hook: resolve g.user from the session cookie."""
    g.user = None
    g.session_expired = False
    token = session.get("sid")
    if not token:
        return
    record = db.session.execute(db.select(UserSession).filter_by(token_hash=_hash(token))).scalar_one_or_none()
    now = utcnow()
    idle = timedelta(minutes=current_app.config["SESSION_IDLE_MINUTES"])
    if record is None or record.revoked_at is not None or record.expires_at <= now or record.last_seen_at + idle <= now:
        if record is not None and record.revoked_at is None:
            record.revoked_at = now
            db.session.commit()
        session.pop("sid", None)
        g.session_expired = True
        return
    user = record.user
    if user is None or user.status != "active":
        session.pop("sid", None)
        return
    if (now - record.last_seen_at).total_seconds() > 60:
        record.last_seen_at = now
        db.session.commit()
    g.user = user


def revoke_all_sessions(user_id: int) -> None:
    now = utcnow()
    db.session.execute(
        db.update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None)).values(revoked_at=now)
    )
