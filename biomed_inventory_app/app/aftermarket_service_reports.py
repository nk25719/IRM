from __future__ import annotations

import io
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

from app import legacy_main


routes = APIRouter(tags=["Aftermarket Service Reports"])
router = APIRouter(prefix="/api/aftermarket", tags=["Aftermarket Service Reports"])
alias_router = APIRouter(prefix="/api/after-sales", tags=["Aftermarket Service Reports Alias"])

ASSET_FIELDS = [
    "company", "supplier", "product_type", "model", "serial_number", "institution",
    "unit_status", "order_number", "installation_date", "warranty_end_date", "source_file",
]

REPORT_FIELDS = [
    "sr_number", "engineer_id", "customer_id", "equipment_asset_id", "institution", "city",
    "country", "supplier", "equipment_model", "equipment_serial_number", "call_date",
    "call_time", "visit_date", "visit_time", "completed_date", "completed_time",
    "description", "call_reason", "ct1", "ct2", "total_travel_hours", "total_labor_hours",
    "total_working_hours", "total_travel_km", "status", "match_status", "source_file",
]

PART_FIELDS = ["supplier", "part_number", "description", "quantity", "unit_price", "total_price"]

HEADER_ALIASES = {
    "sr_number": ["sr#", "sr number", "service report", "service report no", "service report number", "report no"],
    "institution": ["institution", "customer", "client", "hospital", "company"],
    "city": ["city"],
    "country": ["country"],
    "supplier": ["supplier", "vendor"],
    "equipment_model": ["equipment model", "model", "device model", "machine model"],
    "equipment_serial_number": ["equipment serial number", "serial number", "serial", "s/n", "sn"],
    "call_date": ["call date", "reported date", "request date"],
    "call_time": ["call time", "reported time", "request time"],
    "visit_date": ["visit date", "service date", "attendance date"],
    "visit_time": ["visit time", "service time", "attendance time"],
    "completed_date": ["completed date", "completion date", "closed date"],
    "completed_time": ["completed time", "completion time", "closed time"],
    "description": ["description", "problem description", "work description", "service description"],
    "call_reason": ["call reason", "reason", "fault", "issue"],
    "ct1": ["ct1", "ct 1"],
    "ct2": ["ct2", "ct 2"],
    "total_travel_hours": ["total travel hours", "travel hours"],
    "total_labor_hours": ["total labor hours", "labor hours", "labour hours"],
    "total_working_hours": ["total working hours", "working hours"],
    "total_travel_km": ["total travel km", "travel km", "kilometers", "kilometres"],
    "status": ["status", "state"],
}

PART_ALIASES = {
    "supplier": ["supplier", "vendor", "part supplier"],
    "part_number": ["part number", "part no", "p/n", "pn", "item code", "part_number"],
    "description": ["part description", "description", "item description"],
    "quantity": ["quantity", "qty", "qtty"],
    "unit_price": ["unit price", "u/price", "price", "unit_price"],
    "total_price": ["total price", "total", "amount", "line total", "total_price"],
}

ASSET_ALIASES = {
    "company": ["company"],
    "supplier": ["supplier"],
    "product_type": ["product type", "product_type", "type"],
    "model": ["model"],
    "serial_number": ["serial #", "serial number", "serial", "s/n", "sn"],
    "institution": ["institution", "customer", "client", "hospital"],
    "unit_status": ["unit status", "unit_status", "status"],
    "order_number": ["order #", "order no", "order number", "order_number"],
    "installation_date": ["installation date", "install date", "installed"],
    "warranty_end_date": ["warranty ends", "warranty end", "warranty_end_date", "warranty end date"],
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    return legacy_main.db()


def normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def to_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def to_number(value: Any) -> float:
    if value is None or pd.isna(value) or value == "":
        return 0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned or 0)
    except ValueError:
        return 0


