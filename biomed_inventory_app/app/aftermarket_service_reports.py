from __future__ import annotations

import io
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

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


class DashboardMetric(BaseModel):
    key: str
    label: str
    count: int | float
    tone: str
    icon: str
    secondary: str = ""
    href: str = ""


class DashboardActivity(BaseModel):
    key: str
    label: str
    icon: str
    pending: int
    overdue: int = 0
    blocked: int = 0
    completed: int = 0
    href: str = ""


class DashboardStage(BaseModel):
    key: str
    label: str
    count: int
    largest: bool = False
    href: str = ""


class DashboardCountItem(BaseModel):
    key: str
    label: str
    count: int
    tone: str = "neutral"
    icon: str = ""
    href: str = ""


class DashboardEngineerWorkload(BaseModel):
    engineer_id: str
    name: str
    active: int
    overdue: int
    capacity: str
    load_percent: int


class DashboardUpcoming(BaseModel):
    title: str
    when: str
    type: str
    href: str = ""


class DashboardSummary(BaseModel):
    generated_at: str
    metrics: list[DashboardMetric]
    activities: list[DashboardActivity]
    pipeline: list[DashboardStage]
    aging: list[DashboardCountItem]
    blockers: list[DashboardCountItem]
    engineers: list[DashboardEngineerWorkload]
    upcoming: list[DashboardUpcoming]
    alerts: list[DashboardCountItem]


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


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def coalesce_columns(conn: sqlite3.Connection, table: str, candidates: list[str]) -> str:
    existing = table_columns(conn, table)
    columns = [column for column in candidates if column in existing]
    return f"COALESCE({', '.join(columns)}, '')" if columns else "''"


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    try:
        row = conn.execute(sql, params).fetchone()
        return int((row[0] if row else 0) or 0)
    except sqlite3.Error:
        return 0


def today_iso() -> str:
    return date.today().isoformat()


def in_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def is_open_status_sql(column: str = "status") -> str:
    return f"lower(COALESCE({column},'')) NOT IN ('completed','closed','done','cancelled','resolved')"


def status_count(conn: sqlite3.Connection, table: str, where: str = "1=1", params: tuple[Any, ...] = ()) -> int:
    if not table_exists(conn, table):
        return 0
    return scalar(conn, f"SELECT COUNT(*) FROM {table} WHERE {where}", params)


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


