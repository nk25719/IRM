from fastapi import APIRouter

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Warehouse API"])

_PREFIXES = (
    "/api/audit",
    "/api/biomedical",
    "/api/clean-inventory",
    "/api/inventory",
    "/api/item-options",
    "/api/items",
    "/api/lookup",
    "/api/qr-labels",
    "/api/report",
    "/api/sync",
    "/api/transactions",
    "/api/warehouse",
    "/api/stock-movements",
)


mount_legacy_routes(
    router,
    lambda path: path in {"/api/export", "/api/import"} or path.startswith(_PREFIXES),
)
