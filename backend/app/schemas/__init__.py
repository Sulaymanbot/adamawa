"""Request validation schemas (pydantic).

Every schema forbids unknown fields so malformed payloads are rejected rather
than silently ignored.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from flask import request
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.errors import APIError
from app.models.election import CANDIDATE_STATUSES, ELECTION_SCOPES, ELECTION_TYPES
from app.security.identifiers import normalize_email, normalize_phone, normalize_voter_id

NAME_RE = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\- ]{0,79}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

Id = Annotated[StrictInt, Field(gt=0, lt=2**31)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = CONTROL_RE.sub("", value).strip()
    return value or None


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp must include a timezone offset, e.g. 2026-10-01T09:00:00+01:00")
    return value.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def validate_password_strength(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(password.encode("utf-8")) > 64:
        raise ValueError("Password must be at most 64 characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("Password must contain at least one letter and one number")
    return password


def _name(value: str, label: str) -> str:
    if not NAME_RE.match(value):
        raise ValueError(f"{label} may only contain letters, spaces, hyphens and apostrophes")
    return value


class RegisterRequest(Strict):
    surname: str = Field(min_length=1, max_length=80)
    first_name: str = Field(min_length=1, max_length=80)
    other_names: str | None = Field(default=None, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    voter_id: str = Field(min_length=10, max_length=30)
    lga_id: Id
    ward_id: Id
    polling_unit_id: Id
    password: str = Field(min_length=1, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)
    demo_acknowledged: bool

    @field_validator("surname")
    @classmethod
    def _surname(cls, v: str) -> str:
        return _name(v, "Surname")

    @field_validator("first_name")
    @classmethod
    def _first(cls, v: str) -> str:
        return _name(v, "First name")

    @field_validator("other_names")
    @classmethod
    def _other(cls, v: str | None) -> str | None:
        v = clean_text(v)
        return _name(v, "Other names") if v else None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("voter_id")
    @classmethod
    def _vid(cls, v: str) -> str:
        return normalize_voter_id(v)

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("demo_acknowledged")
    @classmethod
    def _ack(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("You must confirm that you understand this is a simulated demo")
        return v

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(Strict):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return normalize_email(v)


class OtpVerifyRequest(Strict):
    code: str = Field(pattern=r"^\d{6}$")


class VerificationRequest(Strict):
    action: Literal["verify", "reject", "suspend", "reactivate"]
    reason: str | None = Field(default=None, max_length=300)

    @field_validator("reason")
    @classmethod
    def _reason(cls, v: str | None) -> str | None:
        return clean_text(v)

    @model_validator(mode="after")
    def _needs_reason(self):
        if self.action in {"reject", "suspend"} and not self.reason:
            raise ValueError("A reason is required when rejecting or suspending a voter")
        return self


class VoterSearchRequest(Strict):
    q: str | None = Field(default=None, max_length=80)
    status: Literal["pending", "verified", "rejected", "suspended"] | None = None
    lga_id: Id | None = None
    ward_id: Id | None = None
    page: Annotated[StrictInt, Field(ge=1, le=10_000)] = 1
    per_page: Annotated[StrictInt, Field(ge=1, le=100)] = 20

    @field_validator("q")
    @classmethod
    def _q(cls, v: str | None) -> str | None:
        return clean_text(v)


class ElectionCreate(Strict):
    title: str = Field(min_length=3, max_length=200)
    type: Literal[ELECTION_TYPES] = "lg_chairmanship"  # type: ignore[valid-type]
    description: str | None = Field(default=None, max_length=2000)
    scope: Literal[ELECTION_SCOPES] = "all_lgas"  # type: ignore[valid-type]
    lga_id: Id | None = None
    start_at: datetime
    end_at: datetime

    @field_validator("title", "description")
    @classmethod
    def _text(cls, v):
        return clean_text(v)

    @field_validator("start_at", "end_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return to_utc_naive(v)

    @model_validator(mode="after")
    def _check(self):
        if self.end_at <= self.start_at:
            raise ValueError("Closing time must be after opening time")
        if self.scope == "single_lga" and self.lga_id is None:
            raise ValueError("Choose the LGA for a single-LGA election")
        if self.scope == "all_lgas":
            self.lga_id = None
        return self


class ElectionUpdate(Strict):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    type: Literal[ELECTION_TYPES] | None = None  # type: ignore[valid-type]
    description: str | None = Field(default=None, max_length=2000)
    scope: Literal[ELECTION_SCOPES] | None = None  # type: ignore[valid-type]
    lga_id: Id | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("title", "description")
    @classmethod
    def _text(cls, v):
        return clean_text(v)

    @field_validator("start_at", "end_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return to_utc_naive(v) if v else None


class ElectionAction(Strict):
    reason: str | None = Field(default=None, max_length=300)


class PublishRequest(Strict):
    publish_at: datetime | None = None
    hide: bool = False

    @field_validator("publish_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return to_utc_naive(v) if v else None


def _photo(v: str | None) -> str | None:
    v = clean_text(v)
    if v and not (v.startswith("/static/") or v.startswith("https://")):
        raise ValueError("Photo URL must be an https:// URL or a /static/ path")
    return v


class CandidateCreate(Strict):
    full_name: str = Field(min_length=3, max_length=150)
    party_affiliation: str = Field(min_length=2, max_length=120)
    manifesto_summary: str | None = Field(default=None, max_length=2000)
    lga_id: Id | None = None
    photo_url: str | None = Field(default=None, max_length=300)

    @field_validator("full_name", "party_affiliation", "manifesto_summary")
    @classmethod
    def _text(cls, v):
        return clean_text(v)

    @field_validator("photo_url")
    @classmethod
    def _photo(cls, v):
        return _photo(v)


class CandidateUpdate(Strict):
    full_name: str | None = Field(default=None, min_length=3, max_length=150)
    party_affiliation: str | None = Field(default=None, min_length=2, max_length=120)
    manifesto_summary: str | None = Field(default=None, max_length=2000)
    lga_id: Id | None = None
    photo_url: str | None = Field(default=None, max_length=300)
    status: Literal[CANDIDATE_STATUSES] | None = None  # type: ignore[valid-type]

    @field_validator("full_name", "party_affiliation", "manifesto_summary")
    @classmethod
    def _text(cls, v):
        return clean_text(v)

    @field_validator("photo_url")
    @classmethod
    def _photo(cls, v):
        return _photo(v)


class VoteRequest(Strict):
    candidate_id: Id


class ReceiptCheckRequest(Strict):
    receipt_reference: str = Field(pattern=r"^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$")

    @field_validator("receipt_reference", mode="before")
    @classmethod
    def _upper(cls, v):
        return v.strip().upper() if isinstance(v, str) else v


def parse_body(model: type[BaseModel]):
    """Parse and validate the JSON body, raising consistent API errors."""
    if not request.is_json:
        raise APIError(415, "unsupported_media_type", "Requests must be sent as JSON.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIError(400, "malformed_json", "The request body must be a JSON object.")
    return model.model_validate(data)
