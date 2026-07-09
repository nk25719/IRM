from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import legacy_main
from app.admin_api import ensure_admin_foundation, permissions_for_role, router as admin_router
from app.aftermarket_service_reports import alias_router as aftermarket_alias_router
from app.aftermarket_service_reports import ensure_service_report_tables, router as aftermarket_router
from app.erp_api import router as erp_router
from app.quotation_api import router as quotation_router
from app.routers import (
    aftersales_api,
    crm_api,
    dashboard_api,
    procurement_api,
    sales_api,
    warehouse_api,
    web_pages,
)


# Expose init_db at module level for tests and direct initialization
def init_db():
    """Initialize database tables. Exposed for tests and direct usage."""
    result = legacy_main.init_db()
    ensure_admin_foundation()
    ensure_service_report_tables()
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown events."""
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Biomedical Warehouse ERP", 
    version="1.2.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory=legacy_main.BASE_DIR / "static"), name="static")
app.mount(
    "/pm/assets",
    StaticFiles(directory=legacy_main.BASE_DIR / "static" / "pm" / "assets"),
    name="pm-assets",
)
app.mount("/uploads", StaticFiles(directory=legacy_main.UPLOADS_DIR), name="uploads")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in legacy_main.PUBLIC_PATHS:
        return await call_next(request)
    if path.startswith("/static") and path.lower().endswith(legacy_main.PUBLIC_STATIC_SUFFIXES):
        return await call_next(request)

    if not request.session.get("authenticated"):
        if path.startswith("/api"):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)

    role = request.session.get("role") or legacy_main.APP_ROLE or "viewer"
    permissions = permissions_for_role(role)
    route_permissions = [
        (("/admin/database-map", "/api/admin/database-map"), "view_database_map"),
        (("/admin/imports", "/api/admin/imports", "/api/admin/import-targets"), "import_data"),
        (("/admin/backups",), "create_backup"),
        (("/admin/query", "/reports/query", "/api/admin/reports"), "view_reports"),
        (("/api/admin/query",), "run_select_queries"),
        (("/quotations", "/sales/quotations"), "edit_quotations"),
        (("/warehouse", "/api/warehouse"), "view_reports"),
        (("/aftersales", "/api/aftermarket", "/api/after-sales"), "view_after_sales_cases"),
        (("/clients", "/api/crm", "/api/erp/clients"), "view_all_clients"),
    ]
    for prefixes, permission in route_permissions:
        if path.startswith(prefixes) and role != "admin" and permission not in permissions:
            if path.startswith("/api") or path.startswith("/admin/backups"):
                return JSONResponse({"detail": f"Permission required: {permission}"}, status_code=403)
            return RedirectResponse(url="/", status_code=303)

    return await call_next(request)


app.add_middleware(SessionMiddleware, secret_key=legacy_main.SESSION_SECRET, https_only=False)

app.include_router(erp_router)
app.include_router(quotation_router)
app.include_router(admin_router)
app.include_router(aftermarket_router)
app.include_router(aftermarket_alias_router)
app.include_router(web_pages.router)
app.include_router(dashboard_api.router)
app.include_router(sales_api.router)
app.include_router(procurement_api.router)
app.include_router(warehouse_api.router)
app.include_router(aftersales_api.router)
app.include_router(crm_api.router)
