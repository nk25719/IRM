# Database Foundation Implementation

This milestone adds normalized database foundations without removing or renaming existing production tables.

## New Tables

- `manufacturers`: normalized manufacturer master data.
- `suppliers`: normalized supplier master data.
- `client_sites`: site-level structure under existing `clients`.
- `locations`: nested physical locations linked to clients, sites, departments, or parent locations.
- `equipment_categories`: hierarchical equipment category master data.
- `import_rows`: raw and normalized row-level import staging.
- `data_validation_errors`: validation errors produced during imports or data cleanup.
- `audit_events`: append-only audit event log.
- `status_history`: generic append-only status transition history.

## Existing Tables Extended

- `equipment_models.manufacturer_id`
- `equipment_models.equipment_category_id`
- `import_batches` receives foundation import tracking columns while retaining legacy admin import columns.

## Compatibility

Legacy text fields remain available. `equipment_models.manufacturer` and `equipment_models.model` are not removed. Existing `Equipment`, `Client`, and `Department` tables are still authoritative for current application behavior. Backfilling normalized manufacturer/category references is intentionally left for a reviewed data-migration step.

## Environment Variables

- `DATABASE_URL`: primary SQLAlchemy database URL.
- `DB_PATH`: legacy SQLite path used by modules that still call `sqlite3` directly.
- `IRM_DATA_ROOT`: persistent file storage root for attachments, imports, exports, backups, and logs.

## SQLite Development

```bash
export DATABASE_URL=sqlite:///./app/data/irm.db
alembic upgrade head
pytest
```

SQLite foreign keys are enabled through SQLAlchemy connection events for the shared engine.

## Upgrade

```bash
cp app/data/inventory.db app/data/inventory.backup-before-foundation.db
export DATABASE_URL=sqlite:///./app/data/inventory.db
alembic upgrade head
pytest
```

## Downgrade

```bash
export DATABASE_URL=sqlite:///./app/data/inventory.db
alembic downgrade -1
```

Downgrade removes only the additive foundation objects from this revision. Do not run downgrade on production without a backup.

## Known Limitations

- Legacy `sqlite3` modules still use `DB_PATH`.
- No automatic manufacturer/category backfill is performed.
- Audit and status-history tables are foundations; existing workflows still write their current status fields.

## Next Milestone

Profile existing equipment manufacturer/model data, review duplicate resolution rules, and backfill `equipment_models.manufacturer_id` plus `equipment_models.equipment_category_id`.
