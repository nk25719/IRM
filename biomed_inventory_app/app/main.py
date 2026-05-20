from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from pathlib import Path
import sqlite3, os, shutil, urllib.parse, io, base64
import html as html_module
import secrets
import pandas as pd
from datetime import datetime, date, timedelta
import qrcode

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("DB_PATH", DATA_DIR / "inventory.db"))
EXCEL_PATH = Path(os.getenv("EXCEL_PATH", DATA_DIR / "inventory_master.xlsx"))
SEED_PATH = DATA_DIR / "inventory_seed.xlsx"
APP_USERNAME = os.getenv("APP_USERNAME", "admin")
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123")
SESSION_SECRET = os.getenv("SESSION_SECRET", "local-dev-session-secret-change-me")

app = FastAPI(title="Biomedical Inventory ERP", version="1.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

PUBLIC_PATHS = {"/login"}
PUBLIC_STATIC_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)
    if path.startswith("/static") and path.lower().endswith(PUBLIC_STATIC_SUFFIXES):
        return await call_next(request)

    if not request.session.get("authenticated"):
        if path.startswith("/api"):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)

    return await call_next(request)


app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=False)


class InventoryItem(BaseModel):
    pn: str
    description: str = ""
    location: str = ""
    system_qty: int = 0
    physical_qty: int = 0
    device_family: str = ""
    status: str = ""
    notes: str = ""
    barcode: str = ""
    photo_url: str = ""

class QuantityUpdate(BaseModel):
    physical_qty: int
    reason: str = "QUICK_EDIT"

class TransactionIn(BaseModel):
    barcode_or_pn: str
    qty: int
    direction: str
    purchase_order_no: str = ""
    client_order_no: str = ""
    client_name: str = ""
    notes: str = ""
    pm_asset_id: int | None = None

class ClientOrder(BaseModel):
    client_order_no: str
    client_name: str = ""
    status: str = "OPEN"
    expected_date: str = ""
    notes: str = ""

class PurchaseOrder(BaseModel):
    po_no: str
    supplier: str = ""
    status: str = "OPEN"
    expected_date: str = ""
    notes: str = ""

class PurchaseOrderLine(BaseModel):
    po_no: str
    pn: str
    description: str = ""
    qty: int
    location: str = ""
    barcode: str = ""
    device_family: str = ""
    notes: str = ""

class PMAsset(BaseModel):
    asset_tag: str
    serial_number: str = ""
    manufacturer: str = ""
    model: str = ""
    department: str = ""
    hospital: str = ""
    location: str = ""
    engineer: str = ""
    contact_email: str = ""
    contract_no: str = ""
    contract_start_date: str = ""
    contract_end_date: str = ""
    frequency_days: int = 180
    next_pm_date: str = ""
    last_pm_date: str = ""
    status: str = "Upcoming"
    notes: str = ""
    linked_inventory_pn: str = ""
    barcode: str = ""

class PMTask(BaseModel):
    asset_id: int
    task_name: str
    description: str = ""
    checklist: str = ""
    status: str = "Open"
    assigned_to: str = ""
    due_date: str = ""
    completed_date: str = ""
    notes: str = ""

class PMHistoryEntry(BaseModel):
    asset_id: int
    action: str
    notes: str = ""
    engineer: str = ""

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.now().isoformat(timespec="seconds")

def parse_iso_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

def add_days_iso(value: str, days: int) -> str:
    base = parse_iso_date(value) or date.today()
    return (base + timedelta(days=max(1, int(days or 1)))).isoformat()

def pm_timing_status(next_pm_date: str, status: str = "") -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"completed", "closed"}:
        return "completed"
    if normalized == "missed":
        return "missed"
    due = parse_iso_date(next_pm_date)
    if not due:
        return "unscheduled"
    today = date.today()
    if due < today:
        return "overdue"
    if due == today:
        return "due_today"
    if due <= today + timedelta(days=7):
        return "due_this_week"
    return "upcoming"

def compute_status(system_qty: int, physical_qty: int) -> str:
    if system_qty > 0 and physical_qty == 0:
        return "MISSING_FROM_SHELF"
    if physical_qty > 0 and system_qty == 0:
        return "FOUND_NOT_IN_ERP"
    if system_qty == physical_qty:
        return "MATCHED"
    return "MISMATCH"

def detect_family(description: str) -> str:
    families = ["Dash", "Dinamap", "B20", "B30", "B40", "B450", "B650",
                "Giraffe", "Panda", "V100", "PSMP", "Procare", "Omni-bed", "B105", "B125"]
    text = (description or "").lower()
    for fam in families:
        if fam.lower() in text:
            return fam
    return ""

def lookup_url_for(pn: str, description: str = "") -> str:
    query = f"{pn} {description} biomedical spare part GE Healthcare".strip()
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)

def audit(conn, item_id, action, old_value="", new_value="", notes=""):
    conn.execute("""
        INSERT INTO audit_log (item_id, action, old_value, new_value, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (item_id, action, str(old_value), str(new_value), notes, now()))

def init_db():
    conn = db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pn TEXT NOT NULL,
            description TEXT,
            location TEXT,
            system_qty INTEGER DEFAULT 0,
            physical_qty INTEGER DEFAULT 0,
            difference INTEGER DEFAULT 0,
            device_family TEXT,
            status TEXT,
            notes TEXT,
            source TEXT,
            updated_at TEXT,
            barcode TEXT,
            photo_url TEXT,
            lookup_url TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            action TEXT,
            old_value TEXT,
            new_value TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            pn TEXT,
            barcode TEXT,
            direction TEXT,
            qty INTEGER,
            old_qty INTEGER,
            new_qty INTEGER,
            purchase_order_no TEXT,
            client_order_no TEXT,
            client_name TEXT,
            pm_asset_id INTEGER,
            pm_asset_tag TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_order_no TEXT UNIQUE,
            client_name TEXT,
            status TEXT,
            expected_date TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_no TEXT UNIQUE,
            supplier TEXT,
            status TEXT,
            expected_date TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_no TEXT,
            pn TEXT,
            description TEXT,
            qty INTEGER,
            received_qty INTEGER DEFAULT 0,
            location TEXT,
            barcode TEXT,
            device_family TEXT,
            notes TEXT,
            received INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pm_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_tag TEXT UNIQUE,
            serial_number TEXT,
            manufacturer TEXT,
            model TEXT,
            department TEXT,
            hospital TEXT,
            location TEXT,
            engineer TEXT,
            contact_email TEXT,
            contract_no TEXT,
            contract_start_date TEXT,
            contract_end_date TEXT,
            frequency_days INTEGER DEFAULT 180,
            next_pm_date TEXT,
            last_pm_date TEXT,
            status TEXT,
            notes TEXT,
            linked_inventory_pn TEXT,
            barcode TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pm_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER,
            task_name TEXT,
            description TEXT,
            checklist TEXT,
            status TEXT,
            assigned_to TEXT,
            due_date TEXT,
            completed_date TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pm_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER,
            action TEXT,
            notes TEXT,
            engineer TEXT,
            created_at TEXT
        )
    """)
    conn.commit()

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(inventory)").fetchall()]
    for col in ["barcode", "photo_url", "lookup_url"]:
        if col not in cols:
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {col} TEXT")

    tx_cols = [r["name"] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    for col in ["client_order_no", "client_name", "pm_asset_id", "pm_asset_tag"]:
        if col not in tx_cols:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} TEXT")

    pm_asset_cols = [r["name"] for r in conn.execute("PRAGMA table_info(pm_assets)").fetchall()]
    for col in ["engineer", "contact_email", "contract_no", "contract_start_date", "contract_end_date"]:
        if col not in pm_asset_cols:
            conn.execute(f"ALTER TABLE pm_assets ADD COLUMN {col} TEXT")

    conn.commit()

    count = conn.execute("SELECT COUNT(*) AS c FROM inventory").fetchone()["c"]
    conn.close()

    if count == 0:
        if EXCEL_PATH.exists():
            import_excel(EXCEL_PATH)
        elif SEED_PATH.exists():
            import_excel(SEED_PATH)
            export_excel(EXCEL_PATH)

def find_col(df, possible):
    for c in possible:
        if c in df.columns:
            return c
    lower = {str(c).lower(): c for c in df.columns}
    for c in possible:
        if c.lower() in lower:
            return lower[c.lower()]
    return None

