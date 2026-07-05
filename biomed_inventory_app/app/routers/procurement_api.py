from fastapi import APIRouter

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Procurement API"])

_PREFIXES = (
    "/api/procurement",
    "/api/purchase-orders",
)


mount_legacy_routes(
    router,
    lambda path: path.startswith(_PREFIXES) and path != "/api/procurement/dashboard",
)
