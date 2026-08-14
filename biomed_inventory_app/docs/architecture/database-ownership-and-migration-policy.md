# Database Ownership And Migration Policy

PostgreSQL and SQLAlchemy are the target database architecture. Some existing workflows and tests still depend on the legacy SQLite implementation. CI runs the PostgreSQL-ready regression suite as a required check and runs the legacy compatibility suite separately to expose remaining migration work. Each legacy failure is tracked, and the compatibility suite will become required once those fixtures and modules have been migrated. New SQLite-dependent code or tests are not permitted.

## Policy

- PostgreSQL is the application and CI database.
- SQLAlchemy is the application data-access layer.
- Alembic is the only schema-creation mechanism.
- New code must not import `sqlite3`.
- New tests must not create `.db` files.
- Existing SQLite paths are compatibility code scheduled for removal.
- Database engines are created through the lazy runtime in `app.database`; tests may call `configure_database()` before opening sessions.

New database work must follow these rules:

- Use SQLAlchemy sessions from `app.database`.
- Add schema changes through Alembic migrations.
- Do not create tables from request handlers.
- Do not introduce new direct `sqlite3` access.
- Keep import staging, audit, and production tables owned by their router/service domain.

## Current Ownership

- CRM and contacts: `app/routers/crm_api.py`, `app/routers/customer_contacts_api.py`, CRM/contact SQLAlchemy models.
- Master data: `app/routers/master_data_api.py`, `app/services/*_service.py`, `app/models/foundation.py`.
- Data management/import staging: `app/routers/data_management_api.py`, `app/routers/imports_api.py`, `app/services/import_service.py`.
- Engineer schedule: `app/routers/schedule_api.py`, `app/schedule_models.py`, `app/services/schedule_*`.
- Service intelligence/contracts coverage: `app/routers/service_intelligence_api.py`, `app/services/service_intelligence.py`.
- Legacy operational domains still pending extraction: `app/legacy_main.py`, `app/quotation_api.py`, `app/admin_api.py`, `app/aftermarket_service_reports.py`.

## Migration Policy

- One Alembic revision per behavior change or table group.
- Migrations must be reversible unless a destructive data migration is explicitly approved.
- Data backfills must be idempotent and separately runnable.
- Route code must not perform schema mutation at request time.
- Runtime startup must not create or mutate tables. Add missing schema to Alembic, run `alembic upgrade head` during deployment, and fail clearly when migrations are missing.
- Avoid import-time database connections. Importing application modules must not connect to PostgreSQL before tests or application setup can configure the database URL.

## Migration Order

1. Read-only dashboard queries.
2. CRM/customer contacts.
3. Engineer scheduling.
4. Warehouse reads.
5. Warehouse mutations and stock ledger.
6. Procurement.
7. Quotations and pricing.
8. After-Sales/service workflows.
9. Admin backup/query functionality.

For each domain:

- Introduce a repository or service using a SQLAlchemy session.
- Point the router at the new service.
- Port its tests to PostgreSQL.
- Verify behavior parity.
- Remove the corresponding SQLite functions.
- Remove its startup `ensure_*_tables()` call.
- Make Alembic own its schema.

## Migration Matrix

| Module | Direct SQLite | SQLAlchemy | PostgreSQL tests | Startup table creation | Status | Tracking |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Static/frontend routing | No | N/A | N/A | No | Complete | `tests/unit`, `tests.test_static_layout` |
| Service intelligence | No | Yes | Partial | Yes | Migrating | create issue: migrate startup schema to Alembic only |
| Data Management | No | Yes | Partial | No | Migrating | create issue: move tests to `tests/postgres` |
| CRM/client read list | Partial | Partial | No | Yes | Migrating | create issue: finish CRM read/write extraction |
| Customer contacts | Partial | Yes | No | Yes | Migrating | create issue: port fixtures to PostgreSQL |
| Engineer schedule | Partial | Yes | No | Yes | Migrating | create issue: port fixtures to PostgreSQL |
| Warehouse | Yes | Partial | No | Yes | Not started | create issue: warehouse read extraction |
| Procurement | Yes | Partial | No | Yes | Not started | create issue: procurement extraction |
| Quotations/pricing | Yes | Partial | No | Yes | Not started | create issue: quotation SQLAlchemy service |
| After-Sales/service reports | Yes | Partial | No | Yes | Not started | create issue: aftermarket service report migration |
| Admin backup/query | Yes | Partial | No | Yes | Not started | create issue: admin PostgreSQL backup/query behavior |
