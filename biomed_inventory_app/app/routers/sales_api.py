from fastapi import APIRouter

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Sales API"])

_PREFIXES = (
    "/api/client-orders",
    "/api/sales",
    "/api/commercial",
    "/api/customer-requests",
    "/api/sales-documents",
    "/api/equipment-bids",
)


mount_legacy_routes(
    router,
    lambda path: path.startswith(_PREFIXES) and path != "/api/sales/dashboard",
)
