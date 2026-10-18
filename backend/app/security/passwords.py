"""bcrypt password hashing."""

from __future__ import annotations

import bcrypt
from flask import current_app, has_app_context

DEFAULT_BCRYPT_ROUNDS = 12
# Used to equalise timing when an account does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser-not-a-password", bcrypt.gensalt(DEFAULT_BCRYPT_ROUNDS))


def _rounds() -> int:
    if has_app_context():
        return int(current_app.config.get("BCRYPT_ROUNDS", DEFAULT_BCRYPT_ROUNDS))
    return DEFAULT_BCRYPT_ROUNDS


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Password is too long")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(_rounds())).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        return False
    if not password_hash:
        bcrypt.checkpw(encoded, _DUMMY_HASH)
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("ascii"))
    except ValueError:
        return False
