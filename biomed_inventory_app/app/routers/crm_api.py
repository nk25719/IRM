from fastapi import APIRouter

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["CRM API"])

_PREFIXES = (
    "/api/crm",
    "/api/clients",
    "/api/departments",
    "/api/equipment",
    "/api/contracts",
    "/api/service-calls",
    "/api/cases",
    "/api/unified-case-entry",
)


mount_legacy_routes(
    router,
    lambda path: path.startswith(_PREFIXES) and not path.startswith("/api/equipment-bids"),
)
