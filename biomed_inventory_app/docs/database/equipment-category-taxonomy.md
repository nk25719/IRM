# Equipment Category Taxonomy

Equipment categories describe biomedical device families, not stock movement, procurement intent, or quotation lines.

## Baseline Taxonomy

`scripts/seed_master_data.py` seeds a conservative baseline:

- Patient Monitoring
- ECG
- Multiparameter Monitor
- Diagnostic Imaging
- Ultrasound
- X-Ray
- Respiratory
- Ventilator
- Spirometer
- Infusion
- Infusion Pump
- Syringe Pump
- Parts and Accessories
- Spare Part
- Accessory

The seed script is idempotent and dry-run by default.

## Review Rules

- Category aliases live in `equipment_category_aliases`.
- Alias matching is trusted only when `is_verified=true`.
- Operational labels such as `spare_parts` and `accessories` should be reviewed before use as equipment model categories.
- Long descriptions should not be mapped directly unless they clearly identify a device family.
- Backfills may set `equipment_models.equipment_category_id` only when the FK is currently null.

## Review CSV

`config/master_data/equipment_category_mapping.csv` is generated with `approved=false`. Human review must set `approved=true` and provide a canonical category before any row can affect equipment models.