def import_excel(path: Path, mode: str = "append_merge"):
    if mode not in {"append_merge", "replace_all"}:
        raise ValueError("Import mode must be append_merge or replace_all.")

    xls = pd.ExcelFile(path)
    sheet = next((s for s in ["DEDUPLICATED_STOCK", "ONE_MASTER_SHEET", "MASTER_SUMMARY", "MASTER_STOCK", "ERP_RECONCILIATION"] if s in xls.sheet_names), xls.sheet_names[0])
    print(f"Importing Excel: {path.name} | Sheet: {sheet}")
    # Read without assuming that row 1 contains headers.
    # Some printable / deduplicated sheets have title rows before the actual header row.
    raw_df = pd.read_excel(path, sheet_name=sheet, header=None)

    header_row = None
    for idx in range(min(15, len(raw_df))):
        row_values = [str(v).strip().lower() for v in raw_df.iloc[idx].tolist()]
        if any(v in ["pn", "item / pn", "part number", "part no", "item"] for v in row_values):
            header_row = idx
            break

    if header_row is None:
        raise ValueError(
            f"No PN / part-number header found in Excel sheet '{sheet}'. "
            f"Please make sure one column is named PN, Item / PN, Part Number, or Item."
        )

    df = pd.read_excel(path, sheet_name=sheet, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]

    # Remove completely empty rows and accidental repeated header rows.
    df = df.dropna(how="all")

    pn_col = find_col(df, ["PN", "pn", "Item / PN", "Part Number", "Part No", "Item"])
    if not pn_col:
        raise ValueError("No PN / part-number column found after header detection.")

    desc_col = find_col(df, ["Description", "description", "Desc"])
    expected_col = find_col(df, ["Expected Qty", "Expected Quantity", "System Qty Num", "System Qty", "system_qty", "Qty"])
    physical_col = find_col(df, ["Counted Qty", "Physical Qty Num", "Physical Qty", "physical_qty", "Verified Physical Qty"])
    loc_col = find_col(df, ["All Locations", "All Locations for PN", "Location", "location", "Loc"])
    fam_col = find_col(df, ["Device Family", "device_family"])
    notes_col = find_col(df, ["Notes", "notes"])
    barcode_col = find_col(df, ["Barcode", "barcode"])
    photo_col = find_col(df, ["Photo URL", "photo_url"])

    def txt(row, col):
        if col is None:
            return ""
        val = row.get(col)
        if pd.isna(val):
            return ""
        return str(val).strip()

    def num(row, col):
        if col is None:
            return 0
        try:
            val = row.get(col)
            if pd.isna(val) or str(val).strip() == "":
                return 0
            return int(float(val))
        except Exception:
            return 0

    def clean_value(value):
        return "" if value is None else str(value).strip()

    def row_dict(row):
        return {k: row[k] for k in row.keys()}

    def same_value(left, right):
        return clean_value(left) == clean_value(right)

    conn = db()
    if mode == "replace_all":
        conn.execute("DELETE FROM inventory")

    counts = {"inserted": 0, "updated": 0, "skipped": 0}

    for _, r in df.iterrows():
        pn = txt(r, pn_col)
        if not pn or pn.lower() == "nan":
            continue

        desc = txt(r, desc_col)
        loc = txt(r, loc_col)
        system_qty = num(r, expected_col)
        physical_qty = num(r, physical_col)
        if physical_col is None or physical_qty == 0:
            # For your deduplicated count sheet, expected qty is the baseline qty to follow.
            physical_qty = system_qty

        family = txt(r, fam_col) or detect_family(desc)
        barcode = txt(r, barcode_col)
        photo_url = txt(r, photo_col)
        notes = txt(r, notes_col)
        difference = physical_qty - system_qty
        status = compute_status(system_qty, physical_qty)
        lookup_url = lookup_url_for(pn, desc)
        imported = {
            "pn": pn,
            "description": desc,
            "location": loc,
            "system_qty": system_qty,
            "physical_qty": physical_qty,
            "difference": difference,
            "device_family": family,
            "status": status,
            "notes": notes,
            "source": "EXCEL_IMPORT",
            "barcode": barcode,
            "photo_url": photo_url,
            "lookup_url": lookup_url,
        }

        existing = conn.execute("""
            SELECT * FROM inventory
            WHERE lower(trim(pn)) = lower(trim(?))
              AND lower(trim(COALESCE(location, ''))) = lower(trim(?))
            ORDER BY id
            LIMIT 1
        """, (pn, loc)).fetchone()

        if existing:
            old = row_dict(existing)
            merged = dict(imported)

            for field in ["description", "device_family"]:
                if not merged[field]:
                    merged[field] = clean_value(existing[field])
            for field in ["barcode", "photo_url", "notes"]:
                if not merged[field]:
                    merged[field] = clean_value(existing[field])

            merged["lookup_url"] = lookup_url_for(merged["pn"], merged["description"])
            merged["difference"] = int(merged["physical_qty"] or 0) - int(merged["system_qty"] or 0)
            merged["status"] = compute_status(int(merged["system_qty"] or 0), int(merged["physical_qty"] or 0))

            tracked_fields = [
                "pn", "description", "location", "system_qty", "physical_qty", "difference",
                "device_family", "status", "notes", "barcode", "photo_url", "lookup_url"
            ]
            changes = {
                field: {"old": old[field], "new": merged[field]}
                for field in tracked_fields
                if not same_value(old[field], merged[field])
            }

            if changes:
                conn.execute("""
                    UPDATE inventory
                    SET pn=?, description=?, location=?, system_qty=?, physical_qty=?, difference=?,
                        device_family=?, status=?, notes=?, source=?, updated_at=?, barcode=?, photo_url=?, lookup_url=?
                    WHERE id=?
                """, (
                    merged["pn"], merged["description"], merged["location"], merged["system_qty"],
                    merged["physical_qty"], merged["difference"], merged["device_family"],
                    merged["status"], merged["notes"], merged["source"], now(), merged["barcode"],
                    merged["photo_url"], merged["lookup_url"], existing["id"]
                ))
                audit(conn, existing["id"], "IMPORT_UPDATE", old, changes, f"Imported from {path.name}")
                counts["updated"] += 1
            else:
                audit(conn, existing["id"], "IMPORT_SKIPPED", "", f"PN={pn}; location={loc}", f"No meaningful change from {path.name}")
                counts["skipped"] += 1
            continue

        cur = conn.execute("""
            INSERT INTO inventory
            (pn, description, location, system_qty, physical_qty, difference, device_family, status, notes, source, updated_at, barcode, photo_url, lookup_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (pn, desc, loc, system_qty, physical_qty, difference, family, status, notes, "EXCEL_IMPORT",
              now(), barcode, photo_url, lookup_url))
        audit(conn, cur.lastrowid, "IMPORT_INSERT", "", imported, f"Imported from {path.name}")
        counts["inserted"] += 1

    conn.commit()
    conn.close()
    return counts

def export_excel(path: Path):
    conn = db()
    df = pd.read_sql_query("SELECT * FROM inventory ORDER BY location, pn", conn)
    tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY created_at DESC", conn)
    audit_df = pd.read_sql_query("SELECT * FROM audit_log ORDER BY created_at DESC", conn)
    po_df = pd.read_sql_query("SELECT * FROM purchase_orders ORDER BY updated_at DESC", conn)
    po_items_df = pd.read_sql_query("SELECT * FROM purchase_order_items ORDER BY updated_at DESC", conn)
    client_orders_df = pd.read_sql_query("SELECT * FROM client_orders ORDER BY updated_at DESC", conn)
    pm_assets_df = pd.read_sql_query("SELECT * FROM pm_assets ORDER BY hospital, next_pm_date", conn)
    pm_tasks_df = pd.read_sql_query("SELECT * FROM pm_tasks ORDER BY due_date", conn)
    pm_history_df = pd.read_sql_query("SELECT * FROM pm_history ORDER BY created_at DESC", conn)
    conn.close()

    if df.empty:
        df = pd.DataFrame(columns=["id", "pn", "description", "location", "system_qty", "physical_qty", "difference",
                                   "device_family", "status", "notes", "barcode", "photo_url", "lookup_url", "updated_at"])

    df["difference"] = df["physical_qty"] - df["system_qty"]
    df["status"] = df.apply(lambda r: compute_status(int(r["system_qty"]), int(r["physical_qty"])), axis=1)
    df["lookup_url"] = df.apply(lambda r: lookup_url_for(str(r["pn"]), str(r["description"])), axis=1)

    summary = df.groupby("pn").agg(
        description=("description", "first"),
        expected_qty=("system_qty", "sum"),
        physical_qty=("physical_qty", "sum"),
        locations=("location", lambda x: ", ".join(sorted(set([str(i) for i in x if str(i) != "nan" and str(i).strip()])))),
        device_family=("device_family", "first"),
        barcode=("barcode", "first"),
        photo_url=("photo_url", "first"),
        lookup_url=("lookup_url", "first")
    ).reset_index()
    summary["difference"] = summary["physical_qty"] - summary["expected_qty"]

    missing = summary[(summary.expected_qty > 0) & (summary.physical_qty == 0)].copy()
    found = summary[(summary.physical_qty > 0) & (summary.expected_qty == 0)].copy()
    stale = summary[(summary.physical_qty > 3) & (summary.expected_qty == 0)].copy()

    loc_count = summary.copy()
    loc_count["location_count"] = loc_count["locations"].apply(lambda x: len([p for p in str(x).split(",") if p.strip()]))
    multi = loc_count[loc_count.location_count > 1].copy()
    multi["duplicate_locations"] = multi["locations"]
    multi["duplicate_note"] = multi["location_count"].apply(lambda c: f"Present in {c} locations")

    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="ONE_MASTER_SHEET", index=False)
        summary.to_excel(writer, sheet_name="MASTER_SUMMARY", index=False)
        missing.to_excel(writer, sheet_name="MISSING_FROM_SHELF", index=False)
        found.to_excel(writer, sheet_name="FOUND_NOT_IN_ERP", index=False)
        stale.to_excel(writer, sheet_name="DEAD_STALE_INVENTORY", index=False)
        multi.to_excel(writer, sheet_name="PRESENT_IN_TWO_PLACES", index=False)
        tx.to_excel(writer, sheet_name="TRANSACTIONS", index=False)
        po_df.to_excel(writer, sheet_name="PURCHASE_ORDERS", index=False)
        po_items_df.to_excel(writer, sheet_name="PURCHASE_ORDER_ITEMS", index=False)
        client_orders_df.to_excel(writer, sheet_name="CLIENT_ORDERS", index=False)
        pm_assets_df.to_excel(writer, sheet_name="PM_ASSETS", index=False)
        pm_tasks_df.to_excel(writer, sheet_name="PM_TASKS", index=False)
        pm_history_df.to_excel(writer, sheet_name="PM_HISTORY", index=False)
        audit_df.to_excel(writer, sheet_name="AUDIT_TRAIL", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(length + 4, 55)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
def index(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/portal", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login")
def login_page(request: Request, error: str = ""):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/portal", status_code=303)
    html = (BASE_DIR / "static" / "login.html").read_text(encoding="utf-8")
    safe_error = html_module.escape(error.strip())
    error_markup = f'<div class="alert" role="alert">{safe_error}</div>' if safe_error else ""
    return HTMLResponse(html.replace("{{ERROR}}", error_markup))

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    username_ok = secrets.compare_digest(username, APP_USERNAME)
    password_ok = secrets.compare_digest(password, APP_PASSWORD)
    if username_ok and password_ok:
        request.session["authenticated"] = True
        request.session["username"] = username
        return RedirectResponse(url="/portal", status_code=303)
    return RedirectResponse(url="/login?error=Invalid%20credentials", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/portal")
def portal():
    return FileResponse(BASE_DIR / "static" / "portal.html")

@app.get("/inventory")
def inventory_page():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/pm")
@app.get("/pm/dashboard")
@app.get("/pm/due")
@app.get("/pm/schedule")
@app.get("/pm/calendar")
@app.get("/pm/completed")
@app.get("/pm/equipment")
@app.get("/pm/assets")
@app.get("/pm/engineers")
@app.get("/pm/reports")
@app.get("/pm/history")
def pm_page():
    return FileResponse(BASE_DIR / "static" / "pm.html")


def enrich_pm_asset(asset):
    asset = dict(asset)
    due = parse_iso_date(asset.get("next_pm_date"))
    asset["timing_status"] = pm_timing_status(asset.get("next_pm_date"), asset.get("status"))
    asset["days_until_pm"] = (due - date.today()).days if due else None
    contract_end = parse_iso_date(asset.get("contract_end_date"))
    asset["contract_days_left"] = (contract_end - date.today()).days if contract_end else None
    if contract_end and contract_end < date.today():
        asset["contract_status"] = "expired"
    elif contract_end and contract_end <= date.today() + timedelta(days=30):
        asset["contract_status"] = "expiring_soon"
    else:
        asset["contract_status"] = "active" if contract_end else ""
    return asset

def pm_dashboard_counts(conn):
    assets = [enrich_pm_asset(r) for r in conn.execute("SELECT * FROM pm_assets").fetchall()]
    today = date.today()
    month_start = today.replace(day=1)
    next_month = today.replace(year=today.year + 1, month=1, day=1) if today.month == 12 else today.replace(month=today.month + 1, day=1)
    completed_this_month = conn.execute("""
        SELECT COUNT(*) AS c FROM pm_tasks
        WHERE lower(status)='completed' AND completed_date >= ? AND completed_date < ?
    """, (month_start.isoformat(), next_month.isoformat())).fetchone()["c"]
    return {
        "total_pm_assets": len(assets),
        "pm_due_today": sum(1 for a in assets if a["timing_status"] == "due_today"),
        "pm_due_this_week": sum(1 for a in assets if a["timing_status"] in {"due_today", "due_this_week"}),
        "overdue_pm": sum(1 for a in assets if a["timing_status"] == "overdue"),
        "completed_this_month": int(completed_this_month or 0),
    }

@app.get("/api/pm-assets")
def list_pm_assets(q: str = "", status: str = "", hospital: str = "", timing: str = ""):
    conn = db()
    where, args = [], []
    if q:
        where.append("(asset_tag LIKE ? OR serial_number LIKE ? OR manufacturer LIKE ? OR model LIKE ? OR department LIKE ? OR hospital LIKE ? OR location LIKE ? OR linked_inventory_pn LIKE ? OR barcode LIKE ? OR engineer LIKE ? OR contract_no LIKE ?)")
        args.extend([f"%{q}%"] * 11)
    if status:
        where.append("status=?")
        args.append(status)
    if hospital:
        where.append("hospital LIKE ?")
        args.append(f"%{hospital}%")
    sql = "SELECT * FROM pm_assets"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(next_pm_date, ''), hospital, asset_tag"
    rows = [enrich_pm_asset(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    if timing:
        rows = [r for r in rows if r["timing_status"] == timing]
    return rows

@app.post("/api/pm-assets")
def create_pm_asset(asset: PMAsset):
    conn = db()
    try:
        cur = conn.execute("""
            INSERT INTO pm_assets
            (asset_tag, serial_number, manufacturer, model, department, hospital, location,
             engineer, contact_email, contract_no, contract_start_date, contract_end_date, frequency_days,
             next_pm_date, last_pm_date, status, notes, linked_inventory_pn, barcode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (asset.asset_tag.strip(), asset.serial_number, asset.manufacturer, asset.model, asset.department,
              asset.hospital, asset.location, asset.engineer, asset.contact_email, asset.contract_no,
              asset.contract_start_date, asset.contract_end_date, asset.frequency_days, asset.next_pm_date,
              asset.last_pm_date, asset.status, asset.notes, asset.linked_inventory_pn, asset.barcode, now(), now()))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Asset tag already exists")
    conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                 (cur.lastrowid, "ASSET_CREATED", "PM asset created", "", now()))
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "message": "PM asset created"}

