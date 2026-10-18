"""AES-256-GCM ballot encryption."""

import pytest

from app.services import crypto_service
from app.services.crypto_service import BallotDecryptionError


def test_round_trip(app):
    ct, nonce, digest = crypto_service.encrypt_ballot(7, 42, 3, "AAAA-BBBB-CCCC-DDDD")
    payload = crypto_service.decrypt_ballot(7, "AAAA-BBBB-CCCC-DDDD", nonce, ct, digest)
    assert payload == {"v": 1, "e": 7, "c": 42, "l": 3}


def test_ciphertext_hides_choice_and_length(app):
    a, _, _ = crypto_service.encrypt_ballot(1, 1, 1, "R1")
    b, _, _ = crypto_service.encrypt_ballot(1, 123456, 21, "R2")
    assert len(a) == len(b), "padding must hide which candidate was chosen"
    assert b"123456" not in b


def test_fresh_nonce_each_time(app):
    _, n1, _ = crypto_service.encrypt_ballot(1, 1, 1, "R")
    _, n2, _ = crypto_service.encrypt_ballot(1, 1, 1, "R")
    assert n1 != n2 and len(n1) == 12


def test_tampered_ciphertext_detected(app):
    ct, nonce, digest = crypto_service.encrypt_ballot(1, 2, 3, "R")
    tampered = bytes([ct[0] ^ 1]) + ct[1:]
    with pytest.raises(BallotDecryptionError):
        crypto_service.decrypt_ballot(1, "R", nonce, tampered, digest)
    # Even with a recomputed hash, GCM authentication fails.
    aad = b"adv:v1:election=1:receipt=R"
    with pytest.raises(BallotDecryptionError):
        crypto_service.decrypt_ballot(1, "R", nonce, tampered, crypto_service.integrity_hash(aad, nonce, tampered))


def test_ciphertext_bound_to_election_and_receipt(app):
    ct, nonce, digest = crypto_service.encrypt_ballot(1, 2, 3, "R")
    with pytest.raises(BallotDecryptionError):
        crypto_service.decrypt_ballot(2, "R", nonce, ct, digest)
    with pytest.raises(BallotDecryptionError):
        crypto_service.decrypt_ballot(1, "OTHER", nonce, ct, digest)


def test_wrong_key_cannot_decrypt(app):
    import base64
    import os

    ct, nonce, digest = crypto_service.encrypt_ballot(1, 2, 3, "R")
    app.config["VOTE_ENCRYPTION_KEY"] = base64.b64encode(os.urandom(32)).decode()
    with pytest.raises(BallotDecryptionError):
        crypto_service.decrypt_ballot(1, "R", nonce, ct, digest)


def test_config_rejects_bad_keys():
    from app.config import ConfigError, validate_config

    good = {"SECRET_KEY": "x" * 40, "IDENTIFIER_PEPPER": "p", "SQLALCHEMY_DATABASE_URI": "sqlite://"}
    with pytest.raises(ConfigError):
        validate_config({**good, "VOTE_ENCRYPTION_KEY": "too-short"})
    with pytest.raises(ConfigError):
        validate_config({**good, "VOTE_ENCRYPTION_KEY": "AAAA"})  # 3 bytes
    with pytest.raises(ConfigError):
        validate_config({**good, "VOTE_ENCRYPTION_KEY": None})
