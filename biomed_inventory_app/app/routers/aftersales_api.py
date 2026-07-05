from fastapi import APIRouter

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["After Sales API"])

_PREFIXES = (
    "/api/after-sales",
    "/api/pm",
)


mount_legacy_routes(
    router,
    lambda path: path.startswith(_PREFIXES) and path != "/api/after-sales/dashboard",
)
