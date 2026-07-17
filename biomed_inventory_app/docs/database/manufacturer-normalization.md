# Manufacturer Normalization

Manufacturers are canonical legal or brand owners of equipment models.

## Rules

- Store canonical rows in `manufacturers`.
- Store alternate spellings, old labels, abbreviations, and import-specific text in `manufacturer_aliases`.
- Alias matching is only trusted when `is_verified=true`.
- A generated mapping row is not actionable until `approved=true`.
- Backfills may set `equipment_models.manufacturer_id` only when the FK is currently null.
- Backfills must not overwrite existing manufacturer links silently.

## Review CSV

`config/master_data/manufacturer_mapping.csv` columns:

- `approved`: `true`, `yes`, `1`, or `approved` enables the row.
- `raw_value`: original source text.
- `normalized_value`: normalized lookup key.
- `canonical_code`: preferred canonical manufacturer code, if known.
- `canonical_name`: preferred canonical manufacturer name, if known.
- `match_action`: review note such as `map`, `create`, or `review`.
- `alias_source`: source table and column.
- `confidence`: profiler confidence.
- `review_notes`: human decision notes.

Rows left unapproved are ignored by `scripts/backfill_equipment_model_master_data.py`.
