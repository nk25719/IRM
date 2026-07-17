# Import Framework

The import foundation separates raw incoming files from normalized records.

## Tables

- `import_batches`: one import job or uploaded source file.
- `import_rows`: each raw row and optional normalized representation.
- `data_validation_errors`: validation errors and warnings linked to a batch or row.

## Intended Flow

```text
file upload -> import_batches -> import_rows -> validation -> data_validation_errors -> reviewed backfill
```

This milestone does not implement full Excel processing. It provides models, schemas, services, and basic batch API support so future import workflows can be built without writing directly into production tables.

## JSON Storage

`raw_data`, `normalized_data`, and audit JSON fields use SQLAlchemy JSON with PostgreSQL JSONB variants for PostgreSQL deployments.

## Known Limitations

- No automatic master-data creation from arbitrary import text.
- No duplicate resolution is performed silently.
- Existing admin import tables and pages remain compatible.
