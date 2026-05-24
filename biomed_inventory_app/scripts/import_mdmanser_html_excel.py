from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import erp_models as m  # noqa: E402
from app.database import session_scope  # noqa: E402

SERVICE_COLUMNS = {"Report #", "Engineer", "Institution", "Serial #"}

COLUMN_MAP = {
    "Report #": "report_number",
    "Engineer": "engineer_name",
    "Supplier": "supplier",
    "Product type": "product_type",
    "Model": "model",
    "Serial #": "serial_number",
    "Institution": "institution",
    "Unit Status": "unit_status",
    "Departament": "department",
    "Address": "address",
    "City": "city",
    "Country": "country",
    "Phone work": "phone_work",
    "Phone mob.": "phone_mobile",
    "Phone": "phone",
    "Email": "email",
    "Sold by": "sold_by",
    "Order #": "order_number",
    "Shipping date": "shipping_date",
    "Install by": "install_by",
    "Installation date": "installation_date",
    "Warranty ends": "warranty_ends",
    "Call reassons": "call_reasons",
    "Call type 1": "call_type_1",
    "Call type 2": "call_type_2",
    "Visit date": "visit_date",
    "Completed date": "completed_date",
    "Call by": "call_by",
    "Received by": "received_by",
    "Call date": "call_date",
    "Call time": "call_time",
    "Visit time": "visit_time",
    "Completed time": "completed_time",
}

DATE_FIELDS = {"shipping_date", "installation_date", "warranty_ends", "visit_date", "completed_date", "call_date"}


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
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", text):
        parsed = pd.to_datetime(text, errors="coerce", format="%Y-%m-%d")
    elif re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", text):
        parsed = pd.to_datetime(text, errors="coerce", format="%d-%m-%Y")
    else:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            parsed = pd.to_datetime(text, errors="coerce", dayfirst=False)
    if pd.isna(parsed):
        return None
    return parsed.date()


def row_hash(values: dict) -> str:
    payload = "|".join(str(values.get(key) or "") for key in sorted(values))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_or_create(db, model, defaults=None, **lookup):
    row = db.query(model).filter_by(**lookup).first()
    if row:
        return row, False
    row = model(**lookup, **(defaults or {}))
    db.add(row)
    db.flush()
    return row, True


def find_service_tables(path: Path):
    tables = pd.read_html(path)
    service_tables = []
    for idx, table in enumerate(tables):
        table.columns = [str(col).strip() for col in table.columns]
        if SERVICE_COLUMNS <= set(table.columns):
            service_tables.append((idx, table))
    return tables, service_tables


def normalized_row(row, source_file: str, source_table_index: int) -> dict:
    values = {}
    for source, target in COLUMN_MAP.items():
        values[target] = parse_date(row.get(source)) if target in DATE_FIELDS else clean(row.get(source))
    values["source_file"] = source_file
    values["source_table_index"] = source_table_index
    values["source_row_hash"] = row_hash(values)
    return values


def import_file(path: Path):
    _, service_tables = find_service_tables(path)
    inserted_records = updated_records = clients = engineers = equipment = cases = service_calls = 0
    with session_scope() as db:
        for table_index, table in service_tables:
            for _, source_row in table.iterrows():
                values = normalized_row(source_row, path.name, table_index)
                if not values.get("source_row_hash"):
                    continue
                raw = db.query(m.MDManserServiceRecord).filter_by(source_row_hash=values["source_row_hash"]).first()
                if raw:
                    for key, value in values.items():
                        setattr(raw, key, value)
                    updated_records += 1
                else:
                    db.add(m.MDManserServiceRecord(**values))
                    db.flush()
                    inserted_records += 1

                institution = values.get("institution") or "Unknown Institution"
                client, created = get_or_create(db, m.Client, name=institution, defaults={"location": values.get("city"), "address": values.get("address"), "status": "active"})
                clients += int(created)
                department = None
                if values.get("department"):
                    department, _ = get_or_create(db, m.Department, client_id=client.id, name=values["department"], defaults={"phone": values.get("phone_work"), "email": values.get("email")})
                engineer = None
                if values.get("engineer_name"):
                    engineer, created = get_or_create(db, m.Engineer, engineer_name=values["engineer_name"], defaults={"active": True})
                    engineers += int(created)
                serial = values.get("serial_number") or f"REPORT-{values.get('report_number')}"
                eq, created = get_or_create(
                    db,
                    m.Equipment,
                    client_id=client.id,
                    serial_number=serial,
                    defaults={
                        "department_id": department.id if department else None,
                        "name": values.get("product_type") or values.get("model") or "Equipment",
                        "manufacturer": values.get("supplier"),
                        "model": values.get("model"),
                        "installation_date": values.get("installation_date"),
                        "warranty_end_date": values.get("warranty_ends"),
                        "status": values.get("unit_status") or "active",
                        "mdmanser_serial_number": values.get("serial_number"),
                        "mdmanser_report_reference": values.get("report_number"),
                        "mdmanser_source_row_hash": values["source_row_hash"],
                    },
                )
                equipment += int(created)
                report = values.get("report_number") or values["source_row_hash"][:12]
                case, created = get_or_create(
                    db,
                    m.Case,
                    parent_case_reference=f"MDM-{report}",
                    defaults={
                        "client_id": client.id,
                        "department_id": department.id if department else None,
                        "equipment_id": eq.id,
                        "mdmanser_report_number": values.get("report_number"),
                        "case_type": values.get("call_type_1") or "service",
                        "title": values.get("call_reasons") or f"MDManser report {report}",
                        "description": values.get("call_reasons"),
                        "status": "closed" if values.get("completed_date") else "open",
                    },
                )
                cases += int(created)
                call = db.query(m.ServiceCall).filter_by(source_row_hash=values["source_row_hash"]).first()
                if not call:
                    db.add(
                        m.ServiceCall(
                            client_id=client.id,
                            department_id=department.id if department else None,
                            equipment_id=eq.id,
                            case_id=case.id,
                            mdmanser_report_number=values.get("report_number"),
                            call_type=values.get("call_type_1") or "service",
                            call_type_2=values.get("call_type_2"),
                            status="completed" if values.get("completed_date") else "open",
                            assigned_engineer_id=engineer.id if engineer else None,
                            call_reason=values.get("call_reasons"),
                            call_by=values.get("call_by"),
                            received_by=values.get("received_by"),
                            request_date=values.get("call_date"),
                            request_time=values.get("call_time"),
                            visit_date=values.get("visit_date"),
                            visit_time=values.get("visit_time"),
                            completed_date=values.get("completed_date"),
                            completed_time=values.get("completed_time"),
                            source="mdmanser_html_excel",
                            source_row_hash=values["source_row_hash"],
                        )
                    )
                    db.flush()
                    service_calls += 1
    return {
        "service_tables": len(service_tables),
        "inserted_records": inserted_records,
        "updated_records": updated_records,
        "clients_created": clients,
        "engineers_created": engineers,
        "equipment_created": equipment,
        "cases_created": cases,
        "service_calls_created": service_calls,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/import_mdmanser_html_excel.py /path/to/MDmanser-05-24-2026.xls")
    summary = import_file(Path(sys.argv[1]))
    print("MDManser import summary:")
    for key, value in summary.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
