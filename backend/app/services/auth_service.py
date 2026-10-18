"""Registration, login, OTP step-up and logout."""

from __future__ import annotations

import time

from flask import current_app, g, session
from sqlalchemy.exc import IntegrityError

from app.errors import APIError
from app.extensions import db
from app.models import User, Voter
from app.schemas import RegisterRequest
from app.security import sessions
from app.security.identifiers import hash_voter_id
from app.security.passwords import hash_password, verify_password
from app.services import audit_service, location_service, otp_service

INVALID_CREDENTIALS = "Email or password is incorrect."
DUPLICATE_ACCOUNT = (
    "An account already exists with some of these details. If this is you, sign in instead or contact the electoral office."
)


def register_voter(data: RegisterRequest) -> Voter:
    location_service.validate_hierarchy(data.lga_id, data.ward_id, data.polling_unit_id)
    vid_hash = hash_voter_id(data.voter_id)

    duplicate = (
        db.session.execute(db.select(User.id).where(User.email == data.email)).first()
        or db.session.execute(db.select(User.id).where(User.phone == data.phone)).first()
        or db.session.execute(db.select(Voter.id).where(Voter.voter_id_hash == vid_hash)).first()
    )
    if duplicate:
        audit_service.record("voter.registration_duplicate", "Registration rejected: duplicate details")
        raise APIError(409, "duplicate_account", DUPLICATE_ACCOUNT)

    user = User(role="voter", email=data.email, phone=data.phone, password_hash=hash_password(data.password))
    voter = Voter(
        user=user,
        voter_id_hash=vid_hash,
        voter_id_last4=data.voter_id[-4:],
        surname=data.surname,
        first_name=data.first_name,
        other_names=data.other_names,
        lga_id=data.lga_id,
        ward_id=data.ward_id,
        polling_unit_id=data.polling_unit_id,
        verification_status="pending",
    )
    db.session.add_all([user, voter])
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        audit_service.record("voter.registration_duplicate", "Registration rejected: duplicate details")
        raise APIError(409, "duplicate_account", DUPLICATE_ACCOUNT) from None
    audit_service.record(
        "voter.registered",
        f"Voter #{voter.id} registered (pending verification)",
        actor_user_id=user.id,
        entity_type="voter",
        entity_id=voter.id,
        commit=False,
    )
    db.session.commit()
    return voter


def login(email: str, password: str) -> dict:
    user = db.session.execute(db.select(User).where(User.email == email)).scalar_one_or_none()
    if not verify_password(password, user.password_hash if user else None):
        audit_service.record(
            "auth.login_failed",
            "Failed login attempt" + (f" for user #{user.id}" if user else " for unknown account"),
            actor_user_id=user.id if user else None,
        )
        raise APIError(401, "invalid_credentials", INVALID_CREDENTIALS)
    if user.status != "active":
        audit_service.record("auth.login_blocked", f"Login blocked: account status {user.status}", actor_user_id=user.id)
        raise APIError(403, "account_inactive", "This account is not active. Please contact the electoral office.")

    if current_app.config.get("OTP_ENABLED"):
        session.clear()
        session["otp_pending"] = {"uid": user.id, "exp": int(time.time()) + current_app.config["OTP_TTL_SECONDS"]}
        otp_service.issue(user)
        audit_service.record("auth.otp_sent", "Password accepted; one-time code issued", actor_user_id=user.id)
        return {"otp_required": True}

    sessions.start_session(user)
    audit_service.record("auth.login_success", f"{user.role.title()} signed in", actor_user_id=user.id)
    return {"otp_required": False, "user": serialize_user(user)}


def _pending_user() -> User:
    pending = session.get("otp_pending")
    if not pending or pending.get("exp", 0) < time.time():
        session.pop("otp_pending", None)
        raise APIError(401, "otp_session_missing", "Your sign-in attempt expired. Please sign in again.")
    user = db.session.get(User, pending["uid"])
    if user is None or user.status != "active":
        session.pop("otp_pending", None)
        raise APIError(401, "otp_session_missing", "Your sign-in attempt expired. Please sign in again.")
    return user


def resend_otp() -> None:
    user = _pending_user()
    otp_service.issue(user)
    audit_service.record("auth.otp_resent", "One-time code re-issued", actor_user_id=user.id)


def verify_otp(code: str) -> dict:
    user = _pending_user()
    if not otp_service.verify(user.id, code):
        audit_service.record("auth.otp_failed", "Incorrect one-time code", actor_user_id=user.id)
        raise APIError(401, "otp_invalid", "That code is not correct. Check it and try again.")
    sessions.start_session(user)
    audit_service.record("auth.login_success", f"{user.role.title()} signed in with OTP", actor_user_id=user.id)
    return {"user": serialize_user(user)}


def logout() -> None:
    user = g.get("user")
    if user is not None:
        audit_service.record("auth.logout", "Signed out", actor_user_id=user.id)
    sessions.end_session()


def serialize_user(user: User) -> dict:
    return {"id": user.id, "role": user.role, "display_name": user.display_name}
