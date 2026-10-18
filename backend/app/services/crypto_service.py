"""Ballot encryption with AES-256-GCM.

Design (prototype):
- One symmetric 256-bit key, base64 in the VOTE_ENCRYPTION_KEY environment
  variable. It is never stored in the database or the repository.
- Each ballot gets a fresh random 96-bit nonce.
- Associated data binds the ciphertext to its election and receipt, so a
  ciphertext copied into another election or row fails authentication.
- The plaintext is padded to a fixed length so ciphertext size does not leak
  which candidate was chosen.
- integrity_hash = SHA-256(aad | nonce | ciphertext) lets the tally detect
  tampered rows before attempting decryption.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app

KEY_VERSION = 1
PLAINTEXT_SIZE = 96


class BallotDecryptionError(Exception):
    pass


def _key() -> bytes:
    return base64.b64decode(current_app.config["VOTE_ENCRYPTION_KEY"])


def _aad(election_id: int, receipt: str) -> bytes:
    return f"adv:v{KEY_VERSION}:election={election_id}:receipt={receipt}".encode()


def integrity_hash(aad: bytes, nonce: bytes, ciphertext: bytes) -> str:
    return hashlib.sha256(aad + b"|" + nonce + b"|" + ciphertext).hexdigest()


def encrypt_ballot(election_id: int, candidate_id: int, lga_id: int, receipt: str):
    body = json.dumps({"v": 1, "e": election_id, "c": candidate_id, "l": lga_id}, separators=(",", ":"))
    plaintext = body.encode().ljust(PLAINTEXT_SIZE, b" ")
    nonce = os.urandom(12)
    aad = _aad(election_id, receipt)
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext, aad)
    return ciphertext, nonce, integrity_hash(aad, nonce, ciphertext)


def decrypt_ballot(election_id: int, receipt: str, nonce: bytes, ciphertext: bytes, expected_hash: str) -> dict:
    aad = _aad(election_id, receipt)
    if integrity_hash(aad, nonce, ciphertext) != expected_hash:
        raise BallotDecryptionError("integrity hash mismatch")
    try:
        plaintext = AESGCM(_key()).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise BallotDecryptionError("authentication failed") from exc
    payload = json.loads(plaintext.decode().strip())
    if payload.get("e") != election_id:
        raise BallotDecryptionError("election mismatch")
    return payload
