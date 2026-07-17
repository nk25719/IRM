from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.erp_models import EquipmentModel
from app.models.foundation import EquipmentCategory, EquipmentCategoryAlias, Manufacturer, ManufacturerAlias
from app.schemas.common import normalized_name
from scripts.master_data_utils import ARTIFACT_DIR, CONFIG_DIR, approved, read_mapping, write_csv


MANUFACTURER_MAPPING = CONFIG_DIR / "manufacturer_mapping.csv"
CATEGORY_MAPPING = CONFIG_DIR / "equipment_category_mapping.csv"
RECONCILIATION_FILE = ARTIFACT_DIR / "equipment-model-master-data-backfill-reconciliation.csv"


def _clean(value: object) -> str:
    return str(value or "").strip()


def _approved_by_normalized(path: Path) -> dict[str, dict]:
    return {row["normalized_value"]: row for row in read_mapping(path) if approved(row.get("approved")) and row.get("normalized_value")}


def _manufacturer_for_mapping(db: Session, row: dict) -> Manufacturer | None:
    code = _clean(row.get("canonical_code"))
    name = _clean(row.get("canonical_name"))
    if code:
        found = db.query(Manufacturer).filter(Manufacturer.code == code).first()
        if found:
            return found
    if name:
        normalized = normalized_name(name)
        return db.query(Manufacturer).filter(Manufacturer.normalized_name == normalized).first()
    return None


def _category_for_mapping(db: Session, row: dict) -> EquipmentCategory | None:
    code = _clean(row.get("canonical_code"))
    name = _clean(row.get("canonical_name"))
    if code:
        found = db.query(EquipmentCategory).filter(EquipmentCategory.code == code).first()
        if found:
            return found
    if name:
        normalized = normalized_name(name)
        return db.query(EquipmentCategory).filter(EquipmentCategory.normalized_name == normalized).first()
    return None


def _verified_manufacturer_alias(db: Session, raw_value: str) -> Manufacturer | None:
    alias = (
        db.query(ManufacturerAlias)
        .filter(
            ManufacturerAlias.normalized_alias == normalized_name(raw_value),
            ManufacturerAlias.is_verified.is_(True),
            ManufacturerAlias.is_deleted.is_(False),
        )
        .first()
    )
    return db.get(Manufacturer, alias.manufacturer_id) if alias else None


def _verified_category_alias(db: Session, raw_value: str) -> EquipmentCategory | None:
    alias = (
        db.query(EquipmentCategoryAlias)
        .filter(
            EquipmentCategoryAlias.normalized_alias == normalized_name(raw_value),
            EquipmentCategoryAlias.is_verified.is_(True),
            EquipmentCategoryAlias.is_deleted.is_(False),
        )
        .first()
    )
    return db.get(EquipmentCategory, alias.equipment_category_id) if alias else None


def plan_backfill(db: Session) -> tuple[list[dict], list[EquipmentModel]]:
    manufacturer_map = _approved_by_normalized(MANUFACTURER_MAPPING)
    category_map = _approved_by_normalized(CATEGORY_MAPPING)
    reconciliation = []
    changed = []

    for model in db.query(EquipmentModel).order_by(EquipmentModel.id).all():
        manufacturer_raw = _clean(getattr(model, "manufacturer", ""))
        model_raw = _clean(getattr(model, "model", ""))
        manufacturer = None
        category = None
        manufacturer_reason = "no raw manufacturer"
        category_reason = "no raw model/category value"

        if manufacturer_raw:
            manufacturer_row = manufacturer_map.get(normalized_name(manufacturer_raw))
            manufacturer = _manufacturer_for_mapping(db, manufacturer_row) if manufacturer_row else _verified_manufacturer_alias(db, manufacturer_raw)
            manufacturer_reason = "approved mapping" if manufacturer_row and manufacturer else "verified alias" if manufacturer else "unapproved or unresolved"

        if model_raw:
            category_row = category_map.get(normalized_name(model_raw))
            category = _category_for_mapping(db, category_row) if category_row else _verified_category_alias(db, model_raw)
            category_reason = "approved mapping" if category_row and category else "verified alias" if category else "unapproved or unresolved"

        manufacturer_action = "skip"
        category_action = "skip"
        if manufacturer and model.manufacturer_id is None:
            manufacturer_action = "set"
        elif manufacturer and model.manufacturer_id is not None:
            manufacturer_action = "blocked_existing_fk"
            manufacturer_reason = "existing manufacturer_id not overwritten"
        if category and model.equipment_category_id is None:
            category_action = "set"
        elif category and model.equipment_category_id is not None:
            category_action = "blocked_existing_fk"
            category_reason = "existing equipment_category_id not overwritten"

        if manufacturer_action == "set" or category_action == "set":
            changed.append(model)
        reconciliation.append(
            {
                "equipment_model_id": model.id,
                "model": model_raw,
                "manufacturer": manufacturer_raw,
                "manufacturer_action": manufacturer_action,
                "manufacturer_id": manufacturer.id if manufacturer else "",
                "manufacturer_reason": manufacturer_reason,
                "category_action": category_action,
                "equipment_category_id": category.id if category else "",
                "category_reason": category_reason,
            }
        )
    return reconciliation, changed


def apply_backfill(db: Session) -> list[dict]:
    reconciliation, _ = plan_backfill(db)
    for row in reconciliation:
        model = db.get(EquipmentModel, int(row["equipment_model_id"]))
        if row["manufacturer_action"] == "set":
            if model.manufacturer_id is not None:
                raise RuntimeError(f"equipment_model {model.id} manufacturer_id changed during backfill")
            model.manufacturer_id = int(row["manufacturer_id"])
        if row["category_action"] == "set":
            if model.equipment_category_id is not None:
                raise RuntimeError(f"equipment_model {model.id} equipment_category_id changed during backfill")
            model.equipment_category_id = int(row["equipment_category_id"])
    return reconciliation


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill equipment model manufacturer/category FKs. Defaults to dry-run.")
    parser.add_argument("--apply", action="store_true", help="Write approved mappings in a single transaction.")
    parser.add_argument("--dry-run", action="store_true", help="Explicitly run without writing data.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.apply:
            with db.begin():
                reconciliation = apply_backfill(db)
            mode = "applied"
        else:
            reconciliation, _ = plan_backfill(db)
            mode = "dry-run"

        write_csv(
            RECONCILIATION_FILE,
            [
                "equipment_model_id",
                "model",
                "manufacturer",
                "manufacturer_action",
                "manufacturer_id",
                "manufacturer_reason",
                "category_action",
                "equipment_category_id",
                "category_reason",
            ],
            reconciliation,
        )
        set_count = sum(1 for row in reconciliation if row["manufacturer_action"] == "set" or row["category_action"] == "set")
        print(f"{mode}: {set_count} equipment model rows would change")
        print(f"wrote {RECONCILIATION_FILE}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
