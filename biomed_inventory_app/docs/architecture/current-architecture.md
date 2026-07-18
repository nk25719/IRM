# Current Architecture

Date: 2026-07-18

## Entry Point

The canonical runtime entry point is:

```text
app.main:app
```

`app/main.py` composes the application. It imports `legacy_main` for still-active runtime behavior, mounts static assets, applies auth middleware, initializes startup tables, and registers modular routers.

## Runtime Layers

```text
Browser
-> static HTML in app/static
-> shared shell from app/static/app_layout.js
-> shared styling from app/static/theme.css
-> FastAPI app.main:app
-> auth middleware
-> router group
-> sqlite3 legacy tables or SQLAlchemy foundation tables
```

## Active Router Groups

- `app.erp_api.router`: generic ERP SQLAlchemy resource API.
- `app.quotation_api.router`: active quotation workflow using direct sqlite3.
- `app.admin_api.router`: admin, imports, backups, database map, and permissions.
- `app.aftermarket_service_reports.router`: aftermarket imported report APIs.
- `app.aftermarket_service_reports.alias_router`: `/api/after-sales` compatibility alias.
- `app.routers.web_pages.router`: static page routes.
- `app.routers.dashboard_api.router`: dashboard/home API wrappers around legacy logic.
- `app.routers.sales_api.router`: sales API wrappers.
- `app.routers.procurement_api.router`: procurement API wrappers.
- `app.routers.warehouse_api.router`: warehouse API wrappers.
- `app.routers.aftersales_api.router`: aftersales API wrappers.
- `app.routers.crm_api.router`: CRM API wrappers.
- `app.routers.master_data_api.router`: SQLAlchemy master-data APIs.
- `app.routers.imports_api.router`: SQLAlchemy import-batch CRUD APIs.
- `app.routers.data_management_api.router`: Data Management Center staging APIs.

## Static UI

Most screens are static HTML. The shared sidebar is injected by `app/static/app_layout.js`, and shared visual rules live in `app/static/theme.css`. `pm-frontend/` is a separate Vite/Tauri source project for the PM workspace bundle that is served from `app/static/pm/`.

## Database Ownership

The app currently uses a hybrid database layer:

- Legacy runtime: direct sqlite3 via `legacy_main.db()` and module-specific sqlite3 helpers.
- Foundation runtime: SQLAlchemy `SessionLocal`, models in `erp_models.py` and `app/models/foundation.py`.
- Schema authority: Alembic migrations.
- Local SQLite DB: replaceable runtime state ignored by Git.
