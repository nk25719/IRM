# Data Management Center Overview

The Data Management Center appears under `Administration -> Data Management` at `/administration/data-management`.

It provides:

- Import staging through `import_batches`, `import_rows`, and `data_validation_errors`.
- Template downloads generated from a central registry.
- Read-only import history and validation-center views.
- Read-only data-quality metrics.
- Export preview and download for implemented datasets.

The module intentionally separates:

- Download Template: empty approved structure.
- Export Data: current database records.
- Import Data: staged upload and validation.

Final production-table import execution is intentionally deferred for datasets that need richer normalization or duplicate resolution.
