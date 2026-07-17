# Safe Migration Plan

No destructive migrations should be generated until profiling and reconciliation are complete.

## Phases

1. Backup current database and export schema snapshots.
2. Profile duplicates and invalid references.
3. Create normalized tables additively.
4. Backfill master data and links.
5. Validate constraints before enforcing.
6. Run dual-read/write compatibility.
7. Migrate APIs from raw sqlite/legacy paths to domain services.
8. Reconcile counts/totals.
9. Remove deprecated fields only after clients are migrated.
10. Roll back by restoring backup and disabling new writes; additive migrations keep old columns.

## Field Removal Migration Map

| field | migration |
| --- | --- |
| equipment.manufacturer, equipment.model, equipment.equipment_model_id | backfill equipment_models from distinct manufacturer/model then set equipment_model_id; legacy screens/imports may read/write strings |
| inventory_items.physical_qty, reserved_qty, available_qty | create inventory_transactions from initial balances and maintain stock_balances; warehouse UI expects direct quantity columns |
| quotations.quotation_number and quotation_no | coalesce into quotation_number; keep quotation_no read alias; old payloads use quotation_no |
| quotations.subtotal,total_amount,amount and quotation_items.line_total,total_price,qty/quantity | recompute totals; deprecate amount,total_price,qty; exports/UI may consume old fields |
| service_reports equipment_model/equipment_serial_number/institution plus equipment_asset_id/equipment_id | retain snapshots, resolve FK links; imports rely on raw text |
| users.role plus roles/user_roles | backfill user_roles from users.role; middleware reads session role |

## Recommended First Milestone
Create additive master-data tables for manufacturers, equipment categories, and normalized equipment models; backfill `equipment.equipment_model_id` while preserving `equipment.manufacturer` and `equipment.model`.
