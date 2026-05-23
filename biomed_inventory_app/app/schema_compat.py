"""Schema compatibility helpers for the legacy SQLite startup sync."""

from __future__ import annotations


LEGACY_STARTUP_COMPAT_COLUMNS: dict[str, dict[str, str]] = {
    "departments": {
        "name": "TEXT",
        "contact_name": "TEXT",
        "department_name": "TEXT",
        "main_contact_name": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "contacts": {
        "title": "TEXT",
        "role": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "equipment_models": {
        "equipment_family": "TEXT",
        "modality": "TEXT",
        "notes": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "inventory_items": {
        "inventory_id": "INTEGER",
        "device_family": "TEXT",
        "barcode": "TEXT",
        "default_location_id": "INTEGER",
        "active": "INTEGER DEFAULT 1",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "blocked_reason": "TEXT DEFAULT 'none'",
        "blocked_notes": "TEXT",
    },
    "equipment": {
        "pm_asset_id": "INTEGER",
        "name": "TEXT",
        "warranty_id": "INTEGER",
        "contract_id": "INTEGER",
        "parent_case_reference": "TEXT",
        "parent_case_id": "INTEGER",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "cases": {
        "case_no": "TEXT",
        "contact_id": "INTEGER",
        "request_id": "INTEGER",
        "quotation_id": "INTEGER",
        "client_order_id": "INTEGER",
        "purchase_order_id": "INTEGER",
        "delivery_note_id": "INTEGER",
        "invoice_id": "INTEGER",
        "engineer_id": "INTEGER",
        "contract_id": "INTEGER",
        "workflow_state": "TEXT DEFAULT 'lead'",
        "department": "TEXT",
        "request_source": "TEXT",
        "parent_case_id": "INTEGER",
        "external_reference": "TEXT",
        "blocked_notes": "TEXT",
        "client_informed": "INTEGER DEFAULT 0",
        "date_informed": "TEXT",
        "informed_by": "TEXT",
        "communication_method": "TEXT",
        "informed_notes": "TEXT",
        "informed_attachment": "TEXT",
        "responsible_person": "TEXT",
        "due_date": "TEXT",
        "notes": "TEXT",
    },
    "case_items": {
        "request_item_id": "INTEGER",
        "requested_item": "TEXT",
        "quantity": "INTEGER DEFAULT 1",
        "reserved_qty": "INTEGER DEFAULT 0",
        "shortage_qty": "INTEGER DEFAULT 0",
        "parent_case_reference": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "client_activities": {
        "parent_case_reference": "TEXT",
        "source_table": "TEXT",
        "source_id": "INTEGER",
        "reference": "TEXT",
        "responsible_person": "TEXT",
        "priority": "TEXT DEFAULT 'normal'",
        "due_date": "TEXT",
        "blocked_reason": "TEXT DEFAULT 'none'",
        "blocked_notes": "TEXT",
        "client_informed": "INTEGER DEFAULT 0",
        "activity_date": "TEXT",
        "department": "TEXT",
        "notes": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "procurement_requests": {
        "sales_request_item_id": "INTEGER",
        "customer_request_item_id": "INTEGER",
        "client_id": "INTEGER",
        "department_id": "INTEGER",
        "sales_request_id": "INTEGER",
        "purchase_order_id": "INTEGER",
        "category": "TEXT",
        "requested_item": "TEXT",
        "expected_delivery_date": "TEXT",
        "received_qty": "INTEGER DEFAULT 0",
        "pending_qty": "INTEGER DEFAULT 0",
        "responsible_person": "TEXT",
        "blocked_reason": "TEXT DEFAULT 'none'",
        "priority": "TEXT DEFAULT 'normal'",
        "due_date": "TEXT",
        "client_informed": "INTEGER DEFAULT 0",
        "notes": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
    "warranties": {
        "department_id": "INTEGER",
        "warranty_start": "TEXT",
        "warranty_end": "TEXT",
        "vendor": "TEXT",
        "notes": "TEXT",
        "parent_case_reference": "TEXT",
        "parent_case_id": "INTEGER",
        "created_at": "TEXT",
        "updated_at": "TEXT",
    },
}


def sqlite_table_columns(conn, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_sqlite_compat_columns(conn, tables: list[str] | None = None) -> None:
    selected = tables or list(LEGACY_STARTUP_COMPAT_COLUMNS)
    for table in selected:
        existing = sqlite_table_columns(conn, table)
        if not existing:
            continue
        for column, column_type in LEGACY_STARTUP_COMPAT_COLUMNS.get(table, {}).items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def insert_or_ignore_dynamic(conn, table: str, values: dict[str, object]) -> None:
    columns = [column for column in values if column in sqlite_table_columns(conn, table)]
    if not columns:
        return
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    conn.execute(
        f"INSERT OR IGNORE INTO {table} ({column_sql}) VALUES ({placeholders})",
        tuple(values[column] for column in columns),
    )