@app.put("/api/pm-assets/{asset_id}")
def update_pm_asset(asset_id: int, asset: PMAsset):
    conn = db()
    existing = conn.execute("SELECT * FROM pm_assets WHERE id=?", (asset_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="PM asset not found")
    conn.execute("""
        UPDATE pm_assets
        SET asset_tag=?, serial_number=?, manufacturer=?, model=?, department=?, hospital=?, location=?,
            engineer=?, contact_email=?, contract_no=?, contract_start_date=?, contract_end_date=?,
            frequency_days=?, next_pm_date=?, last_pm_date=?, status=?, notes=?, linked_inventory_pn=?,
            barcode=?, updated_at=?
        WHERE id=?
    """, (asset.asset_tag.strip(), asset.serial_number, asset.manufacturer, asset.model, asset.department,
          asset.hospital, asset.location, asset.engineer, asset.contact_email, asset.contract_no,
          asset.contract_start_date, asset.contract_end_date, asset.frequency_days, asset.next_pm_date,
          asset.last_pm_date, asset.status, asset.notes, asset.linked_inventory_pn, asset.barcode, now(), asset_id))
    conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                 (asset_id, "ASSET_UPDATED", "PM asset details updated", "", now()))
    conn.commit()
    conn.close()
    return {"message": "PM asset updated"}

