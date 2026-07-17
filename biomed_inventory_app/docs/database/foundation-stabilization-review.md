# Foundation Stabilization Review

## Findings Before Fixes

- `DATABASE_URL` and `DB_PATH` could point to two different SQLite files.
- Legacy sqlite3 modules did not clearly reject PostgreSQL configuration.
- `app.models.__init__` imported foundation models as a side effect; this polluted the original 20260524 migration metadata.
- The original foundation migration attempted to sort current metadata after `equipment_models` gained FKs to not-yet-created foundation tables.
- Adding `import_batches.started_at` with `CURRENT_TIMESTAMP` failed on SQLite existing tables.
- Downgrade dropped referenced foundation tables before removing `equipment_models` FK columns.
- Services did not reject a second primary site or self-parent location/category updates.
- New master-data routers were missing some get/restore endpoints.
- Docker Compose mapped host port 8000 to container port 8000 while the Dockerfile starts Uvicorn on 8080.

## Fixes Applied

- Added `app/config/database.py` with `get_database_url()`, `is_sqlite_database()`, `is_postgresql_database()`, and `get_sqlite_database_path()`.
- Updated SQLAlchemy engine creation to use the shared database URL and exposed `build_engine()` for tests.
- Updated legacy sqlite3 consumers to derive SQLite paths from the shared configuration.
- Legacy sqlite3 access now fails clearly when `DATABASE_URL` is PostgreSQL.
- Removed foundation side-effect imports from `app/models/__init__.py`.
- Patched the old 20260524 migration to skip unresolved future-FK columns and indexes.
- Patched the foundation migration for SQLite-safe existing-table column additions and safe downgrade ordering.
- Added service validations for duplicate primary client sites and self-parent location/category updates.
- Added missing read/restore endpoints for master-data resources.
- Fixed Docker Compose app port mapping to target container port 8080.

## Import Batch Compatibility

| Original column | Original type | Original nullable/default | Original index/constraint | New definition | Compatibility risk |
| --- | --- | --- | --- | --- | --- |
| id | Integer PK | required | primary key | unchanged | none |
| import_type | String(80) | nullable | none | unchanged legacy column | none |
| target_table | String(120) | nullable | `ix_import_batches_target_table` | unchanged legacy column | none |
| filename | String(255) | nullable | none | unchanged legacy column | none |
| status | String(40) default preview | nullable/server default in original migration | indexed by new `ix_import_batches_status` | reused by foundation model as String(50) application status | low; no type migration is applied |
| total_rows | Integer default 0 | nullable/server default in original migration | none | reused | low |
| valid_rows | Integer default 0 | nullable/server default | none | unchanged legacy column | none |
| error_rows | Integer default 0 | nullable/server default | none | unchanged legacy column | none |
| saved_rows | Integer default 0 | nullable/server default | none | unchanged legacy column | none |
| created_by | String(120) | nullable | none | unchanged legacy column | none |
| created_at | DateTime default now | nullable/server default | none | reused by TimestampMixin semantics | low |
| committed_at | DateTime | nullable | none | unchanged legacy column | none |
| rolled_back_at | DateTime | nullable | none | unchanged legacy column | none |
| mapping_json | Text | nullable | none | unchanged legacy column | none |
| preview_json | Text | nullable | none | unchanged legacy column | none |
| source_columns_json | Text | nullable | none | unchanged legacy column | none |
| notes | Text | nullable | none | reused | none |
| source_type | String(80) | new nullable column | none | added | safe additive |
| source_filename | String(255) | new nullable column | `ix_import_batches_source_filename` | added | safe additive |
| source_checksum | String(128) | new nullable column | `ix_import_batches_source_checksum` | added | safe additive |
| imported_by_id | Integer FK users.id SET NULL | new nullable column | FK | added via batch mode | safe additive |
| started_at | DateTime | new nullable column | `ix_import_batches_started_at` | added without SQLite-invalid default | safe additive |
| completed_at | DateTime | new nullable column | none | added | safe additive |
| processed_rows | Integer default 0 | new nullable/server default | none | added | safe additive |
| successful_rows | Integer default 0 | new nullable/server default | none | added | safe additive |
| failed_rows | Integer default 0 | new nullable/server default | none | added | safe additive |

The migration does not recreate `import_batches`, does not rename existing columns, and the test `test_import_batches_old_row_survives_upgrade_and_new_columns_downgrade` verifies that an old-format row survives upgrade and downgrade.

## Database Path Divergence