def ensure_service_report_tables() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS equipment_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT,
                supplier TEXT,
                product_type TEXT,
                model TEXT,
                serial_number TEXT UNIQUE,
                institution TEXT,
                unit_status TEXT,
                order_number TEXT,
                installation_date TEXT,
                warranty_end_date TEXT,
                customer_id INTEGER,
                department_id INTEGER,
                source_file TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS service_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sr_number TEXT UNIQUE,
                engineer_id INTEGER,
                customer_id INTEGER,
                equipment_asset_id INTEGER,
                equipment_id INTEGER,
                institution TEXT,
                city TEXT,
                country TEXT,
                supplier TEXT,
                equipment_model TEXT,
                equipment_serial_number TEXT,
                call_date TEXT,
                call_time TEXT,
                visit_date TEXT,
                visit_time TEXT,
                completed_date TEXT,
                completed_time TEXT,
                description TEXT,
                call_reason TEXT,
                ct1 TEXT,
                ct2 TEXT,
                total_travel_hours REAL DEFAULT 0,
                total_labor_hours REAL DEFAULT 0,
                total_working_hours REAL DEFAULT 0,
                total_travel_km REAL DEFAULT 0,
                status TEXT,
                match_status TEXT,
                source_file TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        asset_columns = {r["name"] for r in conn.execute("PRAGMA table_info(equipment_assets)").fetchall()}
        for name, column_type in {
            "company": "TEXT",
            "supplier": "TEXT",
            "product_type": "TEXT",
            "model": "TEXT",
            "serial_number": "TEXT",
            "institution": "TEXT",
            "unit_status": "TEXT",
            "order_number": "TEXT",
            "installation_date": "TEXT",
            "warranty_end_date": "TEXT",
            "customer_id": "INTEGER",
            "department_id": "INTEGER",
            "source_file": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        }.items():
            if name not in asset_columns:
                conn.execute(f"ALTER TABLE equipment_assets ADD COLUMN {name} {column_type}")
        report_columns = {r["name"] for r in conn.execute("PRAGMA table_info(service_reports)").fetchall()}
        wanted_columns = {
            "sr_number": "TEXT",
            "engineer_id": "INTEGER",
            "customer_id": "INTEGER",
            "equipment_asset_id": "INTEGER",
            "equipment_id": "INTEGER",
            "institution": "TEXT",
            "city": "TEXT",
            "country": "TEXT",
            "supplier": "TEXT",
            "equipment_model": "TEXT",
            "equipment_serial_number": "TEXT",
            "call_date": "TEXT",
            "call_time": "TEXT",
            "visit_date": "TEXT",
            "visit_time": "TEXT",
            "completed_date": "TEXT",
            "completed_time": "TEXT",
            "description": "TEXT",
            "call_reason": "TEXT",
            "ct1": "TEXT",
            "ct2": "TEXT",
            "total_travel_hours": "REAL DEFAULT 0",
            "total_labor_hours": "REAL DEFAULT 0",
            "total_working_hours": "REAL DEFAULT 0",
            "total_travel_km": "REAL DEFAULT 0",
            "match_status": "TEXT",
            "source_file": "TEXT",
        }
        for name, column_type in wanted_columns.items():
            if name not in report_columns:
                conn.execute(f"ALTER TABLE service_reports ADD COLUMN {name} {column_type}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS service_report_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_report_id INTEGER,
                sr_number TEXT,
                supplier TEXT,
                part_number TEXT,
                description TEXT,
                quantity REAL DEFAULT 0,
                unit_price REAL DEFAULT 0,
                total_price REAL DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (service_report_id) REFERENCES service_reports(id)
            )
        """)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_equipment_assets_serial_number ON equipment_assets(serial_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_equipment_assets_model ON equipment_assets(model)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_equipment_assets_institution ON equipment_assets(institution)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_service_reports_sr_number ON service_reports(sr_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_service_reports_asset ON service_reports(equipment_asset_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_service_reports_serial ON service_reports(equipment_serial_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_service_report_parts_report ON service_report_parts(service_report_id)")
        conn.commit()


def read_workbook(content: bytes, filename: str) -> list[pd.DataFrame]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        book = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None).values()
        return [df.fillna("") for df in book]
    if suffix == ".csv":
        return [pd.read_csv(io.BytesIO(content), header=None).fillna("")]
    raise HTTPException(status_code=400, detail="Upload must be Excel or CSV")


def read_table_upload(content: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(io.BytesIO(content)).fillna("")
    if suffix == ".csv":
        return pd.read_csv(io.BytesIO(content)).fillna("")
    raise HTTPException(status_code=400, detail="Upload must be Excel or CSV")


def guess_columns(columns: list[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    normalized = {normalize(column): column for column in columns}
    mapping = {}
    for field, names in aliases.items():
        for name in [field, *names]:
            hit = normalized.get(normalize(name))
            if hit:
                mapping[field] = hit
                break
    return mapping


def parse_installed_base(content: bytes, filename: str) -> list[dict[str, Any]]:
    df = read_table_upload(content, filename)
    mapping = guess_columns([str(c) for c in df.columns], ASSET_ALIASES)
    if "serial_number" not in mapping:
        raise HTTPException(status_code=400, detail="Installed-base file must include Serial # / serial number")
    rows = []
    for _, raw in df.iterrows():
        asset = {field: to_text(raw[column]) for field, column in mapping.items() if column in df.columns}
        if not asset.get("serial_number"):
            continue
        asset["source_file"] = filename
        rows.append(asset)
    return rows


def find_header_value(frames: list[pd.DataFrame], field: str) -> str | None:
    aliases = {normalize(a) for a in HEADER_ALIASES.get(field, [field])}
    for df in frames:
        for r_idx in range(len(df.index)):
            row = list(df.iloc[r_idx])
            for c_idx, cell in enumerate(row):
                label = normalize(cell)
                if label in aliases:
                    for offset in range(1, 4):
                        if c_idx + offset < len(row) and to_text(row[c_idx + offset]):
                            return to_text(row[c_idx + offset])
                    if r_idx + 1 < len(df.index) and to_text(df.iat[r_idx + 1, c_idx]):
                        return to_text(df.iat[r_idx + 1, c_idx])
    return None


def detect_parts_table(frames: list[pd.DataFrame]) -> list[dict[str, Any]]:
    best_rows: list[dict[str, Any]] = []
    for df in frames:
        for r_idx in range(len(df.index)):
            row = [normalize(v) for v in list(df.iloc[r_idx])]
            mapping: dict[str, int] = {}
            for field, aliases in PART_ALIASES.items():
                alias_set = {normalize(a) for a in aliases}
                for c_idx, label in enumerate(row):
                    if label in alias_set and field not in mapping:
                        mapping[field] = c_idx
            if len(mapping) >= 3 and {"part_number", "description"}.intersection(mapping):
                parts = []
                for data_idx in range(r_idx + 1, len(df.index)):
                    data_row = list(df.iloc[data_idx])
                    if not any(to_text(v) for v in data_row):
                        if parts:
                            break
                        continue
                    part = {}
                    for field, c_idx in mapping.items():
                        value = data_row[c_idx] if c_idx < len(data_row) else ""
                        part[field] = to_number(value) if field in {"quantity", "unit_price", "total_price"} else to_text(value)
                    if part.get("part_number") or part.get("description"):
                        part.setdefault("quantity", 0)
                        part.setdefault("unit_price", 0)
                        part.setdefault("total_price", to_number(part.get("quantity")) * to_number(part.get("unit_price")))
                        parts.append(part)
                if len(parts) > len(best_rows):
                    best_rows = parts
    return best_rows


def parse_service_report(content: bytes, filename: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frames = read_workbook(content, filename)
    report = {field: find_header_value(frames, field) for field in REPORT_FIELDS if field != "source_file"}
    report["source_file"] = filename
    if not report.get("sr_number"):
        raise HTTPException(status_code=400, detail="Could not find SR# / service report number in uploaded file")
    for field in ["total_travel_hours", "total_labor_hours", "total_working_hours", "total_travel_km"]:
        report[field] = to_number(report.get(field))
    report["status"] = report.get("status") or "imported"
    parts = detect_parts_table(frames)
    return report, parts


def find_equipment_id(conn: sqlite3.Connection, serial_number: str | None) -> int | None:
    if not serial_number:
        return None
    row = conn.execute(
        "SELECT id FROM equipment WHERE lower(serial_number)=lower(?) ORDER BY id DESC LIMIT 1",
        (serial_number,),
    ).fetchone()
    return int(row["id"]) if row else None


def find_equipment_asset_id(conn: sqlite3.Connection, serial_number: str | None) -> int | None:
    if not serial_number:
        return None
    row = conn.execute(
        "SELECT id FROM equipment_assets WHERE lower(serial_number)=lower(?) ORDER BY id DESC LIMIT 1",
        (serial_number,),
    ).fetchone()
    return int(row["id"]) if row else None


def upsert_equipment_asset(conn: sqlite3.Connection, asset: dict[str, Any]) -> str:
    ts = now()
    existing = conn.execute("SELECT id FROM equipment_assets WHERE lower(serial_number)=lower(?)", (asset["serial_number"],)).fetchone()
    data = {field: asset.get(field) for field in ASSET_FIELDS}
    if existing:
        data["updated_at"] = ts
        assignments = [f"{field}=?" for field in [*ASSET_FIELDS, "updated_at"] if field != "serial_number"]
        values = [data.get(field) for field in [*ASSET_FIELDS, "updated_at"] if field != "serial_number"]
        conn.execute(f"UPDATE equipment_assets SET {', '.join(assignments)} WHERE id=?", (*values, existing["id"]))
        return "updated"
    data["created_at"] = ts
    data["updated_at"] = ts
    columns = [*ASSET_FIELDS, "created_at", "updated_at"]
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO equipment_assets ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(data.get(field) for field in columns),
    )
    return "created"


def upsert_service_report(report: dict[str, Any], parts: list[dict[str, Any]]) -> dict[str, Any]:
    ensure_service_report_tables()
    ts = now()
    with db() as conn:
        equipment_asset_id = find_equipment_asset_id(conn, report.get("equipment_serial_number"))
        equipment_id = find_equipment_id(conn, report.get("equipment_serial_number"))
        report["equipment_asset_id"] = equipment_asset_id
        report["equipment_id"] = equipment_id
        report["match_status"] = "matched" if equipment_asset_id else "unmatched"
        existing = conn.execute("SELECT * FROM service_reports WHERE sr_number=?", (report["sr_number"],)).fetchone()
        if existing:
            report["updated_at"] = ts
            assignments = [f"{field}=?" for field in [*REPORT_FIELDS, "equipment_id", "updated_at"] if field != "sr_number"]
            values = [report.get(field) for field in [*REPORT_FIELDS, "equipment_id", "updated_at"] if field != "sr_number"]
            conn.execute(f"UPDATE service_reports SET {', '.join(assignments)} WHERE sr_number=?", (*values, report["sr_number"]))
            service_report_id = int(existing["id"])
            action = "updated"
        else:
            report["created_at"] = ts
            report["updated_at"] = ts
            columns = [*REPORT_FIELDS, "equipment_id", "created_at", "updated_at"]
            placeholders = ", ".join("?" for _ in columns)
            cur = conn.execute(
                f"INSERT INTO service_reports ({', '.join(columns)}) VALUES ({placeholders})",
                tuple(report.get(field) for field in columns),
            )
            service_report_id = int(cur.lastrowid)
            action = "created"
        conn.execute("DELETE FROM service_report_parts WHERE service_report_id=? OR sr_number=?", (service_report_id, report["sr_number"]))
        for part in parts:
            conn.execute(
                """
                INSERT INTO service_report_parts
                (service_report_id, sr_number, supplier, part_number, description, quantity, unit_price, total_price, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_report_id,
                    report["sr_number"],
                    part.get("supplier") or report.get("supplier"),
                    part.get("part_number"),
                    part.get("description"),
                    to_number(part.get("quantity")),
                    to_number(part.get("unit_price")),
                    to_number(part.get("total_price")),
                    ts,
                ),
            )
        conn.commit()
        row = dict(conn.execute("SELECT * FROM service_reports WHERE id=?", (service_report_id,)).fetchone())
    return {"action": action, "service_report": row, "parts_count": len(parts), "equipment_asset_linked": bool(equipment_asset_id), "equipment_linked": bool(equipment_id)}


