# Data Management Current Status

Date: 2026-07-18

## Active

- Dataset registry in `app/data_management/template_registry.py`.
- Data Management static UI at `/administration/data-management`.
- API router at `/api/data-management`.
- Template downloads.
- CSV/XLSX upload staging.
- Required-field validation.
- Import batch and row history.
- Validation error listing.
- Confirm action that marks clean batches as ready for future execution.
- Limited allow-listed export preview/download.
- Audit events for Data Management operations.

## Explicitly Deferred

- Writing staged rows into production department tables.
- Mapping profile persistence.
- Duplicate merge workflows.
- Alias auto-resolution.
- Validation correction editing.
- Department-specific execution services.
- Stock/procurement side effects.

## Authentication Behavior

Unauthenticated users are redirected from the page to `/login`; unauthenticated API calls return `401`.
