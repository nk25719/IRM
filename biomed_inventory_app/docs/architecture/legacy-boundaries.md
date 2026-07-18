# Legacy Boundaries

Date: 2026-07-18

## Still Active

- `app/legacy_main.py`: startup table creation, legacy workflow helpers, and many warehouse/sales/procurement/service route implementations.
- `app/routers/_legacy.py`: adapter helpers used by modular router wrappers.
- `app/quotation_api.py`: active quotation workflow using direct sqlite3.
- `app/admin_api.py`: admin/import/backup/database-map behavior using sqlite3 and shared database config.
- `app/aftermarket_service_reports.py`: active service-report import and installed-base behavior.
- `app/static/*.html`: active static UI pages.
- `app/static/pm/`: built PM bundle served by FastAPI.

## Compatibility Code

- `app.main.__getattr__`: keeps older tests/scripts that import helpers from `app.main` working while implementation remains in `legacy_main`.
- `app/legacy_main.py` audit-log column patch: idempotently adds `audit_log.item_id` for existing databases because legacy warehouse audit writes still require it.
- Aftermarket `/api/after-sales` alias router: preserves older route spelling alongside `/api/aftermarket`.

## Deferred

- Porting all direct sqlite3 workflows to SQLAlchemy services.
- Consolidating `audit_log` into `audit_events`.
- Replacing static HTML screens with a component frontend.
- Splitting warehouse item master, balances, and movement history into clean service-owned aggregates.

## Not A Root Node App

The repository root is FastAPI. `pm-frontend/` is the only Node project and is used only when rebuilding PM assets. Root npm or Expo startup is not valid.