@routes.post("/equipment-assets/import")
async def import_equipment_assets(file: UploadFile = File(...)):
    ensure_service_report_tables()
    content = await file.read()
    assets = parse_installed_base(content, file.filename or "installed_base.xlsx")
    created = 0
    updated = 0
    with db() as conn:
        for asset in assets:
            action = upsert_equipment_asset(conn, asset)
            created += 1 if action == "created" else 0
            updated += 1 if action == "updated" else 0
        conn.commit()
    return {"created": created, "updated": updated, "total_rows": len(assets)}


@routes.post("/service-reports/import")
async def import_service_report(file: UploadFile = File(...)):
    content = await file.read()
    report, parts = parse_service_report(content, file.filename or "service_report.xlsx")
    return upsert_service_report(report, parts)


@routes.get("/service-reports")
def list_service_reports(status: str = "", serial_number: str = "", limit: int = 200):
    ensure_service_report_tables()
    where = []
    params: list[Any] = []
    if status:
        where.append("lower(status)=lower(?)")
        params.append(status)
    if serial_number:
        where.append("lower(equipment_serial_number)=lower(?)")
        params.append(serial_number)
    clause = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM service_reports {clause} ORDER BY COALESCE(visit_date, call_date, created_at) DESC LIMIT ?",
            (*params, min(limit, 1000)),
        ).fetchall()
    return [dict(r) for r in rows]


