from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.foundation import EquipmentCategory
from app.schemas.common import normalized_name


@dataclass(frozen=True)
class CategorySeed:
    code: str
    name: str
    parent_code: str | None = None
    description: str | None = None


CATEGORY_SEEDS = [
    CategorySeed("PATIENT_MONITORING", "Patient Monitoring"),
    CategorySeed("ECG", "ECG", "PATIENT_MONITORING"),
    CategorySeed("MULTIPARAMETER_MONITOR", "Multiparameter Monitor", "PATIENT_MONITORING"),
    CategorySeed("DIAGNOSTIC_IMAGING", "Diagnostic Imaging"),
    CategorySeed("ULTRASOUND", "Ultrasound", "DIAGNOSTIC_IMAGING"),
    CategorySeed("XRAY", "X-Ray", "DIAGNOSTIC_IMAGING"),
    CategorySeed("RESPIRATORY", "Respiratory"),
    CategorySeed("VENTILATOR", "Ventilator", "RESPIRATORY"),
    CategorySeed("SPIROMETER", "Spirometer", "RESPIRATORY"),
    CategorySeed("INFUSION", "Infusion"),
    CategorySeed("INFUSION_PUMP", "Infusion Pump", "INFUSION"),
    CategorySeed("SYRINGE_PUMP", "Syringe Pump", "INFUSION"),
    CategorySeed("PARTS_ACCESSORIES", "Parts and Accessories"),
    CategorySeed("SPARE_PART", "Spare Part", "PARTS_ACCESSORIES"),
    CategorySeed("ACCESSORY", "Accessory", "PARTS_ACCESSORIES"),
]


def plan_category_seed(db: Session) -> list[dict]:
    existing = {category.code: category for category in db.query(EquipmentCategory).all()}
    planned = []
    for seed in CATEGORY_SEEDS:
        parent = existing.get(seed.parent_code) if seed.parent_code else None
        existing_category = existing.get(seed.code)
        if existing_category:
            action = "exists"
        else:
            action = "create"
        planned.append(
            {
                "action": action,
                "code": seed.code,
                "name": seed.name,
                "parent_code": seed.parent_code or "",
                "parent_id": parent.id if parent else "",
            }
        )
        if action == "create":
            category = EquipmentCategory(
                code=seed.code,
                name=seed.name,
                normalized_name=normalized_name(seed.name),
                description=seed.description,
                parent_category_id=parent.id if parent else None,
                status="active",
            )
            existing[seed.code] = category
    return planned


def apply_category_seed(db: Session) -> list[dict]:
    existing = {category.code: category for category in db.query(EquipmentCategory).all()}
    applied = []
    for seed in CATEGORY_SEEDS:
        if seed.code in existing:
            applied.append({"action": "exists", "code": seed.code, "name": seed.name})
            continue
        parent = existing.get(seed.parent_code) if seed.parent_code else None
        category = EquipmentCategory(
            code=seed.code,
            name=seed.name,
            normalized_name=normalized_name(seed.name),
            description=seed.description,
            parent_category_id=parent.id if parent else None,
            status="active",
        )
        db.add(category)
        db.flush()
        existing[seed.code] = category
        applied.append({"action": "created", "code": seed.code, "name": seed.name})
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed safe baseline master data. Defaults to dry-run.")
    parser.add_argument("--apply", action="store_true", help="Write the seed rows. Without this flag no data is changed.")
    parser.add_argument("--dry-run", action="store_true", help="Explicitly run without writing data.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.apply:
            with db.begin():
                rows = apply_category_seed(db)
            mode = "applied"
        else:
            rows = plan_category_seed(db)
            mode = "dry-run"
        for row in rows:
            print(row)
        print(f"{mode}: {sum(1 for row in rows if row['action'] in {'create', 'created'})} category rows")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
