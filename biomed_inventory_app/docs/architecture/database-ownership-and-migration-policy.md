# Database Ownership And Migration Policy

SQLAlchemy models and Alembic migrations are the schema authority.

New database work must follow these rules:

- Use SQLAlchemy sessions from `app.database`.
- Add schema changes through Alembic migrations.
- Do not create tables from request handlers.
- Do not introduce new direct `sqlite3` access.
- Keep import staging, audit, and production tables owned by their router/service domain.

Current ownership:

- CRM and contacts: `app/routers/crm_api.py`, `app/routers/customer_contacts_api.py`, CRM/contact SQLAlchemy models.
- Master data: `app/routers/master_data_api.py`, `app/services/*_service.py`, `app/models/foundation.py`.
- Data management/import staging: `app/routers/data_management_api.py`, `app/routers/imports_api.py`, `app/services/import_service.py`.
- Engineer schedule: `app/routers/schedule_api.py`, `app/schedule_models.py`, `app/services/schedule_*`.
- Service intelligence/contracts coverage: `app/routers/service_intelligence_api.py`, `app/services/service_intelligence.py`.
- Legacy operational domains still pending extraction: `app/legacy_main.py`, `app/quotation_api.py`, `app/admin_api.py`, `app/aftermarket_service_reports.py`.

Migration policy:

- One Alembic revision per behavior change or table group.
- Migrations must be reversible unless a destructive data migration is explicitly approved.
- Data backfills must be idempotent and separately runnable.
- Route code must not perform schema mutation at request time.