@routes.get("/equipment-assets")
def list_equipment_assets(
    serial_number: str = "",
    model: str = "",
    supplier: str = "",
    institution: str = "",
    warranty_status: str = "",
    unit_status: str = "",
    limit: int = 500,
):
    ensure_service_report_tables()
    where = []
    params: list[Any] = []
    filters = {
        "serial_number": serial_number,
        "model": model,
        "supplier": supplier,
        "institution": institution,
        "unit_status": unit_status,
    }
    for field, value in filters.items():
        if value:
            where.append(f"lower({field}) LIKE lower(?)")
            params.append(f"%{value}%")
    if warranty_status == "active":
        where.append("(warranty_end_date IS NOT NULL AND date(warranty_end_date) >= date('now'))")
    elif warranty_status == "expired":
        where.append("(warranty_end_date IS NOT NULL AND date(warranty_end_date) < date('now'))")
    elif warranty_status == "missing":
        where.append("(warranty_end_date IS NULL OR warranty_end_date='')")
    clause = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM equipment_assets {clause} ORDER BY institution, model, serial_number LIMIT ?",
            (*params, min(limit, 1000)),
        ).fetchall()
    return [dict(r) for r in rows]


@routes.get("/service-reports/{sr_number}")
def get_service_report(sr_number: str):
    ensure_service_report_tables()
    with db() as conn:
        report = conn.execute("SELECT * FROM service_reports WHERE sr_number=?", (sr_number,)).fetchone()
        if not report:
            raise HTTPException(status_code=404, detail="Service report not found")
        parts = conn.execute("SELECT * FROM service_report_parts WHERE service_report_id=? ORDER BY id", (report["id"],)).fetchall()
    return {**dict(report), "parts": [dict(p) for p in parts]}


