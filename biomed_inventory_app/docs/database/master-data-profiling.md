# Master Data Profiling

This milestone profiles manufacturer and equipment category candidates without changing production data.

## Outputs

Manufacturer profiling:

- `artifacts/database/manufacturer-values.csv`
- `artifacts/database/manufacturer-duplicate-candidates.csv`
- `artifacts/database/manufacturer-unmatched-values.csv`
- `artifacts/database/equipment-model-manufacturer-profile.csv`
- `config/master_data/manufacturer_mapping.csv`

Equipment category profiling:

- `artifacts/database/equipment-category-values.csv`
- `artifacts/database/equipment-category-candidates.csv`
- `artifacts/database/equipment-category-unmatched.csv`
- `config/master_data/equipment_category_mapping.csv`

The mapping CSVs are review gates. Generated rows default to `approved=false`; the backfill script ignores them until an approved canonical target is present.

## Commands

```bash
python3 scripts/profile_manufacturer_data.py
python3 scripts/profile_equipment_category_data.py
```

Current local profiling found no populated manufacturer values in `equipment_models`, `equipment`, or asset tables. Category-like values are mostly operational labels and descriptions, including `spare_parts`, `accessories`, and inventory descriptions. These require human review before they should become equipment category mappings.
