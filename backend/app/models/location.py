"""Electoral geography: LGA -> Ward -> Polling Unit."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class LocalGovernmentArea(db.Model):
    __tablename__ = "local_government_areas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    wards = relationship("Ward", back_populates="lga", order_by="Ward.name")


class Ward(db.Model):
    __tablename__ = "wards"
    __table_args__ = (UniqueConstraint("lga_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lga_id: Mapped[int] = mapped_column(ForeignKey("local_government_areas.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    lga = relationship("LocalGovernmentArea", back_populates="wards")
    polling_units = relationship("PollingUnit", back_populates="ward", order_by="PollingUnit.name")


class PollingUnit(db.Model):
    __tablename__ = "polling_units"
    __table_args__ = (UniqueConstraint("ward_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ward_id: Mapped[int] = mapped_column(ForeignKey("wards.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    ward = relationship("Ward", back_populates="polling_units")
