# Data Management Security

Current controls:

- Data Management routes are protected by the existing authenticated Administration flow.
- `data_management.*` permissions are registered for future granular authorization.
- Upload filenames are sanitized and replaced with generated server-side names.
- Uploads are stored under `IRM_DATA_ROOT`, not inside the source tree by default.
- File size is limited to 10 MB.
- Only `.csv` and `.xlsx` uploads are accepted.
- Dataset keys are validated against the template registry.
- Export columns are validated against registry definitions.
- Sensitive registry fields are excluded from export selection.
- Arbitrary SQL filters are not accepted.
- Export audit events record metadata only, not row contents.

Known limitation:

Granular role enforcement still depends on the app's existing permission middleware. Admin has the full permission set; non-admin role tuning should be completed in a later hardening milestone.
