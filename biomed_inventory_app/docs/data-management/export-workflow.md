# Export Workflow

The export wizard follows:

1. Choose Dataset
2. Choose Columns
3. Apply Filters
4. Preview
5. Download

Supported formats:

- `.xlsx`
- `.csv`

Only registered, non-sensitive fields can be requested. Unsupported datasets or columns are rejected. Export events are recorded as audit events with dataset, filters, columns, timestamp, and row count; exported row contents are not logged.
