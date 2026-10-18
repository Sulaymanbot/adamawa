"""Model helpers shared by all entities."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp, truncated to whole seconds.

    MySQL DATETIME stores no timezone and no fractional seconds (it rounds them),
    so truncating keeps "visible from now" comparisons identical on MySQL and SQLite.
    """
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def in_check(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