@routes.get("/service-report-parts/usage")
def spare_parts_usage(limit: int = 500):
    ensure_service_report_tables()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT part_number, description, supplier, SUM(quantity) AS quantity_used,
                   SUM(total_price) AS total_value, COUNT(DISTINCT sr_number) AS service_reports
            FROM service_report_parts
            GROUP BY part_number, description, supplier
            ORDER BY quantity_used DESC, service_reports DESC
            LIMIT ?
            """,
            (min(limit, 1000),),
        ).fetchall()
    return [dict(r) for r in rows]


@routes.get("/equipment/service-history")
def equipment_service_history(
    serial_number: str = "",
    model: str = "",
    supplier: str = "",
    institution: str = "",
    warranty_status: str = "",
    unit_status: str = "",
):
    ensure_service_report_tables()
    where = []
    params: list[Any] = []
    for sql, value in [
        ("lower(COALESCE(sr.equipment_serial_number, ea.serial_number, '')) LIKE lower(?)", serial_number),
        ("lower(COALESCE(sr.equipment_model, ea.model, '')) LIKE lower(?)", model),
        ("lower(COALESCE(sr.supplier, ea.supplier, '')) LIKE lower(?)", supplier),
        ("lower(COALESCE(sr.institution, ea.institution, '')) LIKE lower(?)", institution),
        ("lower(COALESCE(ea.unit_status, '')) LIKE lower(?)", unit_status),
    ]:
        if value:
            where.append(sql)
            params.append(f"%{value}%")
    if warranty_status == "active":
        where.append("(ea.warranty_end_date IS NOT NULL AND date(ea.warranty_end_date) >= date('now'))")
    elif warranty_status == "expired":
        where.append("(ea.warranty_end_date IS NOT NULL AND date(ea.warranty_end_date) < date('now'))")
    elif warranty_status == "missing":
        where.append("(ea.warranty_end_date IS NULL OR ea.warranty_end_date='')")
    clause = "WHERE " + " AND ".join(where) if where else ""
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT sr.*, ea.company, ea.product_type, ea.unit_status, ea.order_number,
                   ea.installation_date, ea.warranty_end_date
            FROM service_reports sr
            LEFT JOIN equipment_assets ea ON ea.id=sr.equipment_asset_id
            {clause}
            ORDER BY COALESCE(sr.visit_date, sr.call_date, sr.created_at) DESC
            LIMIT 1000
            """,
            tuple(params),
        ).fetchall()
    return [dict(r) for r in rows]


@routes.get("/service-reports/analytics/summary")
def service_report_analytics():
    ensure_service_report_tables()
    with db() as conn:
        summary = dict(conn.execute(
            """
            SELECT COUNT(*) AS total_reports,
                   SUM(CASE WHEN lower(COALESCE(status,'')) IN ('completed','closed','done') THEN 1 ELSE 0 END) AS completed_reports,
                   SUM(CASE WHEN lower(COALESCE(status,'')) NOT IN ('completed','closed','done') THEN 1 ELSE 0 END) AS open_reports,
                   SUM(COALESCE(total_travel_hours,0)) AS travel_hours,
                   SUM(COALESCE(total_labor_hours,0)) AS labor_hours,
                   SUM(COALESCE(total_working_hours,0)) AS working_hours,
                   SUM(COALESCE(total_travel_km,0)) AS travel_km
            FROM service_reports
            """
        ).fetchone())
        by_engineer = [dict(r) for r in conn.execute(
            "SELECT engineer_id, COUNT(*) AS reports FROM service_reports GROUP BY engineer_id ORDER BY reports DESC"
        ).fetchall()]
    return {"summary": summary, "by_engineer": by_engineer}


router.include_router(routes)
alias_router.include_router(routes)
