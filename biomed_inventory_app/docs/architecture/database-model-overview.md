# Database Model Overview

Date: 2026-07-18

## Schema Authority

Alembic migrations are the committed schema authority. The local SQLite file at `app/data/inventory.db` is replaceable runtime state and is ignored by Git.

## Model Families

- `app/erp_models.py`: original SQLAlchemy ERP model set for clients, equipment, service calls, PM tasks, cases, inventory items, procurement, and quotations.
- `app/models/foundation.py`: foundation models for manufacturers, suppliers, client sites, locations, equipment categories, import staging, validation errors, audit events, and status history.
- `app/models/mixins.py`: timestamp, soft-delete, and audit-user mixins.
- Legacy sqlite3 tables: created and evolved by `legacy_main.init_db()` and module-specific helpers while legacy workflows remain active.

## Audit Tables

Two audit concepts remain active:

- `audit_log`: legacy/admin runtime table. Warehouse audit entries use `item_id`; admin import entries use `table_name` and `record_id`.
- `audit_events`: canonical SQLAlchemy audit table for new foundation and Data Management work, keyed by `entity_type` and `entity_id`.

Decision: keep both for this checkpoint. Consolidating `audit_log` into `audit_events` would require replacing legacy warehouse/admin callers, UI reads, export reads, and tests. That should be a dedicated migration and adapter milestone, not a cleanup side effect.

## Migration Chain

Current head:

```text
20260716_equipment_model_master_fks
```

The branch-local import-batch timestamp repair migration was removed during cleanup. `created_at` and `updated_at` are part of the foundation migration so fresh databases receive the final import-batch shape directly.