@app.delete("/api/pm-assets/{asset_id}")
def delete_pm_asset(asset_id: int):
    conn = db()
    existing = conn.execute("SELECT * FROM pm_assets WHERE id=?", (asset_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="PM asset not found")
    conn.execute("DELETE FROM pm_tasks WHERE asset_id=?", (asset_id,))
    conn.execute("DELETE FROM pm_history WHERE asset_id=?", (asset_id,))
    conn.execute("DELETE FROM pm_assets WHERE id=?", (asset_id,))
    conn.commit()
    conn.close()
    return {"message": "PM asset deleted"}

@app.get("/api/pm-tasks")
def list_pm_tasks(asset_id: int | None = None, status: str = ""):
    conn = db()
    where, args = [], []
    if asset_id:
        where.append("t.asset_id=?")
        args.append(asset_id)
    if status:
        where.append("t.status=?")
        args.append(status)
    sql = "SELECT t.*, a.asset_tag, a.hospital, a.department, a.model FROM pm_tasks t LEFT JOIN pm_assets a ON a.id=t.asset_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(t.due_date, ''), t.status, t.id DESC"
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows

@app.post("/api/pm-tasks")
def create_pm_task(task: PMTask):
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (task.asset_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="PM asset not found")
    cur = conn.execute("""
        INSERT INTO pm_tasks
        (asset_id, task_name, description, checklist, status, assigned_to, due_date, completed_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (task.asset_id, task.task_name, task.description, task.checklist, task.status, task.assigned_to,
          task.due_date, task.completed_date, task.notes, now(), now()))
    conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                 (task.asset_id, "TASK_CREATED", task.task_name, task.assigned_to, now()))
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "message": "PM task created"}

@app.put("/api/pm-tasks/{task_id}")
def update_pm_task(task_id: int, task: PMTask):
    conn = db()
    existing = conn.execute("SELECT * FROM pm_tasks WHERE id=?", (task_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="PM task not found")
    conn.execute("""
        UPDATE pm_tasks
        SET asset_id=?, task_name=?, description=?, checklist=?, status=?, assigned_to=?, due_date=?,
            completed_date=?, notes=?, updated_at=?
        WHERE id=?
    """, (task.asset_id, task.task_name, task.description, task.checklist, task.status, task.assigned_to,
          task.due_date, task.completed_date, task.notes, now(), task_id))
    if task.status.lower() == "completed":
        asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (task.asset_id,)).fetchone()
        completed = task.completed_date or date.today().isoformat()
        next_pm = add_days_iso(completed, int(asset["frequency_days"] or 180)) if asset else ""
        conn.execute("UPDATE pm_assets SET last_pm_date=?, next_pm_date=?, status=?, updated_at=? WHERE id=?",
                     (completed, next_pm, "Completed", now(), task.asset_id))
        conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                     (task.asset_id, "PM_COMPLETED", task.notes or task.task_name, task.assigned_to, now()))
    conn.commit()
    conn.close()
    return {"message": "PM task updated"}

@app.get("/api/pm-history")
def list_pm_history(asset_id: int | None = None, limit: int = 300):
    conn = db()
    if asset_id:
        rows = [dict(r) for r in conn.execute("""
            SELECT h.*, a.asset_tag, a.hospital, a.model FROM pm_history h
            LEFT JOIN pm_assets a ON a.id=h.asset_id
            WHERE h.asset_id=? ORDER BY h.created_at DESC LIMIT ?
        """, (asset_id, limit)).fetchall()]
    else:
        rows = [dict(r) for r in conn.execute("""
            SELECT h.*, a.asset_tag, a.hospital, a.model FROM pm_history h
            LEFT JOIN pm_assets a ON a.id=h.asset_id
            ORDER BY h.created_at DESC LIMIT ?
        """, (limit,)).fetchall()]
    conn.close()
    return rows

@app.post("/api/pm-history")
def create_pm_history(entry: PMHistoryEntry):
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (entry.asset_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="PM asset not found")
    cur = conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                       (entry.asset_id, entry.action, entry.notes, entry.engineer, now()))
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "message": "PM history added"}

@app.get("/api/pm-dashboard")
def pm_dashboard():
    conn = db()
    counts = pm_dashboard_counts(conn)
    upcoming = [enrich_pm_asset(r) for r in conn.execute("SELECT * FROM pm_assets ORDER BY COALESCE(next_pm_date, ''), hospital, asset_tag LIMIT 12").fetchall()]
    hospitals = [dict(r) for r in conn.execute("SELECT hospital, COUNT(*) AS assets FROM pm_assets GROUP BY hospital ORDER BY assets DESC, hospital").fetchall()]
    contracts = [dict(r) for r in conn.execute("""
        SELECT hospital, contract_no, MIN(contract_start_date) AS contract_start_date,
               MAX(contract_end_date) AS contract_end_date, COUNT(*) AS asset_count
        FROM pm_assets
        WHERE COALESCE(contract_no, '') != ''
        GROUP BY hospital, contract_no
        ORDER BY contract_end_date, hospital, contract_no
        LIMIT 12
    """).fetchall()]
    conn.close()
    contracts = [enrich_pm_asset({**c, "next_pm_date": "", "status": ""}) for c in contracts]
    return {**counts, "upcoming": upcoming, "hospitals": hospitals, "contracts": contracts}

@app.get("/api/pm-calendar")
def pm_calendar(month: str = ""):
    today = date.today()
    if month:
        try:
            start = date.fromisoformat(month[:7] + "-01")
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    else:
        start = today.replace(day=1)
    end = start.replace(year=start.year + 1, month=1, day=1) if start.month == 12 else start.replace(month=start.month + 1, day=1)
    conn = db()
    rows = [enrich_pm_asset(r) for r in conn.execute("SELECT * FROM pm_assets WHERE next_pm_date >= ? AND next_pm_date < ? ORDER BY next_pm_date, hospital, asset_tag", (start.isoformat(), end.isoformat())).fetchall()]
    overdue = [enrich_pm_asset(r) for r in conn.execute("SELECT * FROM pm_assets WHERE next_pm_date < ? AND lower(COALESCE(status,'')) != 'completed' ORDER BY next_pm_date, hospital, asset_tag", (today.isoformat(),)).fetchall()]
    conn.close()
    return {
        "month": start.strftime("%Y-%m"),
        "items": rows,
        "overdue": overdue,
        "due_today": [r for r in rows if r["timing_status"] == "due_today"],
        "due_this_week": [r for r in rows if r["timing_status"] in {"due_today", "due_this_week"}],
    }

@app.get("/api/pm-reports")
def pm_reports(report: str = "completion"):
    conn = db()
    if report == "completion":
        df = pd.read_sql_query("""
            SELECT t.*, a.asset_tag, a.hospital, a.department, a.model, a.serial_number
            FROM pm_tasks t LEFT JOIN pm_assets a ON a.id=t.asset_id
            WHERE lower(t.status)='completed' ORDER BY t.completed_date DESC
        """, conn)
        filename = "pm_completion_report.xlsx"
    elif report == "overdue":
        df = pd.read_sql_query("""
            SELECT * FROM pm_assets
            WHERE next_pm_date < ? AND lower(COALESCE(status,'')) != 'completed'
            ORDER BY next_pm_date, hospital
        """, conn, params=(date.today().isoformat(),))
        filename = "pm_overdue_report.xlsx"
    elif report == "hospital-schedule":
        df = pd.read_sql_query("""
            SELECT pm_assets.hospital, pm_assets.department, pm_assets.asset_tag, pm_assets.manufacturer,
                   pm_assets.model, pm_assets.serial_number, pm_assets.next_pm_date, pm_assets.last_pm_date,
                   pm_assets.status AS asset_status, pm_tasks.assigned_to
            FROM pm_assets LEFT JOIN pm_tasks ON pm_tasks.asset_id=pm_assets.id
            ORDER BY pm_assets.hospital, pm_assets.next_pm_date
        """, conn)
        filename = "hospital_pm_schedule.xlsx"
    elif report == "engineer-assignments":
        df = pd.read_sql_query("""
            SELECT t.assigned_to, t.task_name, t.status, t.due_date, t.completed_date,
                   a.asset_tag, a.hospital, a.department, a.model
            FROM pm_tasks t LEFT JOIN pm_assets a ON a.id=t.asset_id
            ORDER BY t.assigned_to, t.due_date
        """, conn)
        filename = "engineer_assignment_report.xlsx"
    elif report == "assets-export":
        df = pd.read_sql_query("SELECT * FROM pm_assets ORDER BY hospital, department, asset_tag", conn)
        filename = "pm_assets_export.xlsx"
    elif report == "contracts":
        df = pd.read_sql_query("""
            SELECT hospital, contract_no, MIN(contract_start_date) AS contract_start_date,
                   MAX(contract_end_date) AS contract_end_date, COUNT(*) AS asset_count,
                   GROUP_CONCAT(asset_tag, ', ') AS assets
            FROM pm_assets
            WHERE COALESCE(contract_no, '') != ''
            GROUP BY hospital, contract_no
            ORDER BY contract_end_date, hospital
        """, conn)
        filename = "pm_contracts_report.xlsx"
    elif report == "history":
        df = pd.read_sql_query("""
            SELECT h.created_at, h.action, h.engineer, h.notes, a.asset_tag, a.hospital, a.department, a.model
            FROM pm_history h LEFT JOIN pm_assets a ON a.id=h.asset_id
            ORDER BY h.created_at DESC
        """, conn)
        filename = "pm_history_report.xlsx"
    else:
        conn.close()
        raise HTTPException(status_code=404, detail="Unknown PM report")
    conn.close()
    path = DATA_DIR / filename
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.fillna("").to_excel(writer, sheet_name=report[:31], index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(length + 4, 55)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)


@app.post("/api/pm-import")
async def import_pm_assets(file: UploadFile = File(...)):
    contents = await file.read()
    suffix = Path(file.filename or "").suffix.lower()
    try:
        if suffix in {".csv", ".txt"}:
            imported_df = pd.read_csv(io.BytesIO(contents))
        else:
            imported_df = pd.read_excel(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PM import file: {exc}")

    if imported_df.empty:
        return {"message": "imported", "inserted": 0, "updated": 0, "skipped": 0}

    def val(row, names, default=""):
        col = find_col(imported_df, names)
        if not col:
            return default
        raw = row.get(col, default)
        if pd.isna(raw):
            return default
        if isinstance(raw, datetime):
            return raw.date().isoformat()
        if isinstance(raw, date):
            return raw.isoformat()
        return str(raw).strip()

    inserted = updated = skipped = 0
    conn = db()
    for idx, row in imported_df.iterrows():
        serial = val(row, ["serial_number", "Serial Number", "Serial", "S/N"])
        asset_tag = val(row, ["asset_tag", "Asset Tag", "Tag", "ID"])
        equipment = val(row, ["equipment", "Equipment", "Device", "Asset"])
        model = val(row, ["model", "Model"], equipment)
        hospital = val(row, ["hospital", "Hospital", "Client", "Customer"])
        if not asset_tag:
            asset_tag = serial or "-".join(p for p in [hospital, model, str(idx + 1)] if p).replace(" ", "-")
        if not asset_tag:
            skipped += 1
            continue

        pms_per_year = val(row, ["PMs per Year", "pmsPerYear", "pms_per_year"])
        frequency_days = val(row, ["frequency_days", "Frequency Days", "PM Frequency Days"])
        if not frequency_days and pms_per_year:
            try:
                frequency_days = str(max(1, round(365 / max(1, float(pms_per_year)))))
            except ValueError:
                frequency_days = "180"
        try:
            frequency_days_int = int(float(frequency_days or 180))
        except ValueError:
            frequency_days_int = 180

        payload = {
            "asset_tag": asset_tag,
            "serial_number": serial,
            "manufacturer": val(row, ["manufacturer", "Manufacturer", "Make"]),
            "model": model,
            "department": val(row, ["department", "Department", "Dept"]),
            "hospital": hospital,
            "location": val(row, ["location", "Location", "Room"]),
            "engineer": val(row, ["engineer", "Engineer", "Assigned To", "assigned_to"]),
            "contact_email": val(row, ["contact_email", "Contact Email", "Hospital Contact Email", "Email"]),
            "contract_no": val(row, ["contract_no", "Contract No.", "Contract No", "Contract Number", "contractNo"]),
            "contract_start_date": val(row, ["contract_start_date", "Contract Start Date", "contractStartDate"]),
            "contract_end_date": val(row, ["contract_end_date", "Contract End Date", "contractEndDate"]),
            "frequency_days": frequency_days_int,
            "next_pm_date": val(row, ["next_pm_date", "Next PM Date", "nextPmDate", "PM1", "PM 1"]),
            "last_pm_date": val(row, ["last_pm_date", "Last PM Date", "lastPmDate"]),
            "status": val(row, ["status", "Status"], "Upcoming") or "Upcoming",
            "notes": val(row, ["notes", "Notes", "Comments"]),
            "linked_inventory_pn": val(row, ["linked_inventory_pn", "Linked Inventory PN", "PN", "Part Number"]),
            "barcode": val(row, ["barcode", "Barcode"]),
        }
        existing = conn.execute("SELECT id FROM pm_assets WHERE asset_tag=?", (asset_tag,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE pm_assets
                SET serial_number=?, manufacturer=?, model=?, department=?, hospital=?, location=?,
                    engineer=?, contact_email=?, contract_no=?, contract_start_date=?, contract_end_date=?,
                    frequency_days=?, next_pm_date=?, last_pm_date=?, status=?, notes=?, linked_inventory_pn=?,
                    barcode=?, updated_at=?
                WHERE id=?
            """, (payload["serial_number"], payload["manufacturer"], payload["model"], payload["department"],
                  payload["hospital"], payload["location"], payload["engineer"], payload["contact_email"],
                  payload["contract_no"], payload["contract_start_date"], payload["contract_end_date"],
                  payload["frequency_days"], payload["next_pm_date"], payload["last_pm_date"], payload["status"],
                  payload["notes"], payload["linked_inventory_pn"], payload["barcode"], now(), existing["id"]))
            conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                         (existing["id"], "PM_IMPORT_UPDATE", f"Updated from {file.filename}", payload["engineer"], now()))
            updated += 1
        else:
            cur = conn.execute("""
                INSERT INTO pm_assets
                (asset_tag, serial_number, manufacturer, model, department, hospital, location,
                 engineer, contact_email, contract_no, contract_start_date, contract_end_date, frequency_days,
                 next_pm_date, last_pm_date, status, notes, linked_inventory_pn, barcode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(payload[k] for k in [
                "asset_tag", "serial_number", "manufacturer", "model", "department", "hospital", "location",
                "engineer", "contact_email", "contract_no", "contract_start_date", "contract_end_date", "frequency_days",
                "next_pm_date", "last_pm_date", "status", "notes", "linked_inventory_pn", "barcode"
            ]) + (now(), now()))
            conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                         (cur.lastrowid, "PM_IMPORT_INSERT", f"Imported from {file.filename}", payload["engineer"], now()))
            inserted += 1
    conn.commit()
    conn.close()
    return {"message": "imported", "filename": file.filename, "inserted": inserted, "updated": updated, "skipped": skipped}


@app.get("/api/clean-inventory")
def clean_inventory(q: str = "", location: str = "", limit: int = 1000):
    conn = db()
    where, args = [], []

    if q:
        where.append("(pn LIKE ? OR description LIKE ? OR barcode LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if location:
        where.append("location LIKE ?")
        args.append(f"%{location}%")

    sql = """
        SELECT
            id,
            pn,
            description,
            barcode,
            location,
            system_qty AS expected_qty,
            photo_url
        FROM inventory
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY location, pn LIMIT ?"
    args.append(limit)

    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows



@app.get("/api/item-options")
def item_options(q: str = "", limit: int = 300):
    conn = db()
    args = []
    sql = """
        SELECT id, pn, description, barcode, location, physical_qty, system_qty
        FROM inventory
    """
    if q:
        sql += " WHERE pn LIKE ? OR description LIKE ? OR barcode LIKE ?"
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    sql += " ORDER BY pn LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows


@app.get("/api/items")
def list_items(q: str = "", status: str = "", location: str = "", limit: int = 1000):
    conn = db()
    where, args = [], []
    if q:
        where.append("(pn LIKE ? OR description LIKE ? OR device_family LIKE ? OR barcode LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
    if status:
        where.append("status = ?")
        args.append(status)
    if location:
        where.append("location LIKE ?")
        args.append(f"%{location}%")
    sql = "SELECT * FROM inventory"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY location, pn LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows

@app.post("/api/items")
def create_item(item: InventoryItem):
    conn = db()
    diff = item.physical_qty - item.system_qty
    status = item.status or compute_status(item.system_qty, item.physical_qty)
    family = item.device_family or detect_family(item.description)
    lookup_url = lookup_url_for(item.pn, item.description)
    cur = conn.execute("""
        INSERT INTO inventory
        (pn, description, location, system_qty, physical_qty, difference, device_family, status, notes, source, updated_at, barcode, photo_url, lookup_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (item.pn.strip(), item.description, item.location, item.system_qty, item.physical_qty,
          diff, family, status, item.notes, "WEB_APP", now(), item.barcode, item.photo_url, lookup_url))
    audit(conn, cur.lastrowid, "CREATE_ITEM", "", item.dict(), item.notes)
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    export_excel(EXCEL_PATH)
    return {"id": new_id, "message": "created"}

@app.put("/api/items/{item_id}")
def update_item(item_id: int, item: InventoryItem):
    conn = db()
    old = conn.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    diff = item.physical_qty - item.system_qty
    status = item.status or compute_status(item.system_qty, item.physical_qty)
    family = item.device_family or detect_family(item.description)
    lookup_url = lookup_url_for(item.pn, item.description)
    conn.execute("""
        UPDATE inventory
        SET pn=?, description=?, location=?, system_qty=?, physical_qty=?, difference=?,
            device_family=?, status=?, notes=?, updated_at=?, barcode=?, photo_url=?, lookup_url=?
        WHERE id=?
    """, (item.pn.strip(), item.description, item.location, item.system_qty, item.physical_qty,
          diff, family, status, item.notes, now(), item.barcode, item.photo_url, lookup_url, item_id))
    audit(conn, item_id, "UPDATE_ITEM", dict(old), item.dict(), item.notes)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "updated"}

@app.patch("/api/items/{item_id}/quantity")
def quick_update_quantity(item_id: int, update: QuantityUpdate):
    conn = db()
    old = conn.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    old_qty = int(old["physical_qty"] or 0)
    new_qty = int(update.physical_qty)
    system_qty = int(old["system_qty"] or 0)
    diff = new_qty - system_qty
    status = compute_status(system_qty, new_qty)
    conn.execute("""
        UPDATE inventory SET physical_qty=?, difference=?, status=?, updated_at=? WHERE id=?
    """, (new_qty, diff, status, now(), item_id))
    audit(conn, item_id, "QUICK_QTY_EDIT", old_qty, new_qty, update.reason)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "quantity updated", "old_qty": old_qty, "new_qty": new_qty, "difference": diff, "status": status}


@app.post("/api/audit/approve-physical-as-expected")
def approve_physical_as_expected():
    """
    After the physical audit is approved, this locks the verified physical_qty
    as the new expected/system quantity.
    It first exports a mismatch report, then updates system_qty=physical_qty.
    """
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM inventory ORDER BY location, pn").fetchall()]

    mismatches = []
    approved_count = 0

    for item in rows:
        old_expected = int(item["system_qty"] or 0)
        physical = int(item["physical_qty"] or 0)
        diff = physical - old_expected

        if diff != 0:
            mismatches.append({
                "PN": item["pn"],
                "Description": item["description"],
                "Location": item["location"],
                "Old Expected Qty": old_expected,
                "Approved Physical Qty": physical,
                "Difference": diff,
                "Barcode": item["barcode"],
                "Notes": item["notes"],
            })

        conn.execute("""
            UPDATE inventory
            SET system_qty=?, difference=?, status=?, updated_at=?
            WHERE id=?
        """, (physical, 0, "MATCHED", now(), item["id"]))

        audit(
            conn,
            item["id"],
            "APPROVE_PHYSICAL_AS_EXPECTED",
            f"old_expected={old_expected}",
            f"new_expected={physical}",
            "Physical audit approved and converted to expected quantity"
        )
        approved_count += 1

    conn.commit()
    conn.close()

    # Export full Excel after approval
    export_excel(EXCEL_PATH)

    # Create mismatch approval report
    report_path = DATA_DIR / "audit_approval_mismatch_report.xlsx"
    df = pd.DataFrame(mismatches)
    if df.empty:
        df = pd.DataFrame(columns=[
            "PN", "Description", "Location", "Old Expected Qty",
            "Approved Physical Qty", "Difference", "Barcode", "Notes"
        ])

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="AUDIT_MISMATCHES", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(length + 4, 55)

    return {
        "message": "Physical quantities approved as new expected quantities",
        "approved_items": approved_count,
        "mismatch_count": len(mismatches),
        "report": "/api/audit/mismatch-report"
    }


@app.get("/api/audit/mismatch-report")
def download_audit_mismatch_report():
    report_path = DATA_DIR / "audit_approval_mismatch_report.xlsx"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Mismatch report has not been generated yet")
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="audit_approval_mismatch_report.xlsx"
    )



@app.delete("/api/items/{item_id}")
def delete_item(item_id: int):
    conn = db()
    old = conn.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
    conn.execute("DELETE FROM inventory WHERE id=?", (item_id,))
    audit(conn, item_id, "DELETE_ITEM", dict(old), "", "")
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "deleted"}

@app.post("/api/items/{item_id}/photo")
async def upload_item_photo(item_id: int, file: UploadFile = File(...)):
    safe = "".join(ch for ch in file.filename if ch.isalnum() or ch in "._-").strip() or "photo.jpg"
    suffix = Path(safe).suffix.lower()
    if suffix not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Only jpg, png, or webp photos are supported.")
    name = f"item_{item_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    dest = UPLOADS_DIR / name
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    photo_url = f"/uploads/{name}"
    conn = db()
    conn.execute("UPDATE inventory SET photo_url=?, updated_at=? WHERE id=?", (photo_url, now(), item_id))
    audit(conn, item_id, "PHOTO_UPLOAD", "", photo_url, "")
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "photo uploaded", "photo_url": photo_url}

@app.post("/api/transactions")
def create_transaction(tx: TransactionIn):
    direction = tx.direction.upper()

    if direction not in ["IN", "OUT"]:
        raise HTTPException(status_code=400, detail="direction must be IN or OUT")
    if tx.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")

    if direction == "IN" and not tx.purchase_order_no.strip():
        raise HTTPException(status_code=400, detail="IN transactions require a Purchase Order number")
    if direction == "OUT" and not tx.client_order_no.strip():
        raise HTTPException(status_code=400, detail="OUT transactions require a Client Order number")

    conn = db()

    if direction == "IN":
        conn.execute("""
            INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(po_no) DO UPDATE SET updated_at=excluded.updated_at
        """, (tx.purchase_order_no, "", "OPEN", "", "Auto-created from IN transaction", now(), now()))

    if direction == "OUT":
        conn.execute("""
            INSERT INTO client_orders (client_order_no, client_name, status, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_order_no) DO UPDATE SET
                client_name=COALESCE(NULLIF(excluded.client_name,''), client_orders.client_name),
                updated_at=excluded.updated_at
        """, (tx.client_order_no, tx.client_name, "OPEN", "", "Auto-created from OUT transaction", now(), now()))

    item = conn.execute(
        "SELECT * FROM inventory WHERE barcode=? OR pn=? LIMIT 1",
        (tx.barcode_or_pn.strip(), tx.barcode_or_pn.strip())
    ).fetchone()

    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="No item found for this barcode or PN")

    pm_asset = None
    if tx.pm_asset_id:
        pm_asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (tx.pm_asset_id,)).fetchone()
        if not pm_asset:
            conn.close()
            raise HTTPException(status_code=404, detail="PM asset not found")

    old_qty = int(item["physical_qty"] or 0)
    new_qty = old_qty + tx.qty if direction == "IN" else old_qty - tx.qty

    if new_qty < 0:
        conn.close()
        raise HTTPException(status_code=400, detail="OUT transaction would make stock negative")

    system_qty = int(item["system_qty"] or 0)
    diff = new_qty - system_qty
    status = compute_status(system_qty, new_qty)

    conn.execute("UPDATE inventory SET physical_qty=?, difference=?, status=?, updated_at=? WHERE id=?",
                 (new_qty, diff, status, now(), item["id"]))

    conn.execute("""
        INSERT INTO transactions
        (item_id, pn, barcode, direction, qty, old_qty, new_qty, purchase_order_no, client_order_no, client_name, pm_asset_id, pm_asset_tag, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item["id"], item["pn"], item["barcode"], direction, tx.qty, old_qty, new_qty,
        tx.purchase_order_no if direction == "IN" else "",
        tx.client_order_no if direction == "OUT" else "",
        tx.client_name if direction == "OUT" else "",
        tx.pm_asset_id if tx.pm_asset_id else "",
        pm_asset["asset_tag"] if pm_asset else "",
        tx.notes, now()
    ))

    ref = f"PO={tx.purchase_order_no}" if direction == "IN" else f"CLIENT_ORDER={tx.client_order_no}; CLIENT={tx.client_name}"
    audit(conn, item["id"], f"TRANSACTION_{direction}", old_qty, new_qty, f"{ref}; {tx.notes}")
    if pm_asset and direction == "OUT":
        conn.execute("""
            INSERT INTO pm_history (asset_id, action, notes, engineer, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            pm_asset["id"], "SPARE_PART_OUT",
            f"Used PN {item['pn']} qty {tx.qty}. Transaction note: {tx.notes}",
            "", now()
        ))

    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "transaction saved", "pn": item["pn"], "old_qty": old_qty, "new_qty": new_qty, "reference": ref}


@app.post("/api/transactions/bulk")
def bulk_transactions(payload: dict):
    direction = str(payload.get("direction", "")).upper()
    purchase_order_no = str(payload.get("purchase_order_no", "")).strip()
    client_order_no = str(payload.get("client_order_no", "")).strip()
    client_name = str(payload.get("client_name", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    lines = payload.get("lines", [])

    if direction not in ["IN", "OUT"]:
        raise HTTPException(status_code=400, detail="direction must be IN or OUT")
    if direction == "IN" and not purchase_order_no:
        raise HTTPException(status_code=400, detail="Bulk IN requires Purchase Order number")
    if direction == "OUT" and not client_order_no:
        raise HTTPException(status_code=400, detail="Bulk OUT requires Client Order number")
    if not isinstance(lines, list) or not lines:
        raise HTTPException(status_code=400, detail="No transaction lines provided")

    conn = db()

    if direction == "IN":
        conn.execute("""
            INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(po_no) DO UPDATE SET updated_at=excluded.updated_at
        """, (purchase_order_no, "", "OPEN", "", "Auto-created from bulk IN transaction", now(), now()))

    if direction == "OUT":
        conn.execute("""
            INSERT INTO client_orders (client_order_no, client_name, status, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_order_no) DO UPDATE SET
                client_name=COALESCE(NULLIF(excluded.client_name,''), client_orders.client_name),
                updated_at=excluded.updated_at
        """, (client_order_no, client_name, "OPEN", "", "Auto-created from bulk OUT transaction", now(), now()))

    processed = 0
    errors = []

    for idx, line in enumerate(lines, start=1):
        item_id = line.get("item_id")
        qty = int(line.get("qty") or 0)

        if qty <= 0:
            errors.append(f"Line {idx}: qty must be positive")
            continue

        item = conn.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
        if not item:
            errors.append(f"Line {idx}: item not found")
            continue

        old_qty = int(item["physical_qty"] or 0)
        new_qty = old_qty + qty if direction == "IN" else old_qty - qty

        if new_qty < 0:
            errors.append(f"Line {idx}: OUT would make stock negative for PN {item['pn']}")
            continue

        system_qty = int(item["system_qty"] or 0)
        diff = new_qty - system_qty
        status = compute_status(system_qty, new_qty)

        conn.execute("""
            UPDATE inventory
            SET physical_qty=?, difference=?, status=?, updated_at=?
            WHERE id=?
        """, (new_qty, diff, status, now(), item["id"]))

        conn.execute("""
            INSERT INTO transactions
            (item_id, pn, barcode, direction, qty, old_qty, new_qty, purchase_order_no, client_order_no, client_name, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["id"], item["pn"], item["barcode"], direction, qty, old_qty, new_qty,
            purchase_order_no if direction == "IN" else "",
            client_order_no if direction == "OUT" else "",
            client_name if direction == "OUT" else "",
            notes, now()
        ))

        ref = f"PO={purchase_order_no}" if direction == "IN" else f"CLIENT_ORDER={client_order_no}; CLIENT={client_name}"
        audit(conn, item["id"], f"BULK_TRANSACTION_{direction}", old_qty, new_qty, f"{ref}; {notes}")

        processed += 1

    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)

    return {"message": "bulk transaction processed", "processed": processed, "errors": errors}



@app.get("/api/transactions")
def list_transactions(limit: int = 300):
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    conn.close()
    return rows


def receive_purchase_order(conn, po_no: str):
    lines = conn.execute(
        "SELECT * FROM purchase_order_items WHERE po_no=? AND received=0",
        (po_no,)
    ).fetchall()

    received_count = 0

    for line in lines:
        qty = int(line["qty"] or 0)
        if qty <= 0:
            continue

        item = conn.execute(
            "SELECT * FROM inventory WHERE pn=? OR barcode=? LIMIT 1",
            (line["pn"], line["barcode"] or line["pn"])
        ).fetchone()

        if item:
            old_qty = int(item["physical_qty"] or 0)
            new_qty = old_qty + qty
            system_qty = int(item["system_qty"] or 0)
            diff = new_qty - system_qty
            status = compute_status(system_qty, new_qty)

            conn.execute("""
                UPDATE inventory
                SET physical_qty=?, difference=?, status=?, updated_at=?
                WHERE id=?
            """, (new_qty, diff, status, now(), item["id"]))

            item_id = item["id"]
            barcode = item["barcode"]

        else:
            system_qty = 0
            new_qty = qty
            diff = new_qty - system_qty
            status = compute_status(system_qty, new_qty)
            family = line["device_family"] or detect_family(line["description"])
            lookup_url = lookup_url_for(line["pn"], line["description"])

            cur = conn.execute("""
                INSERT INTO inventory
                (pn, description, location, system_qty, physical_qty, difference, device_family, status,
                 notes, source, updated_at, barcode, photo_url, lookup_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                line["pn"], line["description"], line["location"], system_qty, new_qty, diff,
                family, status, line["notes"], "PO_RECEIVED", now(),
                line["barcode"], "", lookup_url
            ))

            item_id = cur.lastrowid
            barcode = line["barcode"]
            old_qty = 0

        conn.execute("""
            INSERT INTO transactions
            (item_id, pn, barcode, direction, qty, old_qty, new_qty, purchase_order_no, client_order_no, client_name, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, line["pn"], barcode, "IN", qty, old_qty, new_qty,
            po_no, "", "", f"Auto received from PO {po_no}", now()
        ))

        conn.execute("""
            UPDATE purchase_order_items
            SET received=1, received_qty=?, updated_at=?
            WHERE id=?
        """, (qty, now(), line["id"]))

        audit(conn, item_id, "PO_RECEIVED_AUTO_STOCK_IN", old_qty, new_qty, f"PO={po_no}; PN={line['pn']}; qty={qty}")
        received_count += 1

    return received_count


@app.post("/api/purchase-orders")
def create_po(po: PurchaseOrder):
    conn = db()
    previous = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (po.po_no,)).fetchone()

    conn.execute("""
        INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(po_no) DO UPDATE SET
            supplier=excluded.supplier,
            status=excluded.status,
            expected_date=excluded.expected_date,
            notes=excluded.notes,
            updated_at=excluded.updated_at
    """, (po.po_no, po.supplier, po.status, po.expected_date, po.notes, now(), now()))

    audit(conn, None, "UPSERT_PO", dict(previous) if previous else "", po.dict(), "")

    received_count = 0
    if po.status.upper() == "RECEIVED":
        received_count = receive_purchase_order(conn, po.po_no)

    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "purchase order saved", "auto_received_items": received_count}



