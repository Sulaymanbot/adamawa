"""Public electoral-location lookups (used by the registration form)."""

from app.api import api_v1
from app.errors import ok
from app.services import location_service


@api_v1.get("/locations/lgas")
def lgas():
    return ok([location_service.serialize(x) for x in location_service.list_lgas()])


@api_v1.get("/locations/lgas/<int:lga_id>/wards")
def wards(lga_id: int):
    return ok([location_service.serialize(x) for x in location_service.list_wards(lga_id)])


@api_v1.get("/locations/wards/<int:ward_id>/polling-units")
def polling_units(ward_id: int):
    return ok([location_service.serialize(x) for x in location_service.list_polling_units(ward_id)])
