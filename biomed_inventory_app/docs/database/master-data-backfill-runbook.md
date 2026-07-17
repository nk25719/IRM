# Master Data Backfill Runbook

This runbook keeps manufacturer and category cleanup reviewable and reversible.

## Safety Gates

1. Back up the database outside the repo.
2. Run Alembic migrations.
3. Generate profiling artifacts.
4. Review `config/master_data/*_mapping.csv`.
5. Keep unapproved rows as `approved=false`.
6. Run seed and backfill scripts in dry-run mode.
7. Apply only to a disposable copy first.
8. Apply to the main dev DB only after review approval.

## Commands

```bash
python3 -m alembic upgrade head
python3 scripts/profile_manufacturer_data.py
python3 scripts/profile_equipment_category_data.py
python3 scripts/seed_master_data.py --dry-run
python3 scripts/backfill_equipment_model_master_data.py --dry-run
```

Apply category seed data:

```bash
python3 scripts/seed_master_data.py --apply
```

Apply approved equipment model FK mappings:

```bash
python3 scripts/backfill_equipment_model_master_data.py --apply
```

## Reconciliation

Backfill dry-runs and applies write:

- `artifacts/database/equipment-model-master-data-backfill-reconciliation.csv`

Each row records the equipment model, selected action, target FK, and reason. Actions of `blocked_existing_fk` mean the script found a possible match but refused to overwrite an existing FK.

## Current Stop Point

For this milestone, do not apply manufacturer/category backfills to the main dev DB. The main dev DB may receive schema migrations and profiling reads, but equipment model FK updates must stop at dry-run until the mapping CSVs are reviewed.