@app.post("/api/purchase-orders/items/bulk")
def bulk_add_po_items(payload: dict):
    po_no = str(payload.get("po_no", "")).strip()
    text = str(payload.get("text", "")).strip()

    if not po_no:
        raise HTTPException(status_code=400, detail="PO number is required")
    if not text:
        raise HTTPException(status_code=400, detail="Bulk item text is empty")

    conn = db()

    po = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (po_no,)).fetchone()
    if not po:
        conn.execute("""
            INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (po_no, "", "OPEN", "", "Auto-created PO from bulk item entry", now(), now()))

    added = 0
    errors = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        # Supports tab, comma, semicolon, or pipe separated:
        # PN | Description | Qty | Location | Barcode
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif "|" in line:
            parts = [p.strip() for p in line.split("|")]
        elif ";" in line:
            parts = [p.strip() for p in line.split(";")]
        else:
            parts = [p.strip() for p in line.split(",")]

        while len(parts) < 5:
            parts.append("")

        pn, description, qty_raw, location, barcode = parts[:5]

        if not pn:
            errors.append(f"Line {line_no}: missing PN")
            continue

        try:
            qty = int(float(qty_raw)) if qty_raw else 1
        except Exception:
            errors.append(f"Line {line_no}: invalid qty '{qty_raw}'")
            continue

        if qty <= 0:
            errors.append(f"Line {line_no}: qty must be positive")
            continue

        family = detect_family(description)

        conn.execute("""
            INSERT INTO purchase_order_items
            (po_no, pn, description, qty, received_qty, location, barcode, device_family, notes, received, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            po_no, pn, description, qty, 0,
            location, barcode, family, "Bulk added", 0, now(), now()
        ))

        audit(conn, None, "BULK_ADD_PO_ITEM", "", f"PO={po_no}; PN={pn}; qty={qty}", raw_line)
        added += 1

    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)

    return {"message": "bulk PO items processed", "added": added, "errors": errors}