@routes.get("/dashboard/summary", response_model=DashboardSummary)
def aftermarket_dashboard_summary():
    ensure_service_report_tables()
    with db() as conn:
        open_reports = status_count(conn, "service_reports", is_open_status_sql())
        completed_today = status_count(conn, "service_reports", "lower(COALESCE(status,'')) IN ('completed','closed','done') AND COALESCE(completed_date, updated_at, '') >= ?", (today_iso(),))
        overdue_reports = status_count(conn, "service_reports", f"{is_open_status_sql()} AND COALESCE(visit_date, call_date, created_at, '') < ?", (today_iso(),))
        unmatched_reports = status_count(conn, "service_reports", "lower(COALESCE(match_status,''))='unmatched'")
        scheduled_events = status_count(conn, "engineer_schedule_events", "lower(COALESCE(status,'')) IN ('scheduled','confirmed','in_progress') AND COALESCE(start_datetime,'') >= ? AND COALESCE(start_datetime,'') < ?", (today_iso(), in_days(7)))
        unassigned_events = 0
        if table_exists(conn, "engineer_schedule_events") and table_exists(conn, "engineer_schedule_assignments"):
            unassigned_events = scalar(conn, """
                SELECT COUNT(*) FROM engineer_schedule_events e
                LEFT JOIN engineer_schedule_assignments a ON a.schedule_event_id=e.id
                WHERE a.id IS NULL AND lower(COALESCE(e.status,'')) NOT IN ('completed','cancelled')
            """)
        quotation_pending = status_count(conn, "quotations", "lower(COALESCE(status,'')) NOT IN ('approved','completed','cancelled','rejected')")
        quotation_approval = status_count(conn, "quotations", "lower(COALESCE(status,'')) IN ('submitted','pending_approval','under_review')")
        pm_pending = status_count(conn, "pm_tasks", "lower(COALESCE(status,'')) NOT IN ('completed','cancelled','closed')")
        pm_date = coalesce_columns(conn, "pm_tasks", ["scheduled_date", "due_date", "next_pm_date"])
        pm_due_today = status_count(conn, "pm_tasks", f"{pm_date} <= ? AND lower(COALESCE(status,'')) NOT IN ('completed','cancelled','closed')", (today_iso(),)) if pm_date != "''" else 0
        contract_end = coalesce_columns(conn, "customer_service_contracts", ["end_date", "contract_end_date", "expiry_date"])
        contracts_expiring = status_count(conn, "customer_service_contracts", f"{contract_end} >= ? AND {contract_end} <= ?", (today_iso(), in_days(45))) if contract_end != "''" else 0
        parts_pending = status_count(conn, "service_report_parts", "COALESCE(quantity,0) > 0")
        assets_due_soon = status_count(conn, "equipment_assets", "COALESCE(warranty_end_date,'') >= ? AND COALESCE(warranty_end_date,'') <= ?", (today_iso(), in_days(45)))
        installations = status_count(conn, "engineer_schedule_events", "event_type='installation' AND lower(COALESCE(status,'')) NOT IN ('completed','cancelled')")
        deliveries = status_count(conn, "engineer_schedule_events", "event_type='delivery' AND lower(COALESCE(status,'')) NOT IN ('completed','cancelled')")
        trainings = status_count(conn, "engineer_schedule_events", "event_type='training' AND lower(COALESCE(status,'')) NOT IN ('completed','cancelled')")
        fmi_cases = status_count(conn, "service_opportunities", "lower(COALESCE(opportunity_type,'')) LIKE '%manufacturer%' AND lower(COALESCE(status,'')) NOT IN ('completed','closed','cancelled')")

        critical = overdue_reports + pm_due_today + contracts_expiring
        pending_total = open_reports + quotation_pending + pm_pending + unassigned_events

        activities = [
            DashboardActivity(key="service-calls", label="Service Calls", icon="call", pending=open_reports, overdue=overdue_reports, blocked=unmatched_reports, completed=completed_today, href="/aftersales/service-calls"),
            DashboardActivity(key="quotations", label="Quotations", icon="quote", pending=quotation_pending, overdue=0, blocked=quotation_approval, href="/aftersales/quotations"),
            DashboardActivity(key="pm", label="Preventive Maintenance", icon="pm", pending=pm_pending, overdue=pm_due_today, href="/aftersales/preventive-maintenance"),
            DashboardActivity(key="installations", label="Installations", icon="install", pending=installations, href="/aftersales/installations"),
            DashboardActivity(key="deliveries", label="Deliveries", icon="delivery", pending=deliveries, href="/aftersales/deliveries"),
            DashboardActivity(key="trainings", label="Trainings", icon="training", pending=trainings, href="/aftersales/trainings"),
            DashboardActivity(key="contracts", label="Contracts", icon="contract", pending=contracts_expiring, overdue=0, blocked=assets_due_soon, href="/aftersales/contracts"),
            DashboardActivity(key="parts", label="Spare Parts Requests", icon="parts", pending=parts_pending, href="/aftersales/spare-parts"),
            DashboardActivity(key="fmi", label="FMI / Technical Cases", icon="fmi", pending=fmi_cases, href="/aftersales/technical-cases"),
        ]

        pipeline_counts = {
            "incoming": open_reports,
            "inspection": status_count(conn, "service_reports", f"{is_open_status_sql()} AND lower(COALESCE(call_reason,'')) NOT LIKE '%quote%'"),
            "quotation": quotation_pending,
            "approval": quotation_approval,
            "parts": parts_pending,
            "repair": scheduled_events,
            "completed": completed_today,
        }
        largest_stage = max(pipeline_counts.values() or [0])
        pipeline = [
            DashboardStage(key=key, label=label, count=pipeline_counts[key], largest=pipeline_counts[key] == largest_stage and largest_stage > 0, href=href)
            for key, label, href in [
                ("incoming", "Incoming", "/aftersales/service-calls"),
                ("inspection", "Inspection", "/aftersales/service-calls?status=open"),
                ("quotation", "Quotation", "/aftersales/quotations"),
                ("approval", "Approval", "/aftersales/quotations?status=approval"),
                ("parts", "Parts", "/aftersales/spare-parts"),
                ("repair", "Repair", "/aftersales/service-calls?view=assigned"),
                ("completed", "Completed", "/aftersales/service-calls?status=completed"),
            ]
        ]

        aging = []
        for key, label, start, end, tone in [
            ("0-2", "0-2 days", 0, 2, "healthy"),
            ("3-5", "3-5 days", 3, 5, "due"),
            ("6-10", "6-10 days", 6, 10, "warning"),
            ("10-plus", ">10 days", 11, 9999, "critical"),
        ]:
            modifier = f"-{end} days" if end < 9999 else "-10 days"
            if key == "10-plus":
                count = status_count(conn, "service_reports", f"{is_open_status_sql()} AND date(COALESCE(call_date, created_at)) < date('now','-10 days')")
            else:
                count = status_count(conn, "service_reports", f"{is_open_status_sql()} AND date(COALESCE(call_date, created_at)) BETWEEN date('now',?) AND date('now',?)", (modifier, f"-{start} days"))
            aging.append(DashboardCountItem(key=key, label=label, count=count, tone=tone, href=f"/aftersales/service-calls?age={key}"))

        blockers = [
            DashboardCountItem(key="customer", label="Waiting customer", count=status_count(conn, "service_reports", f"{is_open_status_sql()} AND lower(COALESCE(status,'')) LIKE '%customer%'"), tone="warning", icon="customer", href="/aftersales/service-calls?blocked=customer"),
            DashboardCountItem(key="engineer", label="Waiting engineer", count=unassigned_events, tone="warning", icon="engineer", href="/aftersales/preventive-maintenance#schedule-import"),
            DashboardCountItem(key="approval", label="Quote approval", count=quotation_approval, tone="blocked", icon="approval", href="/aftersales/quotations?status=approval"),
            DashboardCountItem(key="parts", label="Spare parts", count=parts_pending, tone="blocked", icon="parts", href="/aftersales/spare-parts"),
            DashboardCountItem(key="supplier", label="Supplier", count=status_count(conn, "service_reports", f"{is_open_status_sql()} AND lower(COALESCE(supplier,''))!=''"), tone="blocked", icon="supplier", href="/aftersales/service-calls?blocked=supplier"),
            DashboardCountItem(key="manufacturer", label="Manufacturer", count=fmi_cases, tone="blocked", icon="factory", href="/aftersales/technical-cases"),
            DashboardCountItem(key="scheduling", label="Scheduling", count=scheduled_events, tone="active", icon="calendar", href="/aftersales/preventive-maintenance"),
        ]
        blockers.sort(key=lambda item: item.count, reverse=True)

        engineer_rows = []
        if table_exists(conn, "service_reports"):
            engineer_rows = conn.execute("""
                SELECT COALESCE(engineer_id, 'Unassigned') AS engineer_id,
                       COUNT(*) AS active,
                       SUM(CASE WHEN COALESCE(visit_date, call_date, created_at, '') < date('now') THEN 1 ELSE 0 END) AS overdue
                FROM service_reports
                WHERE lower(COALESCE(status,'')) NOT IN ('completed','closed','done','cancelled','resolved')
                GROUP BY COALESCE(engineer_id, 'Unassigned')
                ORDER BY active DESC
                LIMIT 8
            """).fetchall()
        engineers = []
        for row in engineer_rows:
            active = int(row["active"] or 0)
            load_percent = min(100, active * 18)
            capacity = "available" if active <= 2 else "balanced" if active <= 4 else "busy" if active <= 6 else "overloaded"
            engineers.append(DashboardEngineerWorkload(engineer_id=str(row["engineer_id"]), name=str(row["engineer_id"]), active=active, overdue=int(row["overdue"] or 0), capacity=capacity, load_percent=load_percent))

        upcoming_rows = []
        if table_exists(conn, "engineer_schedule_events"):
            upcoming_rows = conn.execute("""
                SELECT title, event_type, start_datetime
                FROM engineer_schedule_events
                WHERE COALESCE(start_datetime,'') >= date('now') AND COALESCE(start_datetime,'') < date('now','+7 days')
                  AND lower(COALESCE(status,'')) NOT IN ('cancelled','completed')
                ORDER BY start_datetime
                LIMIT 6
            """).fetchall()
        upcoming = [DashboardUpcoming(title=row["title"], when=row["start_datetime"], type=row["event_type"], href="/aftersales/preventive-maintenance") for row in upcoming_rows]
        if contracts_expiring:
            upcoming.append(DashboardUpcoming(title="Contracts expiring soon", when="45 days", type="contract", href="/aftersales/contracts"))

    alerts = [
        DashboardCountItem(key="overdue-calls", label="Overdue calls", count=overdue_reports, tone="critical", icon="alert", href="/aftersales/service-calls?status=overdue"),
        DashboardCountItem(key="pm-today", label="PM due today", count=pm_due_today, tone="critical", icon="pm", href="/aftersales/preventive-maintenance"),
        DashboardCountItem(key="contracts", label="Contracts expiring", count=contracts_expiring, tone="warning", icon="contract", href="/aftersales/contracts"),
        DashboardCountItem(key="quotation-approval", label="Quotes awaiting approval", count=quotation_approval, tone="warning", icon="quote", href="/aftersales/quotations"),
        DashboardCountItem(key="parts-delayed", label="Parts delayed", count=parts_pending, tone="blocked", icon="parts", href="/aftersales/spare-parts"),
        DashboardCountItem(key="unassigned", label="Unassigned activities", count=unassigned_events, tone="warning", icon="engineer", href="/aftersales/preventive-maintenance"),
        DashboardCountItem(key="stale", label="No update >10 days", count=aging[-1].count if aging else 0, tone="critical", icon="clock", href="/aftersales/service-calls?age=10-plus"),
    ]
    alerts = [item for item in alerts if item.count > 0]
    alerts.sort(key=lambda item: (item.tone != "critical", -item.count))

    return DashboardSummary(
        generated_at=now(),
        metrics=[
            DashboardMetric(key="critical", label="Critical / Overdue", count=critical, tone="critical", icon="alert", secondary=f"{overdue_reports} calls", href="/aftersales/service-calls?status=overdue"),
            DashboardMetric(key="pending", label="Pending", count=pending_total, tone="warning", icon="inbox", secondary=f"{open_reports} calls", href="/aftersales/operations"),
            DashboardMetric(key="scheduled", label="Scheduled", count=scheduled_events, tone="active", icon="calendar", secondary="next 7 days", href="/aftersales/preventive-maintenance"),
            DashboardMetric(key="completed", label="Completed Today", count=completed_today, tone="healthy", icon="check", secondary="closed work", href="/aftersales/service-calls?status=completed"),
        ],
        activities=activities,
        pipeline=pipeline,
        aging=aging,
        blockers=blockers,
        engineers=engineers,
        upcoming=upcoming[:7],
        alerts=alerts[:7],
    )


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
