# Data Management Call Graph

Date: 2026-07-18

## Browser Flow

```text
GET /administration/data-management
  -> app.routers.web_pages
  -> app/static/data_management.html
  -> app/static/app_layout.js shared shell
  -> app/static/theme.css shared styling
```

Unauthenticated page requests redirect to `/login`.

## API Flow

```text
Data Management UI
  -> GET /api/data-management/datasets
     -> template_registry.list_datasets()

  -> GET /api/data-management/templates/{dataset}/download
     -> template_registry.get_dataset()
     -> openpyxl workbook builder

  -> POST /api/data-management/imports/upload
     -> file size/type checks
     -> pandas/openpyxl/csv parser
     -> registry header mapping
     -> required-field validation
     -> ImportBatch
     -> ImportRow
     -> DataValidationError
     -> AuditEvent

  -> POST /api/data-management/imports/{batch_id}/confirm
     -> blocks unresolved validation errors
     -> marks clean batch ready_for_execution
     -> does not write production tables

  -> POST /api/data-management/exports/preview
     -> registry allow-list
     -> table/column inspection
     -> guarded SELECT

  -> POST /api/data-management/exports/download
     -> preview result
     -> CSV/XLSX response
     -> AuditEvent
```

## Boundary

Data Management currently stages and reviews data. It does not execute staged rows into department-owned production tables. Execution must wait for dataset grain, duplicate policy, validation correction, rollback, and department service ownership decisions.