@app.post("/api/purchase-orders/items")
def add_po_item(line: PurchaseOrderLine):
    if line.qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")

    conn = db()
    po = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (line.po_no,)).fetchone()
    if not po:
        conn.execute("""
            INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (line.po_no, "", "OPEN", "", "Auto-created PO from line item entry", now(), now()))

    family = line.device_family or detect_family(line.description)

    cur = conn.execute("""
        INSERT INTO purchase_order_items
        (po_no, pn, description, qty, received_qty, location, barcode, device_family, notes, received, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        line.po_no, line.pn.strip(), line.description, line.qty, 0,
        line.location, line.barcode, family, line.notes, 0, now(), now()
    ))

    audit(conn, None, "ADD_PO_ITEM", "", line.dict(), f"PO={line.po_no}")
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "PO item added", "id": new_id}


@app.get("/api/purchase-orders/{po_no}/items")
def list_po_items(po_no: str):
    conn = db()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM purchase_order_items WHERE po_no=? ORDER BY id DESC",
        (po_no,)
    ).fetchall()]
    conn.close()
    return rows


@app.get("/api/purchase-orders/items/all")
def list_all_po_items(limit: int = 500):
    conn = db()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM purchase_order_items ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    ).fetchall()]
    conn.close()
    return rows


@app.delete("/api/purchase-orders/items/{line_id}")
def delete_po_item(line_id: int):
    conn = db()
    old = conn.execute("SELECT * FROM purchase_order_items WHERE id=?", (line_id,)).fetchone()
    if not old:
        conn.close()
        raise HTTPException(status_code=404, detail="PO item not found")
    if int(old["received"] or 0) == 1:
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot delete a received PO item")
    conn.execute("DELETE FROM purchase_order_items WHERE id=?", (line_id,))
    audit(conn, None, "DELETE_PO_ITEM", dict(old), "", f"PO={old['po_no']}")
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "PO item deleted"}


