# Template Registry

Dataset definitions live in:

`app/data_management/template_registry.py`

The registry defines:

- Dataset key
- Display name
- Domain
- Description
- Version
- Updated date
- Fields
- Required fields
- Accepted values
- Example rows
- Import/export support flags
- Export table metadata

Generated Excel templates contain:

- `Data`
- `Instructions`
- `Accepted Values`
- `Example Data`

The `Data` sheet contains headers only. Example rows are kept on `Example Data` so users do not accidentally import sample values.
