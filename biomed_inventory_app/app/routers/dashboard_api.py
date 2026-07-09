from fastapi import APIRouter

from app import legacy_main

from ._legacy import mount_legacy_routes

router = APIRouter(tags=["Dashboard API"])

_PATHS = {
    "/api/dashboard",
    "/api/home/snapshot",
    "/api/hospitals",
    "/api/sales/dashboard",
    "/api/procurement/dashboard",
    "/api/after-sales/dashboard",
    "/api/search",
    "/api/traceability/{reference}",
    "/api/imports",
    "/api/imports/{batch_id}/rows",
    "/api/imports/pending-offers/preview",
    "/api/imports/pending-offers/commit",
    "/api/imports/{batch_id}/rollback",
    "/api/bulk-edit",
    "/api/bulk-export",
    "/api/exports/{report_name}",
}


mount_legacy_routes(router, lambda path: path in _PATHS)


@router.get("/api/aftermarket/dashboard")
def aftermarket_dashboard():
    conn = legacy_main.db()
    legacy_main.ensure_clients_from_existing_data(conn)
    conn.commit()
    data = legacy_main.after_sales_dashboard_data(conn)
    conn.close()
    return data