@app.post("/api/purchase-orders/{po_no}/receive")
def receive_po_now(po_no: str):
    conn = db()
    po = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (po_no,)).fetchone()
    if not po:
        conn.close()
        raise HTTPException(status_code=404, detail="PO not found")

    received_count = receive_purchase_order(conn, po_no)

    conn.execute("""
        UPDATE purchase_orders
        SET status=?, updated_at=?
        WHERE po_no=?
    """, ("RECEIVED", now(), po_no))

    audit(conn, None, "RECEIVE_PO", "", f"received_count={received_count}", f"PO={po_no}")
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "PO received", "auto_received_items": received_count}


@app.get("/api/purchase-orders")
def list_pos():
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM purchase_orders ORDER BY updated_at DESC").fetchall()]
    conn.close()
    return rows

@app.get("/api/audit")
def list_audit(limit: int = 500):
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    conn.close()
    return rows


@app.post("/api/client-orders")
def create_client_order(order: ClientOrder):
    conn = db()
    conn.execute("""
        INSERT INTO client_orders (client_order_no, client_name, status, expected_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(client_order_no) DO UPDATE SET
            client_name=excluded.client_name,
            status=excluded.status,
            expected_date=excluded.expected_date,
            notes=excluded.notes,
            updated_at=excluded.updated_at
    """, (order.client_order_no, order.client_name, order.status, order.expected_date, order.notes, now(), now()))
    audit(conn, None, "UPSERT_CLIENT_ORDER", "", order.dict(), "")
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "client order saved"}


