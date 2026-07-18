# Current Call Graph

Date: 2026-07-18

```text
uvicorn app.main:app
  -> app/main.py
     -> imports app.legacy_main
        -> defines legacy FastAPI app and legacy route functions
        -> exposes init_db(), db(), auth/static constants, and workflow helpers
     -> imports active routers
     -> lifespan startup
        -> legacy_main.init_db()
           -> creates legacy sqlite3 tables when SQLite is configured
           -> imports app/data/inventory_master.xlsx when needed
           -> writes legacy audit_log rows through audit_log.item_id
        -> admin_api.ensure_admin_foundation()
        -> aftermarket_service_reports.ensure_service_report_tables()
     -> mounts /static, /pm/assets, /uploads
     -> auth_middleware
        -> allows public login/static paths
        -> redirects page requests to /login when unauthenticated
        -> returns 401 for unauthenticated /api requests
     -> include_router(...)
```

## Router To Data Access

```text
web_pages
  -> FileResponse/StaticFiles

dashboard_api, sales_api, procurement_api, warehouse_api, aftersales_api, crm_api
  -> app.routers._legacy
  -> app.legacy_main functions
  -> sqlite3 runtime tables

quotation_api
  -> sqlite3 connection from shared database config
  -> quotation tables

admin_api
  -> sqlite3 for legacy admin/import/backup/database-map paths
  -> audit_log for admin import audit rows

master_data_api
  -> app.services.* SQLAlchemy services
  -> app.models.foundation master-data tables

imports_api
  -> ImportBatchService
  -> import_batches

data_management_api
  -> app.data_management.template_registry
  -> SQLAlchemy ImportBatch, ImportRow, DataValidationError, AuditEvent
  -> guarded raw SQL reads for registered exports only

aftermarket_service_reports
  -> legacy sqlite3 helper
  -> service report and installed-base tables
```

## Authenticated GET Behavior

Unauthenticated checks verified on 2026-07-18:

- `GET /`: `200 OK`.
- `GET /administration/data-management`: `303 See Other` to `/login`.
- `GET /api/data-management/datasets`: `401 Unauthorized`.
