from __future__ import annotations

from pathlib import Path
import sys

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import engine  # noqa: E402
from app.erp_models import Base  # noqa: E402

REQUIRED_INDEXES = {
    "clients": ["ix_clients_name"],
    "departments": ["ix_departments_client_id"],
    "contacts": ["ix_contacts_client_id", "ix_contacts_department_id"],
    "cases": ["ix_cases_client_id", "ix_cases_department_id", "ix_cases_parent_case_reference", "ix_cases_mdmanser_report_number"],
    "equipment": ["ix_equipment_client_id", "ix_equipment_department_id", "ix_equipment_serial_number", "ix_equipment_mdmanser_serial_number"],
    "contracts": ["ix_contracts_client_id", "ix_contracts_contract_reference"],
    "service_calls": ["ix_service_calls_client_id", "ix_service_calls_case_id", "ix_service_calls_mdmanser_report_number"],
    "pm_tasks": ["ix_pm_tasks_client_id", "ix_pm_tasks_contract_id", "ix_pm_tasks_equipment_id"],
    "mdmanser_service_records": [
        "ix_mdmanser_service_records_report_number",
        "ix_mdmanser_service_records_serial_number",
        "ix_mdmanser_service_records_institution",
        "ix_mdmanser_service_records_engineer_name",
        "ix_mdmanser_service_records_source_row_hash",
    ],
}

REQUIRED_COMPATIBILITY_COLUMNS = {
    "inventory_items": ["inventory_id", "device_family", "barcode", "default_location_id", "active", "created_at", "updated_at"],
    "case_items": ["request_item_id", "requested_item", "quantity", "reserved_qty", "shortage_qty", "parent_case_reference"],
    "procurement_requests": ["sales_request_item_id", "customer_request_item_id", "requested_item", "shortage_qty", "blocked_reason"],
    "departments": ["department_name", "main_contact_name", "created_at", "updated_at"],
    "contacts": ["role", "created_at", "updated_at"],
    "equipment": ["pm_asset_id", "parent_case_reference", "parent_case_id", "created_at", "updated_at"],
    "service_calls": ["engineer", "request_id", "call_no", "opened_at", "closed_at"],
    "pm_tasks": ["asset_id", "task_name", "assigned_to", "due_date"],
}


def main():
    failures = []
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            failures.append(f"missing table: {table.name}")
            continue
        existing = {column["name"] for column in insp.get_columns(table.name)}
        missing = sorted(column.name for column in table.columns if column.name not in existing)
        if missing:
            failures.append(f"{table.name} missing columns: {', '.join(missing)}")
    for table_name, required in REQUIRED_INDEXES.items():
        if not insp.has_table(table_name):
            continue
        existing = {index["name"] for index in insp.get_indexes(table_name)}
        missing = sorted(set(required) - existing)
        if missing:
            failures.append(f"{table_name} missing indexes: {', '.join(missing)}")
    for table_name, required in REQUIRED_COMPATIBILITY_COLUMNS.items():
        if not insp.has_table(table_name):
            failures.append(f"missing compatibility table: {table_name}")
            continue
        existing = {column["name"] for column in insp.get_columns(table_name)}
        missing = sorted(set(required) - existing)
        if missing:
            failures.append(f"{table_name} missing startup compatibility columns: {', '.join(missing)}")
    with engine.connect() as conn:
        counts = {}
        for table_name in ["clients", "engineers", "equipment", "contracts", "cases", "service_calls", "pm_tasks", "mdmanser_service_records"]:
            if insp.has_table(table_name):
                counts[table_name] = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        if insp.has_table("mdmanser_service_records"):
            duplicate_hashes = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT source_row_hash
                        FROM mdmanser_service_records
                        GROUP BY source_row_hash
                        HAVING COUNT(*) > 1
                    ) dupes
                    """
                )
            ).scalar_one()
            if duplicate_hashes:
                failures.append(f"duplicate mdmanser source hashes: {duplicate_hashes}")
    try:
        from app.main import app, init_db  # noqa: F401

        init_db()
    except Exception as exc:
        failures.append(f"FastAPI app import/init_db failed: {exc}")
    if failures:
        print("ERP foundation verification failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)
    print("ERP foundation verification passed.")
    print(counts)


if __name__ == "__main__":
    main()
