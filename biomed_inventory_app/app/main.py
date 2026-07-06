from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import legacy_main
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
    return legacy_main.init_db()


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

    return await call_next(request)


app.add_middleware(SessionMiddleware, secret_key=legacy_main.SESSION_SECRET, https_only=False)

app.include_router(erp_router)
app.include_router(quotation_router)
app.include_router(web_pages.router)
app.include_router(dashboard_api.router)
app.include_router(sales_api.router)
app.include_router(procurement_api.router)
app.include_router(warehouse_api.router)
app.include_router(aftersales_api.router)
app.include_router(crm_api.router)
