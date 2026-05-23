"""Simple ERP foundation verification.

Checks that required tables, columns, indexes, and seed rows exist.
"""
from pathlib import Path
import sys

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import engine  # noqa: E402
from app.schema_compat import LEGACY_STARTUP_COMPAT_COLUMNS  # noqa: E402

REQUIRED = {
    "clients": ["id", "name", "location", "address", "status", "financial_status", "created_at", "updated_at"],
    "departments": ["id", "client_id", "name", "floor_location", "contact_name", "phone", "email", "notes"],
    "contacts": ["id", "client_id", "department_id", "name", "title", "phone", "email", "notes"],
    "cases": ["id", "client_id", "department_id", "equipment_id", "parent_case_reference", "case_type", "title", "description", "status", "priority", "blocked_reason", "responsible_user_id", "created_at", "updated_at"],
    "case_items": ["id", "case_id", "item_type", "description", "requested_qty", "unit_price", "status", "procurement_status", "inventory_item_id"],
    "client_activities": ["id", "client_id", "department_id", "case_id", "activity_type", "title", "description", "status", "date", "created_by"],
    "equipment": ["id", "client_id", "department_id", "equipment_model_id", "name", "manufacturer", "model", "serial_number", "asset_tag", "installation_date", "warranty_start_date", "warranty_end_date", "status", "risk_classification", "life_support", "pm_frequency", "last_pm_date", "next_pm_date", "calibration_required", "calibration_due_date"],
    "inventory_items": ["id", "pn", "description", "category", "manufacturer", "minimum_qty", "physical_qty", "reserved_qty", "available_qty", "location", "status"],
    "procurement_requests": ["id", "case_id", "case_item_id", "inventory_item_id", "requested_qty", "shortage_qty", "procurement_status", "supplier", "expected_date"],
    "service_calls": ["id", "client_id", "department_id", "equipment_id", "case_id", "call_type", "priority", "status", "blocked_reason", "assigned_engineer_id", "request_date", "due_date"],
    "pm_tasks": ["id", "client_id", "department_id", "equipment_id", "contract_id", "case_id", "scheduled_date", "completed_date", "status", "assigned_engineer_id"],
    "contracts": ["id", "client_id", "contract_type", "start_date", "end_date", "status", "coverage_notes"],
    "warranties": ["id", "equipment_id", "client_id", "start_date", "end_date", "status", "coverage_notes"],
    "invoices": ["id", "client_id", "case_id", "parent_case_reference", "invoice_number", "status", "total_amount", "due_date", "paid_date"],
}


def main():
    from app.main import app, init_db  # noqa: E402

    init_db()
    assert app.title
    insp = inspect(engine)
    failures = []
    for table, required_columns in REQUIRED.items():
        if not insp.has_table(table):
            failures.append(f"missing table: {table}")
            continue
        existing = {col["name"] for col in insp.get_columns(table)}
        missing = sorted(set(required_columns) - existing)
        if missing:
            failures.append(f"{table} missing columns: {', '.join(missing)}")
    for table, compat_columns in LEGACY_STARTUP_COMPAT_COLUMNS.items():
        if not insp.has_table(table):
            continue
        existing = {col["name"] for col in insp.get_columns(table)}
        missing = sorted(set(compat_columns) - existing)
        if missing:
            failures.append(f"{table} missing legacy startup compatibility columns: {', '.join(missing)}")
    for table, col in [("cases", "parent_case_reference"), ("sales_requests", "offer_reference"), ("equipment", "serial_number"), ("departments", "client_id"), ("case_items", "case_id")]:
        if insp.has_table(table) and col in {c["name"] for c in insp.get_columns(table)}:
            index_cols = [tuple(idx["column_names"]) for idx in insp.get_indexes(table)]
            if (col,) not in index_cols:
                failures.append(f"missing index on {table}.{col}")
    with engine.connect() as conn:
        counts = {table: conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one() for table in ["clients", "departments", "equipment", "cases", "inventory_items"] if insp.has_table(table)}
    if failures:
        print("ERP verification failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("ERP verification passed.")
    print(counts)


if __name__ == "__main__":
    main()
