from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import erp_models as m  # noqa: E402
from app.database import session_scope  # noqa: E402


def clean(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none", "0000-00-00"}:
        return None
    return text


def parse_date(value: Any):
    text = clean(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def as_int(value: Any):
    text = clean(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1", "overdue"}


def row_hash(row: dict) -> str:
    payload = "|".join(str(row.get(key) or "") for key in sorted(row))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_or_create(db, model, defaults=None, **lookup):
    row = db.query(model).filter_by(**lookup).first()
    if row:
        return row, False
    row = model(**lookup, **(defaults or {}))
    db.add(row)
    db.flush()
    return row, True


def import_file(path: Path):
    pm_tracker = pd.read_excel(path, sheet_name="PM Tracker")
    equipment_tracker = pd.read_excel(path, sheet_name="Equipment PM Tracker")
    clients = contracts = equipment = pm_tasks = 0
    with session_scope() as db:
        for _, row in pm_tracker.iterrows():
            hospital = clean(row.get("Hospital"))
            contract_no = clean(row.get("Contract No."))
            if not hospital or not contract_no:
                continue
            client, created = get_or_create(db, m.Client, name=hospital, defaults={"status": "active"})
            clients += int(created)
            dept = None
            if clean(row.get("Department")):
                dept, _ = get_or_create(db, m.Department, client_id=client.id, name=clean(row.get("Department")), defaults={"contact_name": clean(row.get("Hospital Contact")), "email": clean(row.get("Contact Email"))})
            contract, created = get_or_create(
                db,
                m.Contract,
                contract_reference=contract_no,
                defaults={
                    "client_id": client.id,
                    "contract_type": "pm_contract",
                    "status": clean(row.get("Status")) or "active",
                    "pms_per_year": as_int(row.get("PMs per Year")),
                    "pm_pattern": clean(row.get("PM Pattern")),
                    "coverage_notes": clean(row.get("Notes")),
                    "source": "pm_tracker",
                },
            )
            contracts += int(created)
            engineer = None
            if clean(row.get("Engineer Assigned")):
                engineer, _ = get_or_create(db, m.Engineer, engineer_name=clean(row.get("Engineer Assigned")), defaults={"email": clean(row.get("Engineer Email")), "active": True})
            h = row_hash({key: clean(row.get(key)) for key in pm_tracker.columns})
            if not db.query(m.PMTask).filter_by(source_row_hash=h).first():
                db.add(
                    m.PMTask(
                        client_id=client.id,
                        department_id=dept.id if dept else None,
                        contract_id=contract.id,
                        scheduled_date=parse_date(row.get("Next PM Date")),
                        completed_date=parse_date(row.get("Completion Date")),
                        status=clean(row.get("Status")) or "scheduled",
                        assigned_engineer_id=engineer.id if engineer else None,
                        pm_label="PM Tracker",
                        communication_stage=clean(row.get("Communication Stage")),
                        reminder_1_sent=as_bool(row.get("Reminder 1 Sent")),
                        reminder_2_sent=as_bool(row.get("Reminder 2 Sent")),
                        final_reminder_sent=as_bool(row.get("Final Reminder Sent")),
                        engineer_alert_sent=as_bool(row.get("Engineer Alert Sent")),
                        visit_confirmed_date=parse_date(row.get("Visit Confirmed Date")),
                        overdue=as_bool(row.get("Overdue?")),
                        source="pm_tracker",
                        source_row_hash=h,
                    )
                )
                db.flush()
                pm_tasks += 1
        for _, row in equipment_tracker.iterrows():
            hospital = clean(row.get("Hospital"))
            if not hospital:
                continue
            client, created = get_or_create(db, m.Client, name=hospital, defaults={"status": "active"})
            clients += int(created)
            contract = None
            if clean(row.get("Contract No.")):
                contract, created = get_or_create(db, m.Contract, contract_reference=clean(row.get("Contract No.")), defaults={"client_id": client.id, "contract_type": "pm_contract", "source": "equipment_pm_tracker"})
                contracts += int(created)
            serial = clean(row.get("Serial Number")) or clean(row.get("Equipment ID")) or clean(row.get("Unit No."))
            eq, created = get_or_create(
                db,
                m.Equipment,
                client_id=client.id,
                serial_number=serial or f"PM-{row_hash(dict(row))[:10]}",
                defaults={
                    "name": clean(row.get("Subsystem / Equipment")) or clean(row.get("Parent System")) or "Equipment",
                    "manufacturer": clean(row.get("Manufacturer")),
                    "model": clean(row.get("Model")),
                    "asset_tag": clean(row.get("Equipment ID")),
                    "status": clean(row.get("Status")) or "active",
                    "last_pm_date": parse_date(row.get("Last PM Date")),
                    "next_pm_date": parse_date(row.get("Next PM Date")),
                    "pm_frequency": clean(row.get("PMs per Year")),
                },
            )
            equipment += int(created)
            for label in ["PM1 Date", "PM2 Date", "PM3 Date", "PM4 Date"]:
                scheduled = parse_date(row.get(label))
                if not scheduled:
                    continue
                h = row_hash({"sheet": "Equipment PM Tracker", "equipment": eq.id, "contract": contract.id if contract else None, "label": label, "date": scheduled.isoformat()})
                if not db.query(m.PMTask).filter_by(source_row_hash=h).first():
                    db.add(
                        m.PMTask(
                            client_id=client.id,
                            equipment_id=eq.id,
                            contract_id=contract.id if contract else None,
                            scheduled_date=scheduled,
                            status=clean(row.get("Status")) or "scheduled",
                            pm_label=label,
                            overdue=False,
                            source="equipment_pm_tracker",
                            source_row_hash=h,
                        )
                    )
                    db.flush()
                    pm_tasks += 1
    return {"pm_tracker_rows": len(pm_tracker), "equipment_pm_rows": len(equipment_tracker), "clients_created": clients, "contracts_created": contracts, "equipment_created": equipment, "pm_tasks_created": pm_tasks}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_pm_tracker.py /path/to/pm_tracker_with_hospital_contracts_pmcount_from_source-1.xlsx")
    summary = import_file(Path(sys.argv[1]))
    print("PM tracker import summary:")
    for key, value in summary.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