@app.get("/api/client-orders")
def list_client_orders():
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM client_orders ORDER BY updated_at DESC").fetchall()]
    conn.close()
    return rows



@app.get("/api/purchase-orders/{po_no}/export")
def export_purchase_order(po_no: str):
    conn = db()
    po = pd.read_sql_query("SELECT * FROM purchase_orders WHERE po_no=?", conn, params=(po_no,))
    items = pd.read_sql_query("SELECT * FROM purchase_order_items WHERE po_no=? ORDER BY id", conn, params=(po_no,))
    tx = pd.read_sql_query("SELECT * FROM transactions WHERE purchase_order_no=? ORDER BY created_at DESC", conn, params=(po_no,))
    conn.close()

    if po.empty:
        raise HTTPException(status_code=404, detail="PO not found")

    path = DATA_DIR / f"purchase_order_{po_no}.xlsx"
    safe_path = DATA_DIR / ("purchase_order_" + "".join(ch for ch in po_no if ch.isalnum() or ch in "-_") + ".xlsx")

    with pd.ExcelWriter(safe_path, engine="openpyxl") as writer:
        po.to_excel(writer, sheet_name="PURCHASE_ORDER", index=False)
        items.to_excel(writer, sheet_name="ITEMS", index=False)
        tx.to_excel(writer, sheet_name="LINKED_TRANSACTIONS", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(length + 4, 55)

    return FileResponse(
        safe_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_path.name
    )


@app.get("/api/client-orders/{client_order_no}/export")
def export_client_order(client_order_no: str):
    conn = db()
    co = pd.read_sql_query("SELECT * FROM client_orders WHERE client_order_no=?", conn, params=(client_order_no,))
    tx = pd.read_sql_query("SELECT * FROM transactions WHERE client_order_no=? ORDER BY created_at DESC", conn, params=(client_order_no,))
    conn.close()

    if co.empty:
        raise HTTPException(status_code=404, detail="Client order not found")

    safe_path = DATA_DIR / ("client_order_" + "".join(ch for ch in client_order_no if ch.isalnum() or ch in "-_") + ".xlsx")

    with pd.ExcelWriter(safe_path, engine="openpyxl") as writer:
        co.to_excel(writer, sheet_name="CLIENT_ORDER", index=False)
        tx.to_excel(writer, sheet_name="LINKED_OUT_TRANSACTIONS", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(length + 4, 55)

    return FileResponse(
        safe_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_path.name
    )


@app.get("/api/dashboard")
def dashboard():
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM inventory").fetchall()]
    tx_count = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
    po_count = conn.execute("SELECT COUNT(*) AS c FROM purchase_orders").fetchone()["c"]
    client_order_count = conn.execute("SELECT COUNT(*) AS c FROM client_orders").fetchone()["c"]
    audit_count = conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()["c"]
    conn.close()
    df = pd.DataFrame(rows)
    if df.empty:
        return {}
    multi = df.groupby("pn")["location"].nunique()
    return {
        "total_records": len(df),
        "unique_pn": df["pn"].nunique(),
        "locations": df["location"].nunique(),
        "missing_from_shelf": int(((df.system_qty > 0) & (df.physical_qty == 0)).sum()),
        "found_not_in_erp": int(((df.physical_qty > 0) & (df.system_qty == 0)).sum()),
        "mismatches": int((df.system_qty != df.physical_qty).sum()),
        "dead_stale_candidates": int(((df.physical_qty > 3) & (df.system_qty == 0)).sum()),
        "present_in_two_places": int((multi > 1).sum()),
        "with_photos": int(df["photo_url"].fillna("").astype(str).str.len().gt(0).sum()),
        "with_barcodes": int(df["barcode"].fillna("").astype(str).str.len().gt(0).sum()),
        "transactions": tx_count,
        "purchase_orders": po_count,
        "client_orders": client_order_count,
        "audit_events": audit_count,
        "excel_path": str(EXCEL_PATH),
    }

@app.get("/api/report/{report_name}")
def report(report_name: str):
    conn = db()
    df = pd.read_sql_query("SELECT * FROM inventory", conn)
    conn.close()
    if df.empty:
        return []
    if report_name == "missing":
        out = df[(df.system_qty > 0) & (df.physical_qty == 0)]
    elif report_name == "found":
        out = df[(df.physical_qty > 0) & (df.system_qty == 0)]
    elif report_name == "stale":
        out = df[(df.physical_qty > 3) & (df.system_qty == 0)]
    elif report_name == "mismatch":
        out = df[df.system_qty != df.physical_qty]
    elif report_name == "multi-location":
        pns = df.groupby("pn")["location"].nunique()
        out = df[df.pn.isin(pns[pns > 1].index.tolist())].sort_values(["pn", "location"])
    else:
        raise HTTPException(status_code=404, detail="Unknown report")
    return out.fillna("").to_dict(orient="records")

@app.get("/api/items/{item_id}/qr")
def item_qr(item_id: int):
    conn = db()
    item = conn.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    payload = f"PN: {item['pn']}\nDescription: {item['description']}\nBarcode: {item['barcode'] or item['pn']}\nLocation: {item['location']}"
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/api/qr-labels", response_class=HTMLResponse)
def qr_labels():
    conn = db()
    items = [dict(r) for r in conn.execute("SELECT * FROM inventory ORDER BY location, pn").fetchall()]
    conn.close()
    cards = []
    for item in items:
        payload = f"PN: {item['pn']}\nDescription: {item['description']}\nBarcode: {item.get('barcode') or item['pn']}\nLocation: {item['location']}"
        img = qrcode.make(payload)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        cards.append(f"""
        <div class="label">
          <img src="data:image/png;base64,{b64}" />
          <div class="text">
            <b>PN: {item['pn']}</b>
            <span>{item['description'] or ''}</span>
            <small>Loc: {item['location'] or ''} | Qty: {item['physical_qty']}</small>
          </div>
        </div>
        """)
    return f"""
    <html><head><title>QR Labels</title>
    <style>
    body{{font-family:Arial,sans-serif;margin:12px}}
    .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
    .label{{border:1px solid #222;padding:8px;height:180px;display:grid;grid-template-columns:82px 1fr;gap:8px;align-items:start;break-inside:avoid}}
    img{{width:82px;height:82px}}
    .text{{display:flex;flex-direction:column;gap:4px}}
    b{{font-size:13px}}
    span{{font-size:11px;line-height:1.25}}
    small{{font-size:10px}}
    @media print{{button{{display:none}}.grid{{grid-template-columns:repeat(3,1fr)}}}}
    </style></head><body>
    <button onclick="window.print()">Print QR Labels</button>
    <div class="grid">{''.join(cards)}</div>
    </body></html>
    """

@app.get("/api/lookup")
def lookup_description(pn: str, description: str = ""):
    return {"pn": pn, "description": description, "search_url": lookup_url_for(pn, description)}

@app.post("/api/import")
async def upload_excel(file: UploadFile = File(...), mode: str = "append_merge"):
    temp = DATA_DIR / "uploaded_inventory.xlsx"
    temp.write_bytes(await file.read())
    try:
        result = import_excel(temp, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    export_excel(EXCEL_PATH)
    return {"message": "imported", "filename": file.filename, "mode": mode, **result}

@app.post("/api/sync/export")
def sync_export():
    export_excel(EXCEL_PATH)
    return {"message": "exported", "path": str(EXCEL_PATH)}

@app.get("/api/export")
def download_excel():
    export_excel(EXCEL_PATH)
    return FileResponse(EXCEL_PATH, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename="inventory_master_export.xlsx")
