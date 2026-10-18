"""Normalisation, keyed hashing and masking of personal identifiers."""

from __future__ import annotations

import hashlib
import hmac
import re

from flask import current_app

VOTER_ID_RE = re.compile(r"^[A-Z0-9]{10,20}$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """Normalise a Nigerian mobile number to E.164 (+234XXXXXXXXXX).

    Raises ValueError for anything that is not a plausible Nigerian mobile.
    """
    digits = re.sub(r"[\s\-().]", "", phone.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        raise ValueError("Phone number may only contain digits, spaces, dashes or a leading +")
    if digits.startswith("234"):
        national = digits[3:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        national = digits
    if len(national) != 10 or national[0] not in "789":
        raise ValueError("Enter a valid Nigerian mobile number, e.g. 0803 123 4567")
    return "+234" + national


def normalize_voter_id(voter_id: str) -> str:
    cleaned = re.sub(r"[\s\-]", "", voter_id.strip()).upper()
    if not VOTER_ID_RE.match(cleaned):
        raise ValueError("Voter ID must be 10–20 letters or digits")
    return cleaned


def keyed_hash(value: str, purpose: str) -> str:
    """HMAC-SHA256 with the server-side pepper. Purpose separates domains."""
    pepper = current_app.config["IDENTIFIER_PEPPER"].encode()
    return hmac.new(pepper, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()


def hash_voter_id(normalized_voter_id: str) -> str:
    return keyed_hash(normalized_voter_id, "voter-id")


def hash_ip(ip: str | None) -> str | None:
    if not ip or current_app.config.get("AUDIT_IP_MODE") == "none":
        return None
    return keyed_hash(ip, "ip")[:32]


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    dom_name, _, tld = domain.partition(".")
    return f"{local[:1]}***@{dom_name[:1]}***.{tld or '***'}"


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return f"{phone[:4]}*****{phone[-3:]}"


def mask_voter_id(last4: str) -> str:
    return f"******{last4}"
