"""Password hashing, identifier normalisation/masking, and authorization helpers."""

from types import SimpleNamespace

import pytest

from app.security.authz import PERMISSIONS, has_permission
from app.security.identifiers import (
    hash_voter_id,
    mask_email,
    mask_phone,
    mask_voter_id,
    normalize_email,
    normalize_phone,
    normalize_voter_id,
)
from app.security.passwords import hash_password, verify_password


class TestPasswords:
    def test_hash_is_bcrypt_and_not_plaintext(self, app):
        hashed = hash_password("CorrectHorse9")
        assert hashed.startswith("$2b$")
        assert "CorrectHorse9" not in hashed

    def test_verify_round_trip(self, app):
        hashed = hash_password("CorrectHorse9")
        assert verify_password("CorrectHorse9", hashed)
        assert not verify_password("correcthorse9", hashed)

    def test_same_password_different_salt(self, app):
        assert hash_password("CorrectHorse9") != hash_password("CorrectHorse9")

    def test_missing_hash_never_verifies(self, app):
        assert verify_password("anything", None) is False

    def test_overlong_password_rejected(self, app):
        with pytest.raises(ValueError):
            hash_password("x" * 73)
        assert verify_password("x" * 100, hash_password("short1password")) is False

    def test_garbage_hash_does_not_crash(self, app):
        assert verify_password("pw", "not-a-bcrypt-hash") is False


class TestNormalisation:
    def test_email_lowercased_and_trimmed(self):
        assert normalize_email("  Ada@Example.COM ") == "ada@example.com"

    @pytest.mark.parametrize(
        "raw", ["08031234567", "0803 123 4567", "+2348031234567", "2348031234567", "803-123-4567", "(0803) 123.4567"]
    )
    def test_phone_variants_normalise_to_e164(self, raw):
        assert normalize_phone(raw) == "+2348031234567"

    @pytest.mark.parametrize("raw", ["12345", "06031234567", "0803123456", "080312345678", "0803abc4567", "+1 555 123 4567"])
    def test_invalid_phones_rejected(self, raw):
        with pytest.raises(ValueError):
            normalize_phone(raw)

    def test_voter_id_normalised(self):
        assert normalize_voter_id(" demo-1234 5678 ") == "DEMO12345678"

    @pytest.mark.parametrize("raw", ["short", "X" * 21, "DEMO_1234567", "DEMO'1234567"])
    def test_invalid_voter_id(self, raw):
        with pytest.raises(ValueError):
            normalize_voter_id(raw)

    def test_voter_id_hash_is_keyed_and_stable(self, app):
        a = hash_voter_id("DEMO12345678")
        assert a == hash_voter_id("DEMO12345678")
        assert a != hash_voter_id("DEMO12345679")
        assert "DEMO12345678" not in a and len(a) == 64


class TestMasking:
    def test_mask_email(self):
        assert mask_email("aisha.bello@example.com") == "a***@e***.com"

    def test_mask_phone(self):
        assert mask_phone("+2348031234567") == "+234*****567"
        assert mask_phone(None) is None

    def test_mask_voter_id(self):
        assert mask_voter_id("5678") == "******5678"


class TestAuthorization:
    def user(self, role, status="active"):
        return SimpleNamespace(role=role, status=status)

    def test_voter_permissions(self):
        assert has_permission(self.user("voter"), "ballot.cast")
        assert not has_permission(self.user("voter"), "voters.verify")
        assert not has_permission(self.user("voter"), "audit.read")

    def test_admin_permissions(self):
        admin = self.user("admin")
        for perm in ("voters.verify", "elections.manage", "results.publish", "audit.read"):
            assert has_permission(admin, perm)
        assert not has_permission(admin, "ballot.cast"), "admins must not be able to vote"

    def test_auditor_is_read_only(self):
        auditor = self.user("auditor")
        assert has_permission(auditor, "audit.read")
        assert not has_permission(auditor, "elections.manage")

    def test_inactive_and_anonymous_have_no_permissions(self):
        assert not has_permission(self.user("admin", "suspended"), "audit.read")
        assert not has_permission(None, "audit.read")
        assert not has_permission(self.user("admin"), "unknown.permission")

    def test_every_permission_has_roles(self):
        assert all(PERMISSIONS.values())
