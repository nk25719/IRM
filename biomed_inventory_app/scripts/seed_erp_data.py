"""Seed ERP foundation sample data.

Run after Alembic migration:
    python scripts/seed_erp_data.py
"""
from datetime import date, timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import session_scope  # noqa: E402
from app.erp_models import Case, CaseItem, Client, Department, Equipment, InventoryItem, ProcurementRequest, ServiceCall  # noqa: E402


def get_or_create(db, model, defaults=None, **lookup):
    row = db.query(model).filter_by(**lookup).first()
    if row:
        return row
    values = {**lookup, **(defaults or {})}
    row = model(**values)
    db.add(row)
    db.flush()
    return row


def main():
    today = date.today()
    with session_scope() as db:
        city = get_or_create(
            db,
            Client,
            name="City Care Hospital",
            defaults={"location": "Beirut", "address": "Hamra Medical District", "status": "active", "financial_status": "good_standing"},
        )
        cedar = get_or_create(
            db,
            Client,
            name="Cedar Medical Center",
            defaults={"location": "Jounieh", "address": "Coastal Health Campus", "status": "active", "financial_status": "credit_hold"},
        )

        city_icu = get_or_create(db, Department, client_id=city.id, name="ICU", defaults={"floor_location": "3rd Floor", "contact_name": "Nadine Haddad", "phone": "+961-1-555-101", "email": "icu@citycare.example"})
        city_or = get_or_create(db, Department, client_id=city.id, name="Operating Room", defaults={"floor_location": "2nd Floor", "contact_name": "Karim Mansour"})
        cedar_er = get_or_create(db, Department, client_id=cedar.id, name="Emergency", defaults={"floor_location": "Ground Floor", "contact_name": "Maya Khoury"})
        cedar_rad = get_or_create(db, Department, client_id=cedar.id, name="Radiology", defaults={"floor_location": "Basement", "contact_name": "Rami Saliba"})

        vent = get_or_create(db, Equipment, client_id=city.id, serial_number="VENT-CC-1001", defaults={"department_id": city_icu.id, "name": "ICU Ventilator", "manufacturer": "MedTech", "model": "VentoPro 500", "asset_tag": "CC-ICU-VENT-01", "installation_date": today - timedelta(days=800), "status": "active", "risk_classification": "high", "life_support": True, "pm_frequency": "quarterly", "next_pm_date": today + timedelta(days=30)})
        monitor = get_or_create(db, Equipment, client_id=city.id, serial_number="MON-CC-2001", defaults={"department_id": city_or.id, "name": "Patient Monitor", "manufacturer": "CareVue", "model": "CV-7", "asset_tag": "CC-OR-MON-01", "status": "active", "risk_classification": "medium", "pm_frequency": "semi_annual"})
        pump = get_or_create(db, Equipment, client_id=cedar.id, serial_number="PUMP-CMC-3001", defaults={"department_id": cedar_er.id, "name": "Infusion Pump", "manufacturer": "InfuSafe", "model": "IS-200", "asset_tag": "CMC-ER-PUMP-01", "status": "active", "risk_classification": "medium", "calibration_required": True, "calibration_due_date": today + timedelta(days=60)})
        ultrasound = get_or_create(db, Equipment, client_id=cedar.id, serial_number="US-CMC-4001", defaults={"department_id": cedar_rad.id, "name": "Ultrasound", "manufacturer": "SonoWave", "model": "SW-9", "asset_tag": "CMC-RAD-US-01", "status": "active", "risk_classification": "low"})

        batt = get_or_create(db, InventoryItem, pn="BAT-VP500", defaults={"description": "Ventilator battery pack", "category": "spare_part", "manufacturer": "MedTech", "minimum_qty": 2, "physical_qty": 1, "reserved_qty": 0, "available_qty": 1, "location": "Main Store", "status": "low_stock"})
        cable = get_or_create(db, InventoryItem, pn="ECG-CV7-5L", defaults={"description": "5-lead ECG cable", "category": "accessory", "manufacturer": "CareVue", "minimum_qty": 3, "physical_qty": 8, "reserved_qty": 1, "available_qty": 7, "location": "Main Store", "status": "active"})
        syringe = get_or_create(db, InventoryItem, pn="SYR-IS200", defaults={"description": "Infusion pump syringe set", "category": "consumable", "manufacturer": "InfuSafe", "minimum_qty": 20, "physical_qty": 45, "reserved_qty": 5, "available_qty": 40, "location": "Consumables A", "status": "active"})

        case1 = get_or_create(db, Case, parent_case_reference="CASE-ERP-0001", defaults={"client_id": city.id, "department_id": city_icu.id, "equipment_id": vent.id, "case_type": "after_sales", "title": "Ventilator battery replacement", "description": "Battery fails self-test and requires replacement.", "status": "open", "priority": "high"})
        case2 = get_or_create(db, Case, parent_case_reference="CASE-ERP-0002", defaults={"client_id": cedar.id, "department_id": cedar_er.id, "equipment_id": pump.id, "case_type": "sales", "title": "Infusion consumables replenishment", "description": "Monthly consumables request.", "status": "open", "priority": "normal"})

        item1 = get_or_create(db, CaseItem, case_id=case1.id, item_type="spare_part", description="Ventilator battery pack", defaults={"requested_qty": 2, "unit_price": 250, "status": "pending", "procurement_status": "shortage", "inventory_item_id": batt.id})
        get_or_create(db, CaseItem, case_id=case2.id, item_type="consumable", description="Infusion pump syringe set", defaults={"requested_qty": 30, "unit_price": 8, "status": "ready", "procurement_status": "available", "inventory_item_id": syringe.id})

        get_or_create(db, ProcurementRequest, case_id=case1.id, case_item_id=item1.id, inventory_item_id=batt.id, defaults={"requested_qty": 2, "shortage_qty": 1, "procurement_status": "requested", "supplier": "MedTech Distributor", "expected_date": today + timedelta(days=14)})
        get_or_create(db, ServiceCall, case_id=case1.id, client_id=city.id, defaults={"department_id": city_icu.id, "equipment_id": vent.id, "call_type": "corrective_maintenance", "priority": "high", "status": "open", "request_date": today, "due_date": today + timedelta(days=2)})

        # Touch variables so lint does not complain when copied into stricter projects.
        _ = (monitor, ultrasound, cable)

    print("Seeded ERP sample data: 2 hospitals, 4 departments, 4 equipment records, 2 cases, 3 inventory items.")


if __name__ == "__main__":
    main()
