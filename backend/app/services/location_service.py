"""Electoral locations."""

from __future__ import annotations

from app.errors import APIError
from app.extensions import db
from app.models import LocalGovernmentArea, PollingUnit, Ward


def list_lgas():
    return (
        db.session.execute(db.select(LocalGovernmentArea).filter_by(active=True).order_by(LocalGovernmentArea.name))
        .scalars()
        .all()
    )


def list_wards(lga_id: int):
    lga = db.session.get(LocalGovernmentArea, lga_id)
    if lga is None or not lga.active:
        raise APIError(404, "not_found", "LGA not found.")
    return db.session.execute(db.select(Ward).filter_by(lga_id=lga_id, active=True).order_by(Ward.name)).scalars().all()


def list_polling_units(ward_id: int):
    ward = db.session.get(Ward, ward_id)
    if ward is None or not ward.active:
        raise APIError(404, "not_found", "Ward not found.")
    return (
        db.session.execute(db.select(PollingUnit).filter_by(ward_id=ward_id, active=True).order_by(PollingUnit.name))
        .scalars()
        .all()
    )


def validate_hierarchy(lga_id: int, ward_id: int, polling_unit_id: int) -> None:
    """Ensure the polling unit belongs to the ward and the ward to the LGA."""
    pu = db.session.get(PollingUnit, polling_unit_id)
    if (
        pu is None
        or not pu.active
        or pu.ward_id != ward_id
        or pu.ward.lga_id != lga_id
        or not pu.ward.active
        or not pu.ward.lga.active
    ):
        raise APIError(
            422,
            "validation_error",
            "Some fields are invalid.",
            [{"field": "polling_unit_id", "message": "Choose a polling unit that belongs to the selected ward and LGA"}],
        )


def serialize(obj) -> dict:
    data = {"id": obj.id, "name": obj.name, "code": obj.code}
    return data