| File | Function | Access method | Database path source | Read/write | Risk |
| --- | --- | --- | --- | --- | --- |
| `app/database.py` | module engine | SQLAlchemy | `get_database_url()` | read/write | low after fix |
| `app/database.py` | `get_db`, `session_scope` | SQLAlchemy SessionLocal | shared engine | read/write | low |
| `app/legacy_main.py` | `db` | `sqlite3.connect` | `get_sqlite_database_path()` | read/write | medium: disabled for PostgreSQL |
| `app/quotation_api.py` | `connect` | `sqlite3.connect` | `get_sqlite_database_path()` | read/write | medium: disabled for PostgreSQL |
| `app/admin_api.py` | `sqlite_path` | sqlite file helpers | `get_sqlite_database_path()` | read/write/admin backup | medium: PostgreSQL path handled separately |
| `app/admin_api.py` | database map | SQLAlchemy or sqlite3 | `DATABASE_URL`/shared helper | read | low |

The application can no longer silently connect SQLAlchemy to one SQLite file and legacy sqlite3 to another when `DATABASE_URL` is configured. If only legacy `DB_PATH` is configured, `get_database_url()` derives a SQLite URL from it for compatibility.

## Model Registration

- `Base` is defined once in `app/database.py`.
- `app/models/base.py` re-exports that same `Base`.
- `erp_models.py` and `app/models/foundation.py` use the same metadata.
- `app/models/__init__.py` no longer imports foundation models as a side effect.
- Tests assert expected existing and foundation tables are present in active metadata after explicit imports.
- Alembic foundation migration uses explicit operations. The old metadata-driven migration was patched to avoid future-FK pollution.

## Migration Safety

- Empty disposable database: `alembic upgrade head`, `alembic downgrade -1`, and `alembic upgrade head` passed.
- Existing database copy: upgrade passed.
- Existing important row counts matched before and after upgrade.
- New foundation tables were present after upgrade.
- `equipment_models.manufacturer_id` and `equipment_models.equipment_category_id` were present after upgrade.
- `PRAGMA integrity_check` returned `ok`.
- `PRAGMA foreign_key_check` returned zero rows.

## Tests Added

- Metadata registration.
- Shared SQLite path resolution.
- PostgreSQL rejection for legacy sqlite3 path access.
- Existing `import_batches` preservation across upgrade/downgrade.
- Duplicate manufacturer code/name behavior.
- Rollback after failed service commit.
- Primary client-site enforcement.
- Self-parent rejection for locations and categories.
- Import row unique constraint.
- JSON round trip.
- API 404 and 409 behavior by direct router call.
- Audit append-only behavior.
- Status history identical-state rejection.
- Application startup and route registration.

## Test Results

- `python3 -m compileall app tests`: passed.
- `python3 -m unittest tests.test_database_foundation -v`: passed, 17 tests.
- `python3 -m unittest tests.test_aftermarket_service_reports tests.test_quotation_generator -v`: passed, 9 tests.
- `python3 -m unittest discover -s tests -v`: 29 passed, 4 legacy workflow failures.

## Legacy Failures Still Present

- `test_pending_offer_import_department_progress_search_and_bulk_edit`: `external_reference` is `None`.
- `test_procurement_assigns_unassigned_client_order_items_to_po`: quotation approval gate raises HTTP 400.
- `test_procurement_tracks_duplicate_refs_as_separate_rows`: quotation approval gate raises HTTP 400.
- `test_service_hospital_follow_up_tracks_service_department_buckets`: expected score 4, actual score 5.

These failures are outside the database foundation and existed during the milestone verification pass.

## PostgreSQL Deployment Readiness

- PostgreSQL driver `psycopg[binary]` is listed.
- Compose uses PostgreSQL 16, named volume, health check, and app dependency on a healthy database.
- Database port is not exposed.
- App file storage uses a named volume mounted at `/data/irm`.
- Dockerfile exists and installs requirements.
- Gap: legacy sqlite3-only modules are still part of the active app; PostgreSQL runtime can import the app, but legacy endpoints that call sqlite3 are disabled/fail clearly until they are migrated.
- Alembic execution is documented but not automatically run by Compose startup.

## Remaining Risks

- New mutation endpoints inherit the current app/session middleware, but there is no route-specific admin authorization in these routers yet.
- Legacy sqlite3 paths still exist and are intentionally disabled for PostgreSQL rather than ported.
- Manufacturer normalized-name uniqueness is implemented through application normalization plus a portable unique column. This avoids database-specific functional indexes but requires all writes to use services.
- Only direct self-parent is rejected for locations/categories; deeper cycles require a later recursive validation pass.
- Soft-deleted rows still participate in unique constraints.

## Recommendation

I recommend applying the foundation migration to a backed-up copy first, then to the main development database if the same integrity and row-count checks pass. The migration is additive, preserves existing `import_batches` data, and passed SQLite integrity and foreign-key checks on a disposable copy of the current database. Do not start data backfilling until a separate duplicate-resolution plan is reviewed.
