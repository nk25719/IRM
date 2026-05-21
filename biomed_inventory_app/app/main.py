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
APP_ROLE = os.getenv("APP_ROLE", "admin")

app = FastAPI(title="Biomedical Inventory ERP", version="1.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/pm/assets", StaticFiles(directory=BASE_DIR / "static" / "pm" / "assets"), name="pm-assets")
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

class CRMClient(BaseModel):
    name: str
    city: str = ""
    address: str = ""
    main_contact: str = ""
    contact_email: str = ""
    phone: str = ""
    biomedical_department: str = ""
    primary_engineer: str = ""
    status: str = "active"
    financial_status: str = "good standing"
    notes: str = ""

class CRMCommunication(BaseModel):
    type: str = "note"
    user: str = ""
    note: str

class CustomerRequestLineIn(BaseModel):
    requested_item: str
    quantity: int = 1
    item_type: str = "spare_part"
    unit_price: float = 0
    notes: str = ""
    related_equipment_serial: str = ""

class CustomerRequestIn(BaseModel):
    client_hospital: str
    contact_person: str = ""
    request_source: str = "call"
    notes: str = ""
    lines: list[CustomerRequestLineIn]

class DeliverySelection(BaseModel):
    quantities: dict[int, int] = {}

class EquipmentBidItemIn(BaseModel):
    description: str
    expected_qty: int = 1
    model: str = ""
    manufacturer: str = ""
    notes: str = ""

class EquipmentBidIn(BaseModel):
    client_hospital: str
    contact_person: str = ""
    bid_no: str = ""
    tender_source: str = "bid"
    status: str = "draft"
    notes: str = ""
    items: list[EquipmentBidItemIn] = []

class EquipmentReceivingIn(BaseModel):
    item_id: int
    received_qty: int = 0
    serial_numbers: list[str] = []
    notes: str = ""

class BiomedicalRecordIn(BaseModel):
    equipment_id: int
    data: dict = {}

class DocumentExportRequest(BaseModel):
    title: str = ""
    rows: list[dict] = []
    notes: str = ""

class CaseCreate(BaseModel):
    case_type: str
    client_id: int
    contact_id: int | None = None
    equipment_id: int | None = None
    request_id: int | None = None
    quotation_id: int | None = None
    client_order_id: int | None = None
    purchase_order_id: int | None = None
    delivery_note_id: int | None = None
    invoice_id: int | None = None
    engineer_id: int | None = None
    contract_id: int | None = None
    priority: str = "normal"
    notes: str = ""

class CaseUpdate(BaseModel):
    status: str | None = None
    workflow_state: str | None = None
    priority: str | None = None
    notes: str | None = None
    equipment_id: int | None = None
    engineer_id: int | None = None

class CaseWorkflowStateIn(BaseModel):
    state: str
    user: str = ""
    notes: str = ""
    metadata: dict | None = None

def current_role(request: Request | None = None) -> str:
    if request and request.session.get("role"):
        return request.session.get("role")
    return APP_ROLE

def can_edit_crm(role: str) -> bool:
    return role in {"admin", "crm_user", "pm_coordinator", "service_engineer", "procurement"}

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            city TEXT,
            address TEXT,
            main_contact TEXT,
            contact_email TEXT,
            phone TEXT,
            biomedical_department TEXT,
            primary_engineer TEXT,
            status TEXT DEFAULT 'active',
            financial_status TEXT DEFAULT 'good standing',
            credit_balance REAL DEFAULT 0,
            last_payment_date TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            name TEXT,
            role TEXT,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_communications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            type TEXT,
            user TEXT,
            note TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS service_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            equipment_id INTEGER,
            request_id INTEGER,
            call_no TEXT,
            status TEXT,
            engineer TEXT,
            issue TEXT,
            resolution TEXT,
            opened_at TEXT,
            closed_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            equipment_id INTEGER,
            service_call_id INTEGER,
            quotation_no TEXT,
            quote_date TEXT,
            status TEXT,
            amount REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            label TEXT,
            file_url TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_no TEXT UNIQUE,
            client_id INTEGER,
            client_hospital TEXT,
            contact_person TEXT,
            request_source TEXT,
            status TEXT DEFAULT 'open',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_request_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            requested_item TEXT,
            item_type TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            notes TEXT,
            related_equipment_serial TEXT,
            inventory_item_id INTEGER,
            pn TEXT,
            physical_qty INTEGER DEFAULT 0,
            reserved_qty INTEGER DEFAULT 0,
            available_qty INTEGER DEFAULT 0,
            requested_qty INTEGER DEFAULT 0,
            shortage_qty INTEGER DEFAULT 0,
            stock_status TEXT DEFAULT 'unavailable',
            procurement_status TEXT DEFAULT 'not_ordered',
            linked_purchase_order TEXT,
            linked_delivery_note TEXT,
            linked_invoice TEXT,
            delivered_qty INTEGER DEFAULT 0,
            invoiced_qty INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_case_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            client_id INTEGER,
            doc_type TEXT,
            doc_no TEXT,
            status TEXT,
            source_document_id INTEGER,
            quotation_id INTEGER,
            client_order_id INTEGER,
            delivery_note_id INTEGER,
            amount REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_case_document_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            request_item_id INTEGER,
            requested_item TEXT,
            item_type TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            notes TEXT,
            related_equipment_serial TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS client_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_order_id INTEGER,
            client_order_no TEXT,
            request_id INTEGER,
            quotation_id INTEGER,
            request_item_id INTEGER,
            requested_item TEXT,
            item_type TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            line_total REAL DEFAULT 0,
            reserved_qty INTEGER DEFAULT 0,
            delivered_qty INTEGER DEFAULT 0,
            invoiced_qty INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_type TEXT,
            item_id INTEGER,
            pn TEXT,
            qty INTEGER,
            old_qty INTEGER,
            new_qty INTEGER,
            request_id INTEGER,
            request_item_id INTEGER,
            delivery_note_id INTEGER,
            document_no TEXT,
            client_name TEXT,
            notes TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_no TEXT UNIQUE,
            client_id INTEGER,
            client_hospital TEXT,
            contact_person TEXT,
            tender_source TEXT,
            status TEXT DEFAULT 'draft',
            technical_offer_no TEXT,
            supplier_po_no TEXT,
            packing_list_url TEXT,
            receiving_status TEXT DEFAULT 'pending',
            installation_status TEXT DEFAULT 'pending',
            acceptance_status TEXT DEFAULT 'pending',
            warranty_status TEXT DEFAULT 'pending',
            invoice_id INTEGER,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_bid_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_id INTEGER,
            equipment_id INTEGER,
            description TEXT,
            manufacturer TEXT,
            model TEXT,
            expected_qty INTEGER DEFAULT 1,
            received_qty INTEGER DEFAULT 0,
            delivered_qty INTEGER DEFAULT 0,
            installed_qty INTEGER DEFAULT 0,
            accepted_qty INTEGER DEFAULT 0,
            serial_numbers TEXT,
            missing_qty INTEGER DEFAULT 0,
            validation_status TEXT DEFAULT 'pending',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_receiving_validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bid_id INTEGER,
            bid_item_id INTEGER,
            equipment_id INTEGER,
            expected_qty INTEGER DEFAULT 0,
            received_qty INTEGER DEFAULT 0,
            missing_qty INTEGER DEFAULT 0,
            serial_numbers TEXT,
            validation_result TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_calibrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            calibration_date TEXT,
            next_due_date TEXT,
            calibrated_by TEXT,
            certificate_attachment TEXT,
            calibration_result TEXT,
            standards_used TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_risk_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER UNIQUE,
            client_id INTEGER,
            risk_level TEXT DEFAULT 'medium',
            life_support INTEGER DEFAULT 0,
            criticality_level TEXT,
            department_risk_level TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_uptime_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            event_type TEXT,
            started_at TEXT,
            ended_at TEXT,
            downtime_hours REAL DEFAULT 0,
            failure_category TEXT,
            recurring_issue INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_recall_notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            notice_type TEXT,
            notice_no TEXT,
            manufacturer TEXT,
            affected_serial_numbers TEXT,
            completion_status TEXT DEFAULT 'open',
            corrective_actions TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_compatibility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            inventory_item_id INTEGER,
            part_no TEXT,
            compatibility_type TEXT,
            description TEXT,
            supplier TEXT,
            substitute_part_no TEXT,
            equivalent_part_no TEXT,
            approved INTEGER DEFAULT 1,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pm_checklist_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_type TEXT,
            manufacturer TEXT,
            model TEXT,
            checklist_items TEXT,
            measurements TEXT,
            engineer_signature_required INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS installation_qualification_forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            bid_id INTEGER,
            site_readiness TEXT,
            installation_checklist TEXT,
            environmental_conditions TEXT,
            networking_power_validation TEXT,
            engineer_signature TEXT,
            customer_signature TEXT,
            status TEXT DEFAULT 'draft',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS acceptance_testing_forms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            bid_id INTEGER,
            functionality TEXT,
            alarms TEXT,
            calibration_verification TEXT,
            electrical_safety TEXT,
            pass_fail_criteria TEXT,
            customer_approval TEXT,
            status TEXT DEFAULT 'draft',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_no TEXT UNIQUE,
            case_type TEXT,
            client_id INTEGER,
            contact_id INTEGER,
            equipment_id INTEGER,
            request_id INTEGER,
            quotation_id INTEGER,
            client_order_id INTEGER,
            purchase_order_id INTEGER,
            delivery_note_id INTEGER,
            invoice_id INTEGER,
            engineer_id INTEGER,
            contract_id INTEGER,
            workflow_state TEXT DEFAULT 'lead',
            status TEXT DEFAULT 'open',
            priority TEXT DEFAULT 'normal',
            created_at TEXT,
            updated_at TEXT,
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS case_workflow_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            state TEXT,
            timestamp TEXT,
            user TEXT,
            notes TEXT,
            metadata TEXT
        )
    """)
    conn.commit()

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(inventory)").fetchall()]
    for col in ["barcode", "photo_url", "lookup_url", "client_id", "client_name", "reserved_qty"]:
        if col not in cols:
            col_type = "INTEGER DEFAULT 0" if col == "reserved_qty" else "TEXT"
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {col} {col_type}")

    tx_cols = [r["name"] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    for col in ["client_order_no", "client_name", "pm_asset_id", "pm_asset_tag"]:
        if col not in tx_cols:
            conn.execute(f"ALTER TABLE transactions ADD COLUMN {col} TEXT")

    pm_asset_cols = [r["name"] for r in conn.execute("PRAGMA table_info(pm_assets)").fetchall()]
    for col in ["engineer", "contact_email", "contract_no", "contract_start_date", "contract_end_date",
                "client_id", "warranty_start", "warranty_end", "warranty_status", "vendor", "warranty_notes",
                "risk_level", "life_support", "criticality_level", "department_risk_level", "total_uptime_hours",
                "total_downtime_hours", "outage_frequency", "operational_percentage", "mtbf_hours",
                "failure_categories", "recurring_issue_flag"]:
        if col not in pm_asset_cols:
            col_type = "REAL DEFAULT 0" if col in {"total_uptime_hours", "total_downtime_hours", "operational_percentage", "mtbf_hours"} else "INTEGER DEFAULT 0" if col in {"life_support", "outage_frequency", "recurring_issue_flag"} else "TEXT"
            conn.execute(f"ALTER TABLE pm_assets ADD COLUMN {col} {col_type}")

    doc_cols = [r["name"] for r in conn.execute("PRAGMA table_info(sales_case_documents)").fetchall()]
    for col in ["source_document_id", "quotation_id", "client_order_id", "delivery_note_id"]:
        if col not in doc_cols:
            conn.execute(f"ALTER TABLE sales_case_documents ADD COLUMN {col} INTEGER")

    co_cols = [r["name"] for r in conn.execute("PRAGMA table_info(client_orders)").fetchall()]
    for col in ["request_id", "quotation_id", "client_id"]:
        if col not in co_cols:
            conn.execute(f"ALTER TABLE client_orders ADD COLUMN {col} INTEGER")

    service_call_cols = [r["name"] for r in conn.execute("PRAGMA table_info(service_calls)").fetchall()]
    for col, col_type in {
        "request_id": "INTEGER",
        "engineer_id": "TEXT",
        "contract_id": "TEXT",
        "invoice_id": "INTEGER",
        "scheduled_at": "TEXT",
        "visit_started_at": "TEXT",
        "visit_completed_at": "TEXT",
        "spare_parts_request": "TEXT",
        "service_report_url": "TEXT",
    }.items():
        if col not in service_call_cols:
            conn.execute(f"ALTER TABLE service_calls ADD COLUMN {col} {col_type}")

    client_cols = [r["name"] for r in conn.execute("PRAGMA table_info(clients)").fetchall()]
    for col, col_type in {
        "phone": "TEXT",
        "financial_status": "TEXT DEFAULT 'good standing'",
        "credit_balance": "REAL DEFAULT 0",
        "last_payment_date": "TEXT",
    }.items():
        if col not in client_cols:
            conn.execute(f"ALTER TABLE clients ADD COLUMN {col} {col_type}")

    po_item_cols = [r["name"] for r in conn.execute("PRAGMA table_info(purchase_order_items)").fetchall()]
    for col in ["request_id", "request_item_id"]:
        if col not in po_item_cols:
            conn.execute(f"ALTER TABLE purchase_order_items ADD COLUMN {col} INTEGER")

    quotation_cols = [r["name"] for r in conn.execute("PRAGMA table_info(quotations)").fetchall()]
    for col in ["request_id", "contact_person"]:
        if col not in quotation_cols:
            col_type = "INTEGER" if col == "request_id" else "TEXT"
            conn.execute(f"ALTER TABLE quotations ADD COLUMN {col} {col_type}")

    po_cols = [r["name"] for r in conn.execute("PRAGMA table_info(purchase_orders)").fetchall()]
    for col in ["client_id", "request_id", "quotation_id", "contract_id", "invoice_id"]:
        if col not in po_cols:
            conn.execute(f"ALTER TABLE purchase_orders ADD COLUMN {col} INTEGER")

    ensure_clients_from_existing_data(conn)
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

def client_key(name: str) -> str:
    return " ".join(str(name or "").strip().lower().split())

def warranty_status(warranty_end: str = "") -> str:
    end = parse_iso_date(warranty_end)
    if not end:
        return "unknown"
    today = date.today()
    if end < today:
        return "expired"
    if end <= today + timedelta(days=45):
        return "expiring_soon"
    return "active"

def ensure_client(conn, name: str, **defaults) -> int | None:
    clean_name = str(name or "").strip()
    if not clean_name:
        return None
    existing = conn.execute("SELECT id FROM clients WHERE lower(trim(name))=lower(trim(?))", (clean_name,)).fetchone()
    if existing:
        return existing["id"]
    cur = conn.execute("""
        INSERT INTO clients
        (name, city, address, main_contact, contact_email, phone, biomedical_department, primary_engineer, status, financial_status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        clean_name,
        defaults.get("city", ""),
        defaults.get("address", ""),
        defaults.get("main_contact", ""),
        defaults.get("contact_email", ""),
        defaults.get("phone", ""),
        defaults.get("biomedical_department", ""),
        defaults.get("primary_engineer", ""),
        defaults.get("status", "active"),
        defaults.get("financial_status", "good standing"),
        defaults.get("notes", "Created from existing ERP activity"),
        now(),
        now(),
    ))
    return cur.lastrowid

def ensure_clients_from_existing_data(conn):
    client_ids = {}
    rows = conn.execute("""
        SELECT hospital AS name, MAX(contact_email) AS contact_email, MAX(engineer) AS primary_engineer
        FROM pm_assets
        WHERE COALESCE(hospital, '') != ''
        GROUP BY hospital
    """).fetchall()
    for row in rows:
        client_ids[client_key(row["name"])] = ensure_client(
            conn,
            row["name"],
            contact_email=row["contact_email"] or "",
            primary_engineer=row["primary_engineer"] or "",
            biomedical_department="Biomedical Engineering",
        )
    for row in conn.execute("SELECT DISTINCT client_name AS name FROM client_orders WHERE COALESCE(client_name, '') != ''").fetchall():
        client_ids[client_key(row["name"])] = ensure_client(conn, row["name"])
    for row in conn.execute("SELECT DISTINCT client_name AS name FROM transactions WHERE COALESCE(client_name, '') != ''").fetchall():
        client_ids[client_key(row["name"])] = ensure_client(conn, row["name"])

    for key, client_id in client_ids.items():
        if client_id:
            conn.execute("UPDATE pm_assets SET client_id=? WHERE lower(trim(COALESCE(hospital, '')))=?", (client_id, key))
            conn.execute("UPDATE inventory SET client_id=?, client_name=(SELECT name FROM clients WHERE id=?) WHERE lower(trim(COALESCE(client_name, '')))=?", (client_id, client_id, key))

def crm_client_row(conn, client_id: int):
    ensure_clients_from_existing_data(conn)
    client = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return dict(client)

def crm_client_metrics(conn, client):
    client_id = client["id"]
    name = client["name"]
    equipment = conn.execute("SELECT COUNT(*) AS c FROM pm_assets WHERE client_id=? OR lower(trim(hospital))=lower(trim(?))", (client_id, name)).fetchone()["c"]
    active_contracts = conn.execute("""
        SELECT COUNT(*) AS c FROM (
            SELECT DISTINCT contract_no FROM pm_assets
            WHERE (client_id=? OR lower(trim(hospital))=lower(trim(?)))
              AND COALESCE(contract_no, '') != ''
              AND (COALESCE(contract_end_date, '') = '' OR contract_end_date >= ?)
        )
    """, (client_id, name, date.today().isoformat())).fetchone()["c"]
    warranty_assets = conn.execute("""
        SELECT warranty_end FROM pm_assets
        WHERE client_id=? OR lower(trim(hospital))=lower(trim(?))
    """, (client_id, name)).fetchall()
    under_warranty = sum(1 for row in warranty_assets if warranty_status(row["warranty_end"]) in {"active", "expiring_soon"})
    warranty_alerts = sum(1 for row in warranty_assets if warranty_status(row["warranty_end"]) in {"expired", "expiring_soon"})
    open_calls = conn.execute("SELECT COUNT(*) AS c FROM service_calls WHERE client_id=? AND lower(COALESCE(status, 'open')) NOT IN ('closed', 'resolved', 'cancelled')", (client_id,)).fetchone()["c"]
    upcoming_pms = conn.execute("""
        SELECT COUNT(*) AS c FROM pm_assets
        WHERE (client_id=? OR lower(trim(hospital))=lower(trim(?)))
          AND COALESCE(next_pm_date, '') >= ?
          AND COALESCE(next_pm_date, '') <= ?
    """, (client_id, name, date.today().isoformat(), (date.today() + timedelta(days=30)).isoformat())).fetchone()["c"]
    total_pm = conn.execute("SELECT COUNT(*) AS c FROM pm_tasks t JOIN pm_assets a ON a.id=t.asset_id WHERE a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))", (client_id, name)).fetchone()["c"]
    completed_pm = conn.execute("SELECT COUNT(*) AS c FROM pm_tasks t JOIN pm_assets a ON a.id=t.asset_id WHERE (a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))) AND lower(t.status)='completed'", (client_id, name)).fetchone()["c"]
    open_quotations = conn.execute("SELECT COUNT(*) AS c FROM quotations WHERE client_id=? AND lower(COALESCE(status, 'draft')) IN ('draft', 'sent')", (client_id,)).fetchone()["c"]
    last_activity = conn.execute("""
        SELECT MAX(activity_at) AS last_activity FROM (
            SELECT updated_at AS activity_at FROM clients WHERE id=?
            UNION ALL SELECT updated_at FROM pm_assets WHERE client_id=? OR lower(trim(hospital))=lower(trim(?))
            UNION ALL SELECT created_at FROM crm_communications WHERE client_id=?
            UNION ALL SELECT updated_at FROM service_calls WHERE client_id=?
            UNION ALL SELECT updated_at FROM quotations WHERE client_id=?
        )
    """, (client_id, client_id, name, client_id, client_id, client_id)).fetchone()["last_activity"]
    return {
        "equipment_count": int(equipment or 0),
        "active_contracts": int(active_contracts or 0),
        "under_warranty": int(under_warranty or 0),
        "warranty_alerts": int(warranty_alerts or 0),
        "open_service_calls": int(open_calls or 0),
        "upcoming_pms": int(upcoming_pms or 0),
        "open_quotations": int(open_quotations or 0),
        "pm_compliance": round((completed_pm / total_pm) * 100) if total_pm else 0,
        "last_activity": last_activity or "",
        "contract_status": "active" if active_contracts else "needs_review",
    }

def classify_offer_status(status: str) -> str:
    text = str(status or "draft").strip().lower()
    if text in {"approved", "accepted", "won"}:
        return "approved"
    if text in {"rejected", "lost", "cancelled"}:
        return "rejected"
    if text in {"expired"}:
        return "expired"
    return "open"

def classify_order_status(status: str) -> str:
    text = str(status or "open").strip().lower()
    if text in {"completed", "closed", "fulfilled"}:
        return "completed"
    if "partial" in text:
        return "partially_fulfilled"
    return "open"

def crm_client_dashboard_data(conn, client_id: int):
    client = crm_client_row(conn, client_id)
    metrics = crm_client_metrics(conn, client)
    contacts = [dict(r) for r in conn.execute("SELECT * FROM crm_contacts WHERE client_id=? ORDER BY name", (client_id,)).fetchall()]
    equipment = [dict(r) for r in conn.execute("""
        SELECT * FROM pm_assets
        WHERE client_id=? OR lower(trim(hospital))=lower(trim(?))
        ORDER BY hospital, department, asset_tag
    """, (client_id, client["name"])).fetchall()]
    for item in equipment:
        item["warranty_status"] = item.get("warranty_status") or warranty_status(item.get("warranty_end", ""))
    offers = [dict(r) for r in conn.execute("SELECT * FROM quotations WHERE client_id=? ORDER BY quote_date DESC, id DESC", (client_id,)).fetchall()]
    docs = [dict(r) for r in conn.execute("SELECT * FROM sales_case_documents WHERE client_id=? ORDER BY created_at DESC, id DESC", (client_id,)).fetchall()]
    requests = [dict(r) for r in conn.execute("""
        SELECT cr.*,
               COUNT(cri.id) AS line_count,
               COALESCE(SUM(cri.quantity * cri.unit_price), 0) AS amount
        FROM customer_requests cr
        LEFT JOIN customer_request_items cri ON cri.request_id=cr.id
        WHERE cr.client_id=?
        GROUP BY cr.id
        ORDER BY cr.updated_at DESC
    """, (client_id,)).fetchall()]
    orders = [dict(r) for r in conn.execute("""
        SELECT * FROM client_orders
        WHERE client_id=? OR lower(trim(client_name))=lower(trim(?))
        ORDER BY updated_at DESC
    """, (client_id, client["name"])).fetchall()]
    service_calls = [dict(r) for r in conn.execute("SELECT * FROM service_calls WHERE client_id=? ORDER BY COALESCE(opened_at, created_at) DESC", (client_id,)).fetchall()]
    equipment_history = [dict(r) for r in conn.execute("""
        SELECT h.*, a.asset_tag, a.serial_number, a.model
        FROM pm_history h
        JOIN pm_assets a ON a.id=h.asset_id
        WHERE a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))
        ORDER BY h.created_at DESC
        LIMIT 50
    """, (client_id, client["name"])).fetchall()]
    engineer_activities = [dict(r) for r in conn.execute("""
        SELECT 'service_call' AS activity_type, call_no AS reference, engineer, status, issue AS notes, updated_at AS activity_at, equipment_id, request_id
        FROM service_calls
        WHERE client_id=?
        UNION ALL
        SELECT 'pm_history' AS activity_type, a.asset_tag AS reference, h.engineer, h.action AS status, h.notes, h.created_at AS activity_at, h.asset_id AS equipment_id, NULL AS request_id
        FROM pm_history h
        JOIN pm_assets a ON a.id=h.asset_id
        WHERE a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))
        ORDER BY activity_at DESC
        LIMIT 50
    """, (client_id, client_id, client["name"])).fetchall()]
    pending_items = [dict(r) for r in conn.execute("""
        SELECT cri.*, cr.case_no, cr.client_hospital
        FROM customer_request_items cri
        JOIN customer_requests cr ON cr.id=cri.request_id
        WHERE cr.client_id=?
          AND (
            COALESCE(cri.reserved_qty,0) > 0
            OR COALESCE(cri.shortage_qty,0) > 0
            OR COALESCE(cri.procurement_status,'') IN ('po_draft','po_sent','supplier_confirmed','partially_received','received')
            OR (COALESCE(cri.procurement_status,'')='received' AND COALESCE(cri.delivered_qty,0) < COALESCE(cri.quantity,0))
          )
        ORDER BY cri.updated_at DESC
    """, (client_id,)).fetchall()]
    invoices = [d for d in docs if d.get("doc_type") == "invoice"]
    paid_invoices = [d for d in invoices if str(d.get("status", "")).lower() == "paid"]
    overdue_invoices = [d for d in invoices if str(d.get("status", "")).lower() == "overdue"]
    unpaid_invoices = [d for d in invoices if str(d.get("status", "")).lower() not in {"paid", "cancelled"}]
    offer_counts = {"all": len(offers), "pro_forma": 0, "approved": 0, "rejected": 0, "expired": 0}
    for doc in docs:
        if doc.get("doc_type") == "pro_forma":
            offer_counts["pro_forma"] += 1
    for offer in offers:
        kind = classify_offer_status(offer.get("status", ""))
        if kind in offer_counts:
            offer_counts[kind] += 1
    request_counts = {
        "all": len(requests),
        "pending": sum(1 for r in requests if str(r.get("status", "")).lower() in {"open", "pending"}),
        "in_progress": sum(1 for r in requests if str(r.get("status", "")).lower() in {"client_order_approved", "in_progress", "partially_invoiced"}),
        "completed": sum(1 for r in requests if str(r.get("status", "")).lower() in {"completed", "invoiced"}),
        "cancelled": sum(1 for r in requests if str(r.get("status", "")).lower() == "cancelled"),
    }
    order_counts = {
        "all": len(orders),
        "open": sum(1 for o in orders if classify_order_status(o.get("status", "")) == "open"),
        "partially_fulfilled": sum(1 for o in orders if classify_order_status(o.get("status", "")) == "partially_fulfilled"),
        "completed": sum(1 for o in orders if classify_order_status(o.get("status", "")) == "completed"),
    }
    financials = {
        "total_unpaid_invoices": round(sum(float(i.get("amount") or 0) for i in unpaid_invoices), 2),
        "overdue_invoices": len(overdue_invoices),
        "paid_invoices": len(paid_invoices),
        "credit_balance": float(client.get("credit_balance") or 0),
        "last_payment_date": client.get("last_payment_date") or "",
        "financial_status": client.get("financial_status") or "good standing",
        "invoices": invoices,
    }
    return {
        "client": {**client, **metrics},
        "contacts": contacts,
        "equipment": equipment,
        "offers": offers,
        "documents": docs,
        "requests": requests,
        "orders": orders,
        "service_calls": service_calls,
        "engineer_activities": engineer_activities,
        "equipment_history": equipment_history,
        "pending_items": pending_items,
        "financials": financials,
        "counts": {
            "offers": offer_counts,
            "requests": request_counts,
            "orders": order_counts,
            "service_open": sum(1 for c in service_calls if str(c.get("status", "")).lower() not in {"closed", "resolved", "cancelled"}),
            "pm_due": sum(1 for e in equipment if pm_timing_status(e.get("next_pm_date", ""), e.get("status", "")) in {"due_today", "due_this_week", "overdue"}),
            "warranty_equipment": sum(1 for e in equipment if warranty_status(e.get("warranty_end", "")) in {"active", "expiring_soon"}),
            "contract_covered_equipment": sum(1 for e in equipment if e.get("contract_no")),
        },
    }

def contract_link_id(hospital: str = "", contract_no: str = "") -> str:
    return f"{(hospital or '').strip()}::{(contract_no or '').strip()}".strip(":")

def after_sales_dashboard_data(conn):
    today = date.today()
    expiring_until = today + timedelta(days=60)
    service_calls = []
    for row in conn.execute("""
        SELECT s.*, c.name AS client_name, a.asset_tag, a.serial_number
        FROM service_calls s
        LEFT JOIN clients c ON c.id=s.client_id
        LEFT JOIN pm_assets a ON a.id=s.equipment_id
        WHERE lower(COALESCE(s.status, 'open')) NOT IN ('closed', 'resolved', 'cancelled')
        ORDER BY COALESCE(s.opened_at, s.created_at) DESC
        LIMIT 20
    """).fetchall():
        item = dict(row)
        item["engineer_id"] = item.get("engineer") or ""
        item["contract_id"] = ""
        service_calls.append(item)

    pm_assets = []
    for row in conn.execute("""
        SELECT a.*, c.name AS client_name
        FROM pm_assets a
        LEFT JOIN clients c ON c.id=a.client_id
        ORDER BY COALESCE(a.next_pm_date, ''), a.hospital, a.asset_tag
    """).fetchall():
        asset = enrich_pm_asset(row)
        asset["equipment_id"] = asset.get("id")
        asset["engineer_id"] = asset.get("engineer") or ""
        asset["contract_id"] = contract_link_id(asset.get("hospital", ""), asset.get("contract_no", ""))
        asset["request_id"] = None
        pm_assets.append(asset)
    pm_due = [a for a in pm_assets if a.get("timing_status") in {"due_today", "due_this_week", "overdue"}]
    warranty_pm = [
        a for a in pm_due
        if warranty_status(a.get("warranty_end", "")) in {"active", "expiring_soon"}
    ]

    contracts = []
    for row in conn.execute("""
        SELECT MIN(a.id) AS equipment_id, a.client_id, a.hospital, a.contract_no,
               MIN(a.contract_start_date) AS contract_start_date,
               MAX(a.contract_end_date) AS contract_end_date,
               COUNT(*) AS equipment_count
        FROM pm_assets a
        WHERE COALESCE(a.contract_no, '') != ''
        GROUP BY a.client_id, a.hospital, a.contract_no
        ORDER BY COALESCE(a.contract_end_date, ''), a.hospital, a.contract_no
        LIMIT 30
    """).fetchall():
        contract = dict(row)
        end = parse_iso_date(contract.get("contract_end_date"))
        if end and end < today:
            status = "expired"
        elif end and end <= expiring_until:
            status = "expiring_soon"
        else:
            status = "active" if end or contract.get("contract_no") else ""
        contract["status"] = status
        contract["contract_id"] = contract_link_id(contract.get("hospital", ""), contract.get("contract_no", ""))
        contract["engineer_id"] = ""
        contract["request_id"] = None
        contracts.append(contract)

    report_rows = []
    for row in conn.execute("""
        SELECT 'service_report' AS report_type, s.id AS source_id, s.client_id, s.equipment_id, s.request_id,
               s.call_no AS title, s.engineer, s.status, s.updated_at
        FROM service_calls s
        WHERE lower(COALESCE(s.status, '')) IN ('closed', 'resolved')
          AND COALESCE(s.resolution, '') = ''
        ORDER BY s.updated_at DESC
        LIMIT 20
    """).fetchall():
        item = dict(row)
        item["engineer_id"] = item.get("engineer") or ""
        item["contract_id"] = ""
        report_rows.append(item)
    for row in conn.execute("""
        SELECT 'pm_report' AS report_type, t.id AS source_id, a.client_id, a.id AS equipment_id, NULL AS request_id,
               t.task_name AS title, COALESCE(t.assigned_to, a.engineer) AS engineer, t.status, t.completed_date AS updated_at,
               a.hospital, a.contract_no
        FROM pm_tasks t
        JOIN pm_assets a ON a.id=t.asset_id
        WHERE lower(COALESCE(t.status, ''))='completed'
          AND COALESCE(t.notes, '') = ''
        ORDER BY t.completed_date DESC
        LIMIT 20
    """).fetchall():
        item = dict(row)
        item["engineer_id"] = item.get("engineer") or ""
        item["contract_id"] = contract_link_id(item.get("hospital", ""), item.get("contract_no", ""))
        report_rows.append(item)

    workload = {}
    for call in service_calls:
        engineer = (call.get("engineer") or "Unassigned").strip() or "Unassigned"
        workload.setdefault(engineer, {"engineer_id": engineer, "engineer": engineer, "open_service_calls": 0, "pm_due": 0, "total": 0})
        workload[engineer]["open_service_calls"] += 1
        workload[engineer]["total"] += 1
    for asset in pm_due:
        engineer = (asset.get("engineer") or "Unassigned").strip() or "Unassigned"
        workload.setdefault(engineer, {"engineer_id": engineer, "engineer": engineer, "open_service_calls": 0, "pm_due": 0, "total": 0})
        workload[engineer]["pm_due"] += 1
        workload[engineer]["total"] += 1

    active_contracts = [c for c in contracts if c.get("status") in {"active", "expiring_soon"}]
    expiring_contracts = [c for c in contracts if c.get("status") == "expiring_soon"]
    return {
        "metrics": {
            "open_service_calls": len(service_calls),
            "pm_visits_due": len(pm_due),
            "active_contracts": len(active_contracts),
            "expiring_contracts": len(expiring_contracts),
            "reports_pending": len(report_rows),
            "engineer_workload": sum(w["total"] for w in workload.values()),
            "warranty_equipment_needing_pm": len(warranty_pm),
        },
        "service_calls": service_calls,
        "pm_due": pm_due[:20],
        "pm_completed": [enrich_pm_asset(r) for r in conn.execute("""
            SELECT a.*, c.name AS client_name
            FROM pm_assets a
            LEFT JOIN clients c ON c.id=a.client_id
            WHERE lower(COALESCE(a.status, ''))='completed'
            ORDER BY a.updated_at DESC
            LIMIT 20
        """).fetchall()],
        "contracts": contracts,
        "reports_pending": report_rows,
        "engineer_workload": sorted(workload.values(), key=lambda item: item["total"], reverse=True),
        "warranty_pm": warranty_pm[:20],
        "submodules": [
            {"name": "Service Calls", "path": "/after-sales/service-calls", "existing_route": "/crm", "description": "Corrective maintenance, labor, spare parts + installation, assignments, statuses, and service history."},
            {"name": "PM Tracking", "path": "/after-sales/pm-tracking", "existing_route": "/pm", "description": "Schedules, due lists, completed PMs, engineer assignment, PM reports, and warranty PM tracking."},
            {"name": "Contracts", "path": "/after-sales/contracts", "existing_route": "/pm/contracts", "description": "Maintenance contracts, warranty contracts, covered equipment, dates, and status."},
            {"name": "Reports", "path": "/after-sales/reports", "existing_route": "/pm/reports", "description": "Service, PM, engineer, client, and equipment history reports."},
        ],
    }

STOCK_ITEM_TYPES = {"spare_part", "accessory", "new_equipment"}
SERVICE_ITEM_TYPES = {"labor", "service", "maintenance_contract"}

def stock_status_for(requested_qty: int, available_qty: int, reserved_qty: int = 0, delivered_qty: int = 0, invoiced_qty: int = 0) -> str:
    if invoiced_qty >= requested_qty and requested_qty > 0:
        return "invoiced"
    if delivered_qty >= requested_qty and requested_qty > 0:
        return "delivered"
    if delivered_qty > 0:
        return "partially_delivered"
    if reserved_qty >= requested_qty and requested_qty > 0:
        return "reserved"
    if reserved_qty > 0:
        return "partially_reserved"
    if available_qty >= requested_qty:
        return "available"
    if available_qty > 0:
        return "partially_available"
    return "unavailable"

def find_inventory_for_request_item(conn, requested_item: str):
    text = (requested_item or "").strip()
    if not text:
        return None
    return conn.execute("""
        SELECT * FROM inventory
        WHERE lower(trim(pn))=lower(trim(?))
           OR lower(trim(barcode))=lower(trim(?))
           OR lower(trim(description))=lower(trim(?))
        ORDER BY physical_qty DESC, id
        LIMIT 1
    """, (text, text, text)).fetchone()

def enrich_case_line(conn, line):
    row = dict(line)
    requested_qty = int(row.get("quantity") or row.get("requested_qty") or 0)
    item_type = (row.get("item_type") or "").strip()
    inv = None
    if item_type in STOCK_ITEM_TYPES:
        inv = conn.execute("SELECT * FROM inventory WHERE id=?", (row.get("inventory_item_id"),)).fetchone() if row.get("inventory_item_id") else find_inventory_for_request_item(conn, row.get("requested_item", ""))
    physical_qty = int(inv["physical_qty"] or 0) if inv else 0
    reserved_qty_total = int(inv["reserved_qty"] or 0) if inv and "reserved_qty" in inv.keys() else 0
    available_qty = max(0, physical_qty - reserved_qty_total)
    line_reserved_qty = int(row.get("reserved_qty") or 0)
    delivered_qty = int(row.get("delivered_qty") or 0)
    invoiced_qty = int(row.get("invoiced_qty") or 0)
    shortage_qty = max(0, requested_qty - available_qty - line_reserved_qty)
    stock_status = "not_stock_item" if item_type not in STOCK_ITEM_TYPES else stock_status_for(requested_qty, available_qty, line_reserved_qty, delivered_qty, invoiced_qty)
    procurement_status = row.get("procurement_status") or "not_ordered"
    if shortage_qty <= 0 and procurement_status == "not_ordered":
        procurement_status = ""
    row.update({
        "inventory_item_id": inv["id"] if inv else row.get("inventory_item_id"),
        "pn": inv["pn"] if inv else row.get("pn", ""),
        "physical_qty": physical_qty,
        "available_qty": available_qty,
        "requested_qty": requested_qty,
        "shortage_qty": shortage_qty if item_type in STOCK_ITEM_TYPES else 0,
        "stock_status": stock_status,
        "procurement_status": procurement_status,
    })
    return row

def sync_case_line_stock(conn, line_id: int):
    line = conn.execute("SELECT * FROM customer_request_items WHERE id=?", (line_id,)).fetchone()
    if not line:
        return None
    data = enrich_case_line(conn, line)
    conn.execute("""
        UPDATE customer_request_items
        SET inventory_item_id=?, pn=?, physical_qty=?, available_qty=?, requested_qty=?,
            shortage_qty=?, stock_status=?, procurement_status=?, updated_at=?
        WHERE id=?
    """, (
        data.get("inventory_item_id"), data.get("pn", ""), data["physical_qty"], data["available_qty"],
        data["requested_qty"], data["shortage_qty"], data["stock_status"], data.get("procurement_status", ""),
        now(), line_id
    ))
    return data

def request_with_lines(conn, request_id: int):
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        raise HTTPException(status_code=404, detail="Customer request not found")
    raw_lines = conn.execute("SELECT * FROM customer_request_items WHERE request_id=? ORDER BY id", (request_id,)).fetchall()
    lines = []
    for line in raw_lines:
        data = sync_case_line_stock(conn, line["id"]) or dict(line)
        lines.append(data)
    docs = []
    for doc in conn.execute("SELECT * FROM sales_case_documents WHERE request_id=? ORDER BY created_at DESC", (request_id,)).fetchall():
        doc_data = dict(doc)
        doc_data["lines"] = [dict(r) for r in conn.execute("SELECT * FROM sales_case_document_lines WHERE document_id=? ORDER BY id", (doc["id"],)).fetchall()]
        docs.append(doc_data)
    return {**dict(req), "lines": lines, "documents": docs}

def make_doc_no(prefix: str, request_id: int) -> str:
    return f"{prefix}-{date.today().strftime('%y%m%d')}-{request_id:04d}"

def create_sales_document(conn, request_id: int, doc_type: str, status: str = "draft", notes: str = "", source_document_id: int | None = None, line_quantities: dict[int, int] | None = None):
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        raise HTTPException(status_code=404, detail="Customer request not found")
    prefix = {
        "quotation": "QT",
        "pro_forma": "PF",
        "client_order": "CO",
        "delivery_note": "DN",
        "invoice": "INV",
    }.get(doc_type, "DOC")
    existing = conn.execute("SELECT * FROM sales_case_documents WHERE request_id=? AND doc_type=? ORDER BY id DESC LIMIT 1", (request_id, doc_type)).fetchone()
    if existing and doc_type not in {"delivery_note", "invoice"}:
        return dict(existing)
    lines = conn.execute("SELECT * FROM customer_request_items WHERE request_id=? ORDER BY id", (request_id,)).fetchall()
    amount = 0
    selected_lines = []
    for line in lines:
        quantity = int(line["quantity"] or 0)
        if line_quantities is not None:
            quantity = int(line_quantities.get(line["id"], 0) or 0)
        if quantity <= 0:
            continue
        line_total = float(line["unit_price"] or 0) * quantity
        amount += line_total
        selected_lines.append((line, quantity, line_total))
    doc_no = make_doc_no(prefix, request_id)
    cur = conn.execute("""
        INSERT INTO sales_case_documents
        (request_id, client_id, doc_type, doc_no, status, source_document_id, amount, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (request_id, req["client_id"], doc_type, doc_no, status, source_document_id, amount, notes, now(), now()))
    document_id = cur.lastrowid
    for line, quantity, line_total in selected_lines:
        conn.execute("""
            INSERT INTO sales_case_document_lines
            (document_id, request_item_id, requested_item, item_type, quantity, unit_price, line_total, notes, related_equipment_serial, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            document_id, line["id"], line["requested_item"], line["item_type"], quantity,
            float(line["unit_price"] or 0), line_total, line["notes"], line["related_equipment_serial"], now()
        ))
    return dict(conn.execute("SELECT * FROM sales_case_documents WHERE id=?", (document_id,)).fetchone())

def latest_sales_document(conn, request_id: int, doc_type: str):
    row = conn.execute("SELECT * FROM sales_case_documents WHERE request_id=? AND doc_type=? ORDER BY id DESC LIMIT 1", (request_id, doc_type)).fetchone()
    return dict(row) if row else None

def reserve_customer_request_stock_in_conn(conn, request_id: int, client_order_id: int | None = None):
    request_with_lines(conn, request_id)
    reserved_total = 0
    lines = conn.execute("SELECT * FROM customer_request_items WHERE request_id=? ORDER BY id", (request_id,)).fetchall()
    for line in lines:
        if line["item_type"] not in STOCK_ITEM_TYPES:
            continue
        data = enrich_case_line(conn, line)
        reserve_qty = min(max(0, data["requested_qty"] - int(line["reserved_qty"] or 0)), data["available_qty"])
        if reserve_qty <= 0:
            sync_case_line_stock(conn, line["id"])
            continue
        inv = conn.execute("SELECT * FROM inventory WHERE id=?", (data["inventory_item_id"],)).fetchone()
        old_reserved = int(inv["reserved_qty"] or 0)
        conn.execute("UPDATE inventory SET reserved_qty=?, updated_at=? WHERE id=?", (old_reserved + reserve_qty, now(), inv["id"]))
        conn.execute("UPDATE customer_request_items SET reserved_qty=reserved_qty+?, updated_at=? WHERE id=?", (reserve_qty, now(), line["id"]))
        if client_order_id:
            conn.execute("""
                UPDATE client_order_items
                SET reserved_qty=reserved_qty+?, updated_at=?
                WHERE client_order_id=? AND request_item_id=?
            """, (reserve_qty, now(), client_order_id, line["id"]))
        audit(conn, inv["id"], "RESERVE_STOCK", old_reserved, old_reserved + reserve_qty, f"Request line {line['id']}")
        sync_case_line_stock(conn, line["id"])
        reserved_total += reserve_qty
    return reserved_total

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
    clients_df = pd.read_sql_query("SELECT * FROM clients ORDER BY name", conn)
    communications_df = pd.read_sql_query("SELECT * FROM crm_communications ORDER BY created_at DESC", conn)
    service_calls_df = pd.read_sql_query("SELECT * FROM service_calls ORDER BY created_at DESC", conn)
    quotations_df = pd.read_sql_query("SELECT * FROM quotations ORDER BY quote_date DESC", conn)
    customer_requests_df = pd.read_sql_query("SELECT * FROM customer_requests ORDER BY updated_at DESC", conn)
    customer_request_items_df = pd.read_sql_query("SELECT * FROM customer_request_items ORDER BY id", conn)
    sales_case_documents_df = pd.read_sql_query("SELECT * FROM sales_case_documents ORDER BY updated_at DESC", conn)
    sales_case_document_lines_df = pd.read_sql_query("SELECT * FROM sales_case_document_lines ORDER BY document_id, id", conn)
    client_order_items_df = pd.read_sql_query("SELECT * FROM client_order_items ORDER BY client_order_id, id", conn)
    stock_movements_df = pd.read_sql_query("SELECT * FROM stock_movements ORDER BY created_at DESC", conn)
    equipment_bids_df = pd.read_sql_query("SELECT * FROM equipment_bids ORDER BY updated_at DESC", conn)
    equipment_bid_items_df = pd.read_sql_query("SELECT * FROM equipment_bid_items ORDER BY bid_id, id", conn)
    equipment_receiving_df = pd.read_sql_query("SELECT * FROM equipment_receiving_validations ORDER BY updated_at DESC", conn)
    calibrations_df = pd.read_sql_query("SELECT * FROM equipment_calibrations ORDER BY updated_at DESC", conn)
    risk_profiles_df = pd.read_sql_query("SELECT * FROM equipment_risk_profiles ORDER BY updated_at DESC", conn)
    uptime_df = pd.read_sql_query("SELECT * FROM equipment_uptime_events ORDER BY updated_at DESC", conn)
    recalls_df = pd.read_sql_query("SELECT * FROM equipment_recall_notices ORDER BY updated_at DESC", conn)
    compatibility_df = pd.read_sql_query("SELECT * FROM equipment_compatibility ORDER BY updated_at DESC", conn)
    checklist_templates_df = pd.read_sql_query("SELECT * FROM pm_checklist_templates ORDER BY updated_at DESC", conn)
    iq_forms_df = pd.read_sql_query("SELECT * FROM installation_qualification_forms ORDER BY updated_at DESC", conn)
    acceptance_forms_df = pd.read_sql_query("SELECT * FROM acceptance_testing_forms ORDER BY updated_at DESC", conn)
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
        clients_df.to_excel(writer, sheet_name="CRM_CLIENTS", index=False)
        communications_df.to_excel(writer, sheet_name="CRM_COMMUNICATIONS", index=False)
        service_calls_df.to_excel(writer, sheet_name="SERVICE_CALLS", index=False)
        quotations_df.to_excel(writer, sheet_name="QUOTATIONS", index=False)
        customer_requests_df.to_excel(writer, sheet_name="CUSTOMER_REQUESTS", index=False)
        customer_request_items_df.to_excel(writer, sheet_name="CUSTOMER_REQUEST_ITEMS", index=False)
        sales_case_documents_df.to_excel(writer, sheet_name="SALES_CASE_DOCUMENTS", index=False)
        sales_case_document_lines_df.to_excel(writer, sheet_name="SALES_CASE_DOC_LINES", index=False)
        client_order_items_df.to_excel(writer, sheet_name="CLIENT_ORDER_ITEMS", index=False)
        stock_movements_df.to_excel(writer, sheet_name="STOCK_MOVEMENTS", index=False)
        equipment_bids_df.to_excel(writer, sheet_name="EQUIPMENT_BIDS", index=False)
        equipment_bid_items_df.to_excel(writer, sheet_name="EQUIPMENT_BID_ITEMS", index=False)
        equipment_receiving_df.to_excel(writer, sheet_name="RECEIVING_VALIDATION", index=False)
        calibrations_df.to_excel(writer, sheet_name="CALIBRATION_HISTORY", index=False)
        risk_profiles_df.to_excel(writer, sheet_name="RISK_PROFILES", index=False)
        uptime_df.to_excel(writer, sheet_name="UPTIME_MTBF", index=False)
        recalls_df.to_excel(writer, sheet_name="FDA_FMI_RECALLS", index=False)
        compatibility_df.to_excel(writer, sheet_name="COMPATIBILITY", index=False)
        checklist_templates_df.to_excel(writer, sheet_name="PM_CHECKLIST_TEMPLATES", index=False)
        iq_forms_df.to_excel(writer, sheet_name="INSTALLATION_QUAL", index=False)
        acceptance_forms_df.to_excel(writer, sheet_name="ACCEPTANCE_TESTS", index=False)
        audit_df.to_excel(writer, sheet_name="AUDIT_TRAIL", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for column_cells in ws.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                ws.column_dimensions[column_cells[0].column_letter].width = min(length + 4, 55)

def safe_filename(value: str) -> str:
    clean = "".join(ch for ch in str(value or "document") if ch.isalnum() or ch in "-_")
    return clean or "document"

def document_html(title: str, rows: list[dict], notes: str = "") -> str:
    columns = sorted({key for row in rows for key in row.keys()}) if rows else ["message"]
    body = rows or [{"message": "No rows available"}]
    head = "".join(f"<th>{html_module.escape(str(col))}</th>" for col in columns)
    table_rows = ""
    for row in body:
        table_rows += "<tr>" + "".join(f"<td>{html_module.escape(str(row.get(col, '')))}</td>" for col in columns) + "</tr>"
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>{html_module.escape(title)}</title>
    <style>body{{font-family:Arial,sans-serif;margin:32px;color:#1f2937}}h1{{color:#1f4e78}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #d0d7de;padding:8px;text-align:left;font-size:12px}}th{{background:#eef6ff}}.notes{{margin:16px 0;color:#475569}}@media print{{button{{display:none}}}}</style></head>
    <body><button onclick='window.print()'>Print</button><h1>{html_module.escape(title)}</h1><div class='notes'>{html_module.escape(notes or '')}</div><table><thead><tr>{head}</tr></thead><tbody>{table_rows}</tbody></table></body></html>"""

def minimal_pdf_bytes(title: str, rows: list[dict], notes: str = "") -> bytes:
    lines = [title, notes, ""]
    for row in rows[:40]:
        lines.append(" | ".join(f"{k}: {v}" for k, v in row.items()))
    text = "\\n".join(lines).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 11 Tf 40 780 Td 14 TL ({text}) Tj ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(stream.encode('latin-1', 'ignore'))} >> stream\n{stream}\nendstream endobj",
    ]
    content = "%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(content.encode("latin-1")))
        content += obj + "\n"
    xref_at = len(content.encode("latin-1"))
    content += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        content += f"{offset:010d} 00000 n \n"
    content += f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF"
    return content.encode("latin-1", "ignore")

def export_rows_response(title: str, rows: list[dict], fmt: str = "excel", notes: str = ""):
    fmt = (fmt or "excel").lower()
    filename = safe_filename(title)
    if fmt in {"print", "html", "printable"}:
        return HTMLResponse(document_html(title, rows, notes))
    if fmt == "pdf":
        return StreamingResponse(io.BytesIO(minimal_pdf_bytes(title, rows, notes)), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}.pdf"})
    path = DATA_DIR / f"{filename}.xlsx"
    pd.DataFrame(rows or [{"message": "No rows available"}]).to_excel(path, index=False)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=path.name)

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
        request.session["role"] = APP_ROLE
        return RedirectResponse(url="/portal", status_code=303)
    return RedirectResponse(url="/login?error=Invalid%20credentials", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/portal")
def portal():
    return FileResponse(BASE_DIR / "static" / "portal.html")

@app.get("/dashboard")
def dashboard_page():
    return FileResponse(BASE_DIR / "static" / "portal.html")

@app.get("/inventory")
def inventory_page():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/procurement")
def procurement_page():
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/sales")
@app.get("/sales/{section:path}")
def sales_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "sales.html")

@app.get("/equipment-registry")
@app.get("/equipment-registry/{section:path}")
def equipment_registry_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/financials")
def financials_page():
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/reports")
def reports_page():
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/admin")
def admin_page():
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/crm")
def crm_page():
    return FileResponse(BASE_DIR / "static" / "crm.html")

@app.get("/crm/client/{client_id}")
@app.get("/crm/client/{client_id}/{section:path}")
def crm_client_page(client_id: int, section: str = ""):
    return FileResponse(BASE_DIR / "static" / "crm_client.html")

@app.get("/sales-cases")
def sales_cases_page():
    return RedirectResponse(url="/sales", status_code=303)

@app.get("/after-sales")
@app.get("/after-sales/{section:path}")
def after_sales_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "after_sales.html")

@app.get("/pm")
@app.get("/pm/")
@app.get("/pm/{path:path}")
def pm_page(path: str = ""):
    return FileResponse(BASE_DIR / "static" / "pm" / "index.html")


@app.get("/api/crm/clients")
def crm_clients(q: str = "", city: str = "", contract_status: str = "", engineer: str = "", status: str = ""):
    conn = db()
    ensure_clients_from_existing_data(conn)
    conn.commit()
    rows = [dict(r) for r in conn.execute("SELECT * FROM clients ORDER BY name").fetchall()]
    result = []
    for client in rows:
        metrics = crm_client_metrics(conn, client)
        row = {**client, **metrics}
        matches = True
        if q:
            text = " ".join(str(row.get(k, "")) for k in ["name", "city", "address", "main_contact", "primary_engineer"]).lower()
            matches = q.lower() in text
        if city and city.lower() not in str(row.get("city", "")).lower():
            matches = False
        if contract_status and row.get("contract_status") != contract_status:
            matches = False
        if engineer and engineer.lower() not in str(row.get("primary_engineer", "")).lower():
            matches = False
        if status and row.get("status") != status:
            matches = False
        if matches:
            result.append(row)
    conn.close()
    return result

@app.post("/api/crm/clients")
def create_crm_client(client: CRMClient, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    client_id = ensure_client(
        conn,
        client.name,
        city=client.city,
        address=client.address,
        main_contact=client.main_contact,
        contact_email=client.contact_email,
        phone=client.phone,
        biomedical_department=client.biomedical_department,
        primary_engineer=client.primary_engineer,
        status=client.status,
        financial_status=client.financial_status,
        notes=client.notes,
    )
    conn.commit()
    conn.close()
    return {"id": client_id, "message": "client saved"}

@app.get("/api/crm/client/{client_id}")
def crm_client_detail(client_id: int, request: Request):
    conn = db()
    client = crm_client_row(conn, client_id)
    metrics = crm_client_metrics(conn, client)
    conn.commit()
    conn.close()
    return {**client, **metrics, "role": current_role(request), "can_edit": can_edit_crm(current_role(request))}

@app.get("/api/crm/client/{client_id}/dashboard")
def crm_client_dashboard(client_id: int):
    conn = db()
    data = crm_client_dashboard_data(conn, client_id)
    conn.close()
    return data

@app.get("/api/after-sales/dashboard")
def after_sales_dashboard():
    conn = db()
    ensure_clients_from_existing_data(conn)
    conn.commit()
    data = after_sales_dashboard_data(conn)
    conn.close()
    return data

@app.get("/api/crm/client/{client_id}/equipment")
def crm_client_equipment(client_id: int, q: str = "", warranty: str = "", pm_status: str = ""):
    conn = db()
    client = crm_client_row(conn, client_id)
    rows = [enrich_pm_asset(r) for r in conn.execute("""
        SELECT * FROM pm_assets
        WHERE client_id=? OR lower(trim(hospital))=lower(trim(?))
        ORDER BY department, asset_tag
    """, (client_id, client["name"])).fetchall()]
    result = []
    for row in rows:
        row["equipment"] = row.get("asset_tag") or row.get("model") or "Equipment"
        row["warranty_status"] = row.get("warranty_status") or warranty_status(row.get("warranty_end"))
        if q:
            text = " ".join(str(row.get(k, "")) for k in ["asset_tag", "serial_number", "manufacturer", "model", "department", "engineer"]).lower()
            if q.lower() not in text:
                continue
        if warranty and row["warranty_status"] != warranty:
            continue
        if pm_status and row["timing_status"] != pm_status:
            continue
        result.append(row)
    conn.close()
    return result

@app.get("/api/crm/client/{client_id}/contracts")
def crm_client_contracts(client_id: int):
    conn = db()
    client = crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("""
        SELECT contract_no, MIN(contract_start_date) AS contract_start_date,
               MAX(contract_end_date) AS contract_end_date, COUNT(*) AS equipment_count,
               GROUP_CONCAT(asset_tag, ', ') AS equipment
        FROM pm_assets
        WHERE (client_id=? OR lower(trim(hospital))=lower(trim(?)))
          AND COALESCE(contract_no, '') != ''
        GROUP BY contract_no
        ORDER BY contract_end_date, contract_no
    """, (client_id, client["name"])).fetchall()]
    today = date.today().isoformat()
    for row in rows:
        end = row.get("contract_end_date") or ""
        row["status"] = "active" if not end or end >= today else "expired"
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/pm")
def crm_client_pm(client_id: int):
    conn = db()
    client = crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("""
        SELECT t.*, a.asset_tag, a.hospital, a.department, a.model, a.serial_number
        FROM pm_tasks t
        JOIN pm_assets a ON a.id=t.asset_id
        WHERE a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))
        ORDER BY COALESCE(t.due_date, ''), t.status
    """, (client_id, client["name"])).fetchall()]
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/offers")
def crm_client_offers(client_id: int):
    conn = db()
    crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("SELECT * FROM quotations WHERE client_id=? ORDER BY quote_date DESC, id DESC", (client_id,)).fetchall()]
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/customer-requests")
def crm_client_customer_requests(client_id: int):
    conn = db()
    crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("""
        SELECT cr.*,
               COUNT(cri.id) AS line_count,
               COALESCE(SUM(cri.quantity * cri.unit_price), 0) AS amount
        FROM customer_requests cr
        LEFT JOIN customer_request_items cri ON cri.request_id=cr.id
        WHERE cr.client_id=?
        GROUP BY cr.id
        ORDER BY cr.updated_at DESC
    """, (client_id,)).fetchall()]
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/service-calls")
def crm_client_service_calls(client_id: int):
    conn = db()
    crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("SELECT * FROM service_calls WHERE client_id=? ORDER BY COALESCE(opened_at, created_at) DESC", (client_id,)).fetchall()]
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/contacts")
def crm_client_contacts(client_id: int):
    conn = db()
    client = crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("SELECT * FROM crm_contacts WHERE client_id=? ORDER BY name", (client_id,)).fetchall()]
    if not rows and (client.get("main_contact") or client.get("contact_email")):
        rows = [{
            "id": "",
            "client_id": client_id,
            "name": client.get("main_contact") or "Main contact",
            "role": client.get("biomedical_department") or "Biomedical department",
            "email": client.get("contact_email") or "",
            "phone": "",
            "notes": "Primary CRM contact placeholder",
        }]
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/communications")
def crm_client_communications(client_id: int):
    conn = db()
    crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("SELECT * FROM crm_communications WHERE client_id=? ORDER BY created_at DESC", (client_id,)).fetchall()]
    conn.close()
    return rows

@app.post("/api/crm/client/{client_id}/communications")
def create_crm_communication(client_id: int, entry: CRMCommunication, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    crm_client_row(conn, client_id)
    cur = conn.execute("""
        INSERT INTO crm_communications (client_id, type, user, note, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, entry.type, entry.user or request.session.get("username", role), entry.note, now()))
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "message": "communication added"}

@app.post("/api/cases")
def create_case(case: CaseCreate):
    conn = db()
    case_no = f"CASE-{int(datetime.now().timestamp())}"
    import json
    cur = conn.execute("""
        INSERT INTO cases (case_no, case_type, client_id, contact_id, equipment_id, request_id,
                          quotation_id, client_order_id, purchase_order_id, delivery_note_id,
                          invoice_id, engineer_id, contract_id, priority, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_no, case.case_type, case.client_id, case.contact_id, case.equipment_id, case.request_id,
          case.quotation_id, case.client_order_id, case.purchase_order_id, case.delivery_note_id,
          case.invoice_id, case.engineer_id, case.contract_id, case.priority, case.notes, now(), now()))
    case_id = cur.lastrowid
    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, "lead", now(), "system", "Case created"))
    conn.commit()
    conn.close()
    return {"id": case_id, "case_no": case_no, "message": "Case created successfully"}

@app.get("/api/cases")
def list_cases(case_type: str = "", client_id: int | None = None):
    conn = db()
    where = "WHERE 1=1"
    params = []
    if case_type:
        where += " AND case_type = ?"
        params.append(case_type)
    if client_id:
        where += " AND client_id = ?"
        params.append(client_id)
    rows = conn.execute(f"""
        SELECT id, case_no, case_type, client_id, workflow_state, status, priority, created_at, updated_at
        FROM cases {where} ORDER BY created_at DESC
    """, params).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result

@app.get("/api/cases/{case_id}")
def get_case(case_id: int):
    conn = db()
    case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")
    case_data = dict(case_row)
    states = [dict(r) for r in conn.execute(
        "SELECT state, timestamp, user, notes FROM case_workflow_states WHERE case_id = ? ORDER BY timestamp DESC",
        (case_id,)
    ).fetchall()]
    case_data["workflow_history"] = states
    conn.close()
    return case_data

@app.put("/api/cases/{case_id}")
def update_case(case_id: int, update: CaseUpdate):
    conn = db()
    case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")
    updates = []
    params = []
    if update.status is not None:
        updates.append("status = ?")
        params.append(update.status)
    if update.workflow_state is not None:
        updates.append("workflow_state = ?")
        params.append(update.workflow_state)
    if update.priority is not None:
        updates.append("priority = ?")
        params.append(update.priority)
    if update.notes is not None:
        updates.append("notes = ?")
        params.append(update.notes)
    if update.equipment_id is not None:
        updates.append("equipment_id = ?")
        params.append(update.equipment_id)
    if update.engineer_id is not None:
        updates.append("engineer_id = ?")
        params.append(update.engineer_id)
    if updates:
        updates.append("updated_at = ?")
        params.append(now())
        params.append(case_id)
        conn.execute(f"UPDATE cases SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return {"message": "Case updated successfully"}

@app.post("/api/cases/{case_id}/workflow-state")
def transition_case_state(case_id: int, state_change: CaseWorkflowStateIn):
    conn = db()
    case_row = conn.execute("SELECT workflow_state FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")
    import json
    metadata_json = json.dumps(state_change.metadata) if state_change.metadata else None
    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (case_id, state_change.state, now(), state_change.user, state_change.notes, metadata_json))
    conn.execute("UPDATE cases SET workflow_state = ?, updated_at = ? WHERE id = ?",
                 (state_change.state, now(), case_id))
    conn.commit()
    conn.close()
    return {"message": "Workflow state updated", "new_state": state_change.state}

@app.get("/api/customer-requests")
def list_customer_requests(q: str = ""):
    conn = db()
    where = ""
    params = []
    if q.strip():
        where = "WHERE case_no LIKE ? OR client_hospital LIKE ? OR contact_person LIKE ? OR request_source LIKE ?"
        like = f"%{q.strip()}%"
        params = [like, like, like, like]
    rows = [request_with_lines(conn, r["id"]) for r in conn.execute(f"SELECT id FROM customer_requests {where} ORDER BY updated_at DESC", params).fetchall()]
    conn.commit()
    conn.close()
    return rows

@app.post("/api/customer-requests")
def create_customer_request(payload: CustomerRequestIn, request: Request):
    if not payload.client_hospital.strip():
        raise HTTPException(status_code=400, detail="client/hospital is required")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="At least one requested item is required")
    conn = db()
    client_id = ensure_client(conn, payload.client_hospital.strip(), main_contact=payload.contact_person)
    cur = conn.execute("""
        INSERT INTO customer_requests (case_no, client_id, client_hospital, contact_person, request_source, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("PENDING", client_id, payload.client_hospital.strip(), payload.contact_person, payload.request_source, "open", payload.notes, now(), now()))
    request_id = cur.lastrowid
    case_no = make_doc_no("CASE", request_id)
    conn.execute("UPDATE customer_requests SET case_no=? WHERE id=?", (case_no, request_id))

    case_type = "spare_parts_sale"
    for line in payload.lines:
        if line.item_type == "new_equipment":
            case_type = "equipment_delivery"
            break
        elif line.item_type == "labor":
            case_type = "corrective_maintenance"
            break

    case_cur = conn.execute("""
        INSERT INTO cases (case_no, case_type, client_id, request_id, status, workflow_state, created_at, updated_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_no, case_type, client_id, request_id, "open", "lead", now(), now(), payload.notes))
    case_id = case_cur.lastrowid
    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, "lead", now(), "system", f"Customer request {case_no} created"))

    for line in payload.lines:
        if not line.requested_item.strip():
            continue
        if int(line.quantity or 0) <= 0:
            raise HTTPException(status_code=400, detail="Line quantities must be positive")
        inv = find_inventory_for_request_item(conn, line.requested_item) if line.item_type in STOCK_ITEM_TYPES else None
        cur_line = conn.execute("""
            INSERT INTO customer_request_items
            (request_id, requested_item, item_type, quantity, unit_price, notes, related_equipment_serial,
             inventory_item_id, pn, procurement_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request_id, line.requested_item.strip(), line.item_type, int(line.quantity), float(line.unit_price or 0),
            line.notes, line.related_equipment_serial, inv["id"] if inv else None, inv["pn"] if inv else "",
            "not_ordered", now(), now()
        ))
        sync_case_line_stock(conn, cur_line.lastrowid)
    conn.execute("""
        INSERT INTO crm_communications (client_id, type, user, note, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, "customer_request", request.session.get("username", current_role(request)), f"Created {case_no}", now()))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.get("/api/customer-requests/{request_id}")
def get_customer_request(request_id: int):
    conn = db()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    return data

@app.post("/api/customer-requests/{request_id}/generate/{doc_type}")
def generate_customer_request_document(request_id: int, doc_type: str):
    if doc_type not in {"quotation", "pro_forma"}:
        raise HTTPException(status_code=400, detail="Only quotation or pro_forma generation is allowed here")
    conn = db()
    doc = create_sales_document(conn, request_id, doc_type, "draft", "Generated from Customer Request")
    if doc_type == "quotation":
        req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
        conn.execute("""
            INSERT INTO quotations (client_id, equipment_id, service_call_id, quotation_no, quote_date, status, amount, notes, created_at, updated_at, request_id, contact_person)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (req["client_id"], None, None, doc["doc_no"], date.today().isoformat(), "draft", doc["amount"], f"Linked to {req['case_no']}", now(), now(), request_id, req["contact_person"]))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/convert-client-order")
def convert_customer_request_to_order(request_id: int):
    conn = db()
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        raise HTTPException(status_code=404, detail="Customer request not found")
    quotation = latest_sales_document(conn, request_id, "quotation")
    if not quotation:
        quotation = create_sales_document(conn, request_id, "quotation", "approved", "Auto-generated approved quotation before client order")
    else:
        conn.execute("UPDATE sales_case_documents SET status=?, updated_at=? WHERE id=?", ("approved", now(), quotation["id"]))
        conn.execute("UPDATE quotations SET status=?, updated_at=? WHERE quotation_no=?", ("approved", now(), quotation["doc_no"]))
    doc = create_sales_document(conn, request_id, "client_order", "approved", "Converted from approved quotation", quotation["id"])
    conn.execute("""
        INSERT INTO client_orders (client_order_no, client_name, status, expected_date, notes, created_at, updated_at, request_id, quotation_id, client_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(client_order_no) DO UPDATE SET status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at, request_id=excluded.request_id, quotation_id=excluded.quotation_id, client_id=excluded.client_id
    """, (doc["doc_no"], req["client_hospital"], "APPROVED", "", f"Linked to {req['case_no']} and quotation {quotation['doc_no']}", now(), now(), request_id, quotation["id"], req["client_id"]))
    client_order_row = conn.execute("SELECT * FROM client_orders WHERE client_order_no=?", (doc["doc_no"],)).fetchone()
    existing_lines = conn.execute("SELECT COUNT(*) AS c FROM client_order_items WHERE client_order_id=?", (client_order_row["id"],)).fetchone()["c"]
    if not existing_lines:
        for line in conn.execute("SELECT * FROM customer_request_items WHERE request_id=? ORDER BY id", (request_id,)).fetchall():
            conn.execute("""
                INSERT INTO client_order_items
                (client_order_id, client_order_no, request_id, quotation_id, request_item_id, requested_item, item_type,
                 quantity, unit_price, line_total, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                client_order_row["id"], doc["doc_no"], request_id, quotation["id"], line["id"], line["requested_item"],
                line["item_type"], int(line["quantity"] or 0), float(line["unit_price"] or 0),
                int(line["quantity"] or 0) * float(line["unit_price"] or 0), line["notes"], now(), now()
            ))
    conn.execute("UPDATE sales_case_documents SET client_order_id=?, quotation_id=?, updated_at=? WHERE id=?", (client_order_row["id"], quotation["id"], now(), doc["id"]))
    service_lines = conn.execute("SELECT * FROM customer_request_items WHERE request_id=? AND item_type IN ('labor','service','maintenance_contract')", (request_id,)).fetchall()
    for line in service_lines:
        call_no = make_doc_no("ST", request_id) + f"-{line['id']}"
        conn.execute("""
            INSERT INTO service_calls (client_id, equipment_id, request_id, call_no, status, engineer, issue, resolution, opened_at, closed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (req["client_id"], None, request_id, call_no, "open", "", f"{line['item_type']}: {line['requested_item']}", "", now(), "", now(), now()))
    conn.execute("UPDATE customer_requests SET status=?, updated_at=? WHERE id=?", ("client_order_approved", now(), request_id))
    conn.commit()
    reserve_customer_request_stock_in_conn(conn, request_id, client_order_row["id"])
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/reserve-stock")
def reserve_customer_request_stock(request_id: int):
    conn = db()
    client_order = latest_sales_document(conn, request_id, "client_order")
    reserve_customer_request_stock_in_conn(conn, request_id, client_order.get("client_order_id") if client_order else None)
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/create-po-missing")
def create_po_for_missing_items(request_id: int):
    conn = db()
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        raise HTTPException(status_code=404, detail="Customer request not found")
    po_no = make_doc_no("PO", request_id)
    conn.execute("""
        INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(po_no) DO UPDATE SET updated_at=excluded.updated_at
    """, (po_no, "", "DRAFT", "", f"Missing items for {req['case_no']}", now(), now()))
    for line in conn.execute("SELECT * FROM customer_request_items WHERE request_id=?", (request_id,)).fetchall():
        data = sync_case_line_stock(conn, line["id"]) or dict(line)
        if data.get("shortage_qty", 0) <= 0:
            continue
        if line["linked_purchase_order"]:
            continue
        conn.execute("""
            INSERT INTO purchase_order_items
            (po_no, pn, description, qty, received_qty, location, barcode, device_family, notes, received, created_at, updated_at, request_id, request_item_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (po_no, data.get("pn") or data["requested_item"], data["requested_item"], data["shortage_qty"], 0, "", "", "", f"Linked to {req['case_no']} line {line['id']}", 0, now(), now(), request_id, line["id"]))
        conn.execute("UPDATE customer_request_items SET linked_purchase_order=?, procurement_status=?, updated_at=? WHERE id=?", (po_no, "po_draft", now(), line["id"]))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/receive-po-items")
def receive_customer_request_po_items(request_id: int):
    conn = db()
    po_numbers = [r["linked_purchase_order"] for r in conn.execute("SELECT DISTINCT linked_purchase_order FROM customer_request_items WHERE request_id=? AND COALESCE(linked_purchase_order,'')!=''", (request_id,)).fetchall()]
    received = 0
    for po_no in po_numbers:
        received += receive_purchase_order(conn, po_no)
        conn.execute("UPDATE purchase_orders SET status=?, updated_at=? WHERE po_no=?", ("RECEIVED", now(), po_no))
    for line in conn.execute("SELECT * FROM customer_request_items WHERE request_id=? AND COALESCE(linked_purchase_order,'')!=''", (request_id,)).fetchall():
        po_summary = conn.execute("""
            SELECT COALESCE(SUM(qty),0) AS ordered_qty, COALESCE(SUM(received_qty),0) AS received_qty
            FROM purchase_order_items
            WHERE request_item_id=?
        """, (line["id"],)).fetchone()
        ordered_qty = int(po_summary["ordered_qty"] or 0)
        received_qty = int(po_summary["received_qty"] or 0)
        if ordered_qty and received_qty >= ordered_qty:
            procurement_status = "received"
        elif received_qty > 0:
            procurement_status = "partially_received"
        else:
            procurement_status = line["procurement_status"] or "po_draft"
        conn.execute("UPDATE customer_request_items SET procurement_status=?, updated_at=? WHERE id=?", (procurement_status, now(), line["id"]))
        sync_case_line_stock(conn, line["id"])
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"received": received, "request": data}

@app.post("/api/customer-requests/{request_id}/delivery-note")
def create_customer_request_delivery_note(request_id: int, selection: DeliverySelection | None = None):
    conn = db()
    quantities = {}
    if selection and selection.quantities:
        quantities = {int(k): int(v or 0) for k, v in selection.quantities.items()}
    else:
        for line in conn.execute("SELECT * FROM customer_request_items WHERE request_id=?", (request_id,)).fetchall():
            remaining = int(line["quantity"] or 0) - int(line["delivered_qty"] or 0)
            if remaining <= 0:
                continue
            ready_qty = int(line["reserved_qty"] or 0) if line["item_type"] in STOCK_ITEM_TYPES else remaining
            if ready_qty > 0:
                quantities[line["id"]] = min(remaining, ready_qty)
    if not quantities:
        conn.close()
        raise HTTPException(status_code=400, detail="No selected items are ready for delivery")
    client_order = latest_sales_document(conn, request_id, "client_order")
    doc = create_sales_document(conn, request_id, "delivery_note", "draft", "Delivery note generated for selected ready items", client_order["id"] if client_order else None, quantities)
    conn.execute("UPDATE sales_case_documents SET client_order_id=?, updated_at=? WHERE id=?", (client_order.get("client_order_id") if client_order else None, now(), doc["id"]))
    conn.execute("UPDATE customer_request_items SET linked_delivery_note=COALESCE(NULLIF(linked_delivery_note,''), ?), updated_at=? WHERE request_id=? AND id IN (%s)" % ",".join("?" for _ in quantities), (doc["doc_no"], now(), request_id, *quantities.keys()))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/remove-from-stock")
def remove_customer_request_from_stock(request_id: int, selection: DeliverySelection | None = None):
    conn = db()
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer request not found")
    if selection and selection.quantities:
        create_customer_request_delivery_note(request_id, selection)
        conn = db()
    doc = latest_sales_document(conn, request_id, "delivery_note")
    if not doc:
        conn.close()
        create_customer_request_delivery_note(request_id)
        conn = db()
        doc = latest_sales_document(conn, request_id, "delivery_note")
    doc_lines = conn.execute("SELECT * FROM sales_case_document_lines WHERE document_id=? ORDER BY id", (doc["id"],)).fetchall()
    if not doc_lines:
        conn.close()
        raise HTTPException(status_code=400, detail="Delivery note has no selected items")
    for doc_line in doc_lines:
        line = conn.execute("SELECT * FROM customer_request_items WHERE id=?", (doc_line["request_item_id"],)).fetchone()
        if not line:
            continue
        qty = min(int(doc_line["quantity"] or 0), int(line["quantity"] or 0) - int(line["delivered_qty"] or 0))
        if qty <= 0:
            continue
        if line["item_type"] not in STOCK_ITEM_TYPES:
            conn.execute("UPDATE customer_request_items SET delivered_qty=delivered_qty+?, linked_delivery_note=?, updated_at=? WHERE id=?", (qty, doc["doc_no"], now(), line["id"]))
            continue
        if line["item_type"] not in STOCK_ITEM_TYPES:
            continue
        data = sync_case_line_stock(conn, line["id"]) or dict(line)
        qty = min(qty, int(line["reserved_qty"] or 0))
        if qty <= 0:
            continue
        inv = conn.execute("SELECT * FROM inventory WHERE id=?", (data["inventory_item_id"],)).fetchone()
        old_qty = int(inv["physical_qty"] or 0)
        old_reserved = int(inv["reserved_qty"] or 0)
        new_qty = max(0, old_qty - qty)
        new_reserved = max(0, old_reserved - qty)
        conn.execute("UPDATE inventory SET physical_qty=?, reserved_qty=?, difference=?, status=?, updated_at=? WHERE id=?", (new_qty, new_reserved, new_qty - int(inv["system_qty"] or 0), compute_status(int(inv["system_qty"] or 0), new_qty), now(), inv["id"]))
        conn.execute("UPDATE customer_request_items SET delivered_qty=delivered_qty+?, reserved_qty=max(0,reserved_qty-?), linked_delivery_note=?, updated_at=? WHERE id=?", (qty, qty, doc["doc_no"], now(), line["id"]))
        conn.execute("""
            INSERT INTO transactions (item_id, pn, barcode, direction, qty, old_qty, new_qty, purchase_order_no, client_order_no, client_name, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (inv["id"], inv["pn"], inv["barcode"], "OUT", qty, old_qty, new_qty, "", "", req["client_hospital"], f"Delivered for {req['case_no']} via {doc['doc_no']}", now()))
        conn.execute("""
            INSERT INTO stock_movements
            (movement_type, item_id, pn, qty, old_qty, new_qty, request_id, request_item_id, delivery_note_id, document_no, client_name, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("OUT", inv["id"], inv["pn"], qty, old_qty, new_qty, request_id, line["id"], doc["id"], doc["doc_no"], req["client_hospital"], "Delivery note stock removal", now()))
        if doc.get("client_order_id"):
            conn.execute("""
                UPDATE client_order_items
                SET delivered_qty=delivered_qty+?, reserved_qty=max(0,reserved_qty-?), updated_at=?
                WHERE client_order_id=? AND request_item_id=?
            """, (qty, qty, now(), doc["client_order_id"], line["id"]))
        audit(conn, inv["id"], "DELIVERY_STOCK_OUT", old_qty, new_qty, f"{req['case_no']} {doc['doc_no']}")
        sync_case_line_stock(conn, line["id"])
    conn.execute("UPDATE sales_case_documents SET status=?, updated_at=? WHERE id=?", ("completed", now(), doc["id"]))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/invoice")
def generate_customer_request_invoice(request_id: int):
    conn = db()
    lines = conn.execute("SELECT * FROM customer_request_items WHERE request_id=?", (request_id,)).fetchall()
    invoice_quantities = {}
    for line in lines:
        delivered_qty = int(line["delivered_qty"] or 0)
        invoiced_qty = int(line["invoiced_qty"] or 0)
        quantity = max(0, delivered_qty - invoiced_qty)
        if quantity > 0:
            invoice_quantities[line["id"]] = quantity
    if not invoice_quantities:
        conn.close()
        raise HTTPException(status_code=400, detail="Invoice can be generated only from delivered items")
    delivery_note = latest_sales_document(conn, request_id, "delivery_note")
    client_order = latest_sales_document(conn, request_id, "client_order")
    doc = create_sales_document(conn, request_id, "invoice", "issued", "Invoice generated from delivered items", delivery_note["id"] if delivery_note else None, invoice_quantities)
    conn.execute("""
        UPDATE sales_case_documents
        SET delivery_note_id=?, client_order_id=?, updated_at=?
        WHERE id=?
    """, (delivery_note["id"] if delivery_note else None, client_order.get("client_order_id") if client_order else None, now(), doc["id"]))
    for line_id, quantity in invoice_quantities.items():
        conn.execute("UPDATE customer_request_items SET linked_invoice=?, invoiced_qty=invoiced_qty+?, updated_at=? WHERE id=?", (doc["doc_no"], quantity, now(), line_id))
        if client_order and client_order.get("client_order_id"):
            conn.execute("""
                UPDATE client_order_items
                SET invoiced_qty=invoiced_qty+?, updated_at=?
                WHERE client_order_id=? AND request_item_id=?
            """, (quantity, now(), client_order["client_order_id"], line_id))
    open_uninvoiced = conn.execute("""
        SELECT COUNT(*) AS c FROM customer_request_items
        WHERE request_id=? AND invoiced_qty < quantity
    """, (request_id,)).fetchone()["c"]
    conn.execute("UPDATE customer_requests SET status=?, updated_at=? WHERE id=?", ("invoiced" if not open_uninvoiced else "partially_invoiced", now(), request_id))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.post("/api/customer-requests/{request_id}/status/{status}")
def update_customer_request_status(request_id: int, status: str):
    allowed = {"draft", "pending approval", "approved", "rejected", "partially available", "unavailable", "reserved", "ordered", "partially received", "received", "delivered", "invoiced", "cancelled", "open", "client_order_approved", "partially_delivered", "partially_invoiced"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported status")
    conn = db()
    conn.execute("UPDATE customer_requests SET status=?, updated_at=? WHERE id=?", (status, now(), request_id))
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return data

@app.get("/api/sales-documents/{document_id}/export")
def export_sales_document(document_id: int, format: str = "excel"):
    conn = db()
    doc = conn.execute("SELECT * FROM sales_case_documents WHERE id=?", (document_id,)).fetchone()
    if not doc:
        conn.close()
        raise HTTPException(status_code=404, detail="Document not found")
    rows = [dict(r) for r in conn.execute("SELECT * FROM sales_case_document_lines WHERE document_id=? ORDER BY id", (document_id,)).fetchall()]
    conn.close()
    return export_rows_response(f"{doc['doc_type']}_{doc['doc_no']}", rows, format, dict(doc).get("notes", ""))

@app.get("/api/stock-movements/export")
def export_stock_movements(format: str = "excel"):
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM stock_movements ORDER BY created_at DESC").fetchall()]
    conn.close()
    return export_rows_response("stock_movement_report", rows, format, "Stock IN/OUT movements")

@app.get("/api/equipment-bids")
def list_equipment_bids():
    conn = db()
    bids = [dict(r) for r in conn.execute("SELECT * FROM equipment_bids ORDER BY updated_at DESC").fetchall()]
    for bid in bids:
        bid["items"] = [dict(r) for r in conn.execute("SELECT * FROM equipment_bid_items WHERE bid_id=? ORDER BY id", (bid["id"],)).fetchall()]
    conn.close()
    return bids

@app.post("/api/equipment-bids")
def create_equipment_bid(payload: EquipmentBidIn):
    conn = db()
    client_id = ensure_client(conn, payload.client_hospital, main_contact=payload.contact_person)
    bid_no = payload.bid_no.strip() or f"BID-{date.today().strftime('%y%m%d')}"
    cur = conn.execute("""
        INSERT INTO equipment_bids (bid_no, client_id, client_hospital, contact_person, tender_source, status, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (bid_no, client_id, payload.client_hospital, payload.contact_person, payload.tender_source, payload.status, payload.notes, now(), now()))
    bid_id = cur.lastrowid
    if payload.bid_no.strip() == "":
        conn.execute("UPDATE equipment_bids SET bid_no=? WHERE id=?", (f"{bid_no}-{bid_id:04d}", bid_id))
    for item in payload.items:
        conn.execute("""
            INSERT INTO equipment_bid_items (bid_id, description, manufacturer, model, expected_qty, missing_qty, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (bid_id, item.description, item.manufacturer, item.model, item.expected_qty, item.expected_qty, item.notes, now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_bids WHERE id=?", (bid_id,)).fetchone())
    row["items"] = [dict(r) for r in conn.execute("SELECT * FROM equipment_bid_items WHERE bid_id=? ORDER BY id", (bid_id,)).fetchall()]
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/equipment-bids/{bid_id}/packing-list")
def upload_packing_list(bid_id: int, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Packing list must be a PDF")
    target = UPLOADS_DIR / f"packing_list_{bid_id}_{safe_filename(file.filename)}"
    with target.open("wb") as handle:
        shutil.copyfileobj(file.file, handle)
    conn = db()
    conn.execute("UPDATE equipment_bids SET packing_list_url=?, updated_at=? WHERE id=?", (f"/uploads/{target.name}", now(), bid_id))
    conn.commit()
    conn.close()
    return {"packing_list_url": f"/uploads/{target.name}"}

@app.post("/api/equipment-bids/{bid_id}/receive")
def receive_equipment_bid_item(bid_id: int, payload: EquipmentReceivingIn):
    conn = db()
    item = conn.execute("SELECT * FROM equipment_bid_items WHERE id=? AND bid_id=?", (payload.item_id, bid_id)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Bid item not found")
    serials = [s.strip() for s in payload.serial_numbers if str(s).strip()]
    duplicate_serials = sorted({s for s in serials if serials.count(s) > 1})
    expected = int(item["expected_qty"] or 0)
    received = int(payload.received_qty or 0)
    missing = max(0, expected - received)
    validation = "valid" if not missing and len(serials) >= received and not duplicate_serials else "needs_review"
    conn.execute("""
        UPDATE equipment_bid_items SET received_qty=?, serial_numbers=?, missing_qty=?, validation_status=?, notes=?, updated_at=?
        WHERE id=?
    """, (received, ", ".join(serials), missing, validation, payload.notes, now(), payload.item_id))
    conn.execute("""
        INSERT INTO equipment_receiving_validations
        (bid_id, bid_item_id, expected_qty, received_qty, missing_qty, serial_numbers, validation_result, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (bid_id, payload.item_id, expected, received, missing, ", ".join(serials), validation, f"Duplicate serials: {', '.join(duplicate_serials)}. {payload.notes}".strip(), now(), now()))
    conn.execute("UPDATE equipment_bids SET receiving_status=?, updated_at=? WHERE id=?", ("received" if missing == 0 else "partially_received", now(), bid_id))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_bid_items WHERE id=?", (payload.item_id,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/equipment-bids/{bid_id}/register-equipment")
def register_equipment_from_bid(bid_id: int):
    conn = db()
    bid = conn.execute("SELECT * FROM equipment_bids WHERE id=?", (bid_id,)).fetchone()
    if not bid:
        conn.close()
        raise HTTPException(status_code=404, detail="Bid not found")
    created = []
    for item in conn.execute("SELECT * FROM equipment_bid_items WHERE bid_id=? ORDER BY id", (bid_id,)).fetchall():
        serials = [s.strip() for s in str(item["serial_numbers"] or "").split(",") if s.strip()]
        for idx in range(max(1, int(item["received_qty"] or 0))):
            serial = serials[idx] if idx < len(serials) else ""
            asset_tag = f"EQ-{bid_id}-{item['id']}-{idx+1}"
            conn.execute("""
                INSERT OR IGNORE INTO pm_assets
                (asset_tag, serial_number, manufacturer, model, hospital, client_id, status, warranty_start, warranty_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (asset_tag, serial, item["manufacturer"], item["model"], bid["client_hospital"], bid["client_id"], "Installed", date.today().isoformat(), "active", now(), now()))
            equipment_id = conn.execute("SELECT id FROM pm_assets WHERE asset_tag=?", (asset_tag,)).fetchone()["id"]
            conn.execute("UPDATE equipment_bid_items SET equipment_id=?, updated_at=? WHERE id=?", (equipment_id, now(), item["id"]))
            created.append({"equipment_id": equipment_id, "asset_tag": asset_tag, "serial_number": serial})
    conn.execute("UPDATE equipment_bids SET installation_status=?, warranty_status=?, updated_at=? WHERE id=?", ("registered", "active", now(), bid_id))
    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"created": created}

@app.get("/api/crm/client/{client_id}/client-orders")
def crm_client_orders(client_id: int):
    conn = db()
    client = crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("""
        SELECT * FROM client_orders
        WHERE lower(trim(client_name))=lower(trim(?))
        ORDER BY updated_at DESC
    """, (client["name"],)).fetchall()]
    conn.close()
    return rows

@app.get("/api/crm/client/{client_id}/purchase-orders")
def crm_purchase_orders(client_id: int):
    conn = db()
    crm_client_row(conn, client_id)
    conn.close()
    return []

@app.get("/api/crm/client/{client_id}/reports")
def crm_client_reports(client_id: int):
    conn = db()
    client = crm_client_row(conn, client_id)
    metrics = crm_client_metrics(conn, client)
    conn.close()
    return {"client": client, "metrics": metrics, "reports": ["Equipment registry", "PM compliance", "Warranty alerts", "Open service calls", "Quotation pipeline"]}

@app.get("/api/biomedical/equipment/{equipment_id}/profile")
def biomedical_equipment_profile(equipment_id: int):
    conn = db()
    equipment = conn.execute("SELECT * FROM pm_assets WHERE id=?", (equipment_id,)).fetchone()
    if not equipment:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    profile = {
        "equipment": dict(equipment),
        "calibrations": [dict(r) for r in conn.execute("SELECT * FROM equipment_calibrations WHERE equipment_id=? ORDER BY calibration_date DESC", (equipment_id,)).fetchall()],
        "risk": dict(conn.execute("SELECT * FROM equipment_risk_profiles WHERE equipment_id=?", (equipment_id,)).fetchone() or {}),
        "uptime_events": [dict(r) for r in conn.execute("SELECT * FROM equipment_uptime_events WHERE equipment_id=? ORDER BY started_at DESC", (equipment_id,)).fetchall()],
        "recalls": [dict(r) for r in conn.execute("SELECT * FROM equipment_recall_notices WHERE equipment_id=? ORDER BY created_at DESC", (equipment_id,)).fetchall()],
        "compatibility": [dict(r) for r in conn.execute("SELECT * FROM equipment_compatibility WHERE equipment_id=? ORDER BY compatibility_type, part_no", (equipment_id,)).fetchall()],
        "installation_qualification": [dict(r) for r in conn.execute("SELECT * FROM installation_qualification_forms WHERE equipment_id=? ORDER BY updated_at DESC", (equipment_id,)).fetchall()],
        "acceptance_tests": [dict(r) for r in conn.execute("SELECT * FROM acceptance_testing_forms WHERE equipment_id=? ORDER BY updated_at DESC", (equipment_id,)).fetchall()],
    }
    downtime = sum(float(r.get("downtime_hours") or 0) for r in profile["uptime_events"])
    failures = [r for r in profile["uptime_events"] if str(r.get("event_type", "")).lower() in {"failure", "outage"}]
    uptime = float(dict(equipment).get("total_uptime_hours") or 0)
    profile["uptime_summary"] = {
        "total_uptime_hours": uptime,
        "downtime_hours": downtime,
        "outage_frequency": len(failures),
        "operational_percentage": round((uptime / (uptime + downtime)) * 100, 2) if (uptime + downtime) else 100,
        "mtbf_hours": round(uptime / len(failures), 2) if failures else uptime,
        "recurring_issue_detected": any(int(r.get("recurring_issue") or 0) for r in profile["uptime_events"]),
    }
    conn.close()
    return profile

@app.post("/api/biomedical/calibrations")
def add_calibration(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (record.equipment_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    cur = conn.execute("""
        INSERT INTO equipment_calibrations
        (equipment_id, client_id, calibration_date, next_due_date, calibrated_by, certificate_attachment, calibration_result, standards_used, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("calibration_date", ""), data.get("next_due_date", ""), data.get("calibrated_by", ""), data.get("certificate_attachment", ""), data.get("calibration_result", ""), data.get("standards_used", ""), data.get("notes", ""), now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_calibrations WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/risk-profile")
def save_risk_profile(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (record.equipment_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    conn.execute("""
        INSERT INTO equipment_risk_profiles
        (equipment_id, client_id, risk_level, life_support, criticality_level, department_risk_level, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(equipment_id) DO UPDATE SET risk_level=excluded.risk_level, life_support=excluded.life_support,
            criticality_level=excluded.criticality_level, department_risk_level=excluded.department_risk_level,
            notes=excluded.notes, updated_at=excluded.updated_at
    """, (record.equipment_id, asset["client_id"], data.get("risk_level", "medium"), int(bool(data.get("life_support", False))), data.get("criticality_level", ""), data.get("department_risk_level", ""), data.get("notes", ""), now(), now()))
    conn.execute("""
        UPDATE pm_assets SET risk_level=?, life_support=?, criticality_level=?, department_risk_level=?, updated_at=? WHERE id=?
    """, (data.get("risk_level", "medium"), int(bool(data.get("life_support", False))), data.get("criticality_level", ""), data.get("department_risk_level", ""), now(), record.equipment_id))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_risk_profiles WHERE equipment_id=?", (record.equipment_id,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/uptime-events")
def add_uptime_event(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (record.equipment_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    downtime = float(data.get("downtime_hours") or 0)
    cur = conn.execute("""
        INSERT INTO equipment_uptime_events
        (equipment_id, client_id, event_type, started_at, ended_at, downtime_hours, failure_category, recurring_issue, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("event_type", "outage"), data.get("started_at", ""), data.get("ended_at", ""), downtime, data.get("failure_category", ""), int(bool(data.get("recurring_issue", False))), data.get("notes", ""), now(), now()))
    events = [dict(r) for r in conn.execute("SELECT * FROM equipment_uptime_events WHERE equipment_id=?", (record.equipment_id,)).fetchall()]
    total_downtime = sum(float(r.get("downtime_hours") or 0) for r in events)
    failures = [r for r in events if str(r.get("event_type", "")).lower() in {"failure", "outage"}]
    total_uptime = float(asset["total_uptime_hours"] or data.get("total_uptime_hours") or 0)
    operational = round((total_uptime / (total_uptime + total_downtime)) * 100, 2) if (total_uptime + total_downtime) else 100
    mtbf = round(total_uptime / len(failures), 2) if failures else total_uptime
    conn.execute("UPDATE pm_assets SET total_downtime_hours=?, outage_frequency=?, operational_percentage=?, mtbf_hours=?, recurring_issue_flag=?, updated_at=? WHERE id=?",
                 (total_downtime, len(failures), operational, mtbf, int(any(int(r.get("recurring_issue") or 0) for r in events)), now(), record.equipment_id))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_uptime_events WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/recalls")
def add_recall_notice(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (record.equipment_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    cur = conn.execute("""
        INSERT INTO equipment_recall_notices
        (equipment_id, client_id, notice_type, notice_no, manufacturer, affected_serial_numbers, completion_status, corrective_actions, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("notice_type", "recall"), data.get("notice_no", ""), data.get("manufacturer", asset["manufacturer"] or ""), data.get("affected_serial_numbers", ""), data.get("completion_status", "open"), data.get("corrective_actions", ""), data.get("notes", ""), now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_recall_notices WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/compatibility")
def add_compatibility(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    cur = conn.execute("""
        INSERT INTO equipment_compatibility
        (equipment_id, inventory_item_id, part_no, compatibility_type, description, supplier, substitute_part_no, equivalent_part_no, approved, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, data.get("inventory_item_id"), data.get("part_no", ""), data.get("compatibility_type", "accessory"), data.get("description", ""), data.get("supplier", ""), data.get("substitute_part_no", ""), data.get("equivalent_part_no", ""), int(bool(data.get("approved", True))), data.get("notes", ""), now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment_compatibility WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/pm-checklist-templates")
def save_pm_checklist_template(payload: dict):
    conn = db()
    cur = conn.execute("""
        INSERT INTO pm_checklist_templates
        (equipment_type, manufacturer, model, checklist_items, measurements, engineer_signature_required, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (payload.get("equipment_type", ""), payload.get("manufacturer", ""), payload.get("model", ""), payload.get("checklist_items", ""), payload.get("measurements", ""), int(bool(payload.get("engineer_signature_required", True))), now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM pm_checklist_templates WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/installation-qualification")
def save_installation_qualification(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (record.equipment_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    cur = conn.execute("""
        INSERT INTO installation_qualification_forms
        (equipment_id, client_id, bid_id, site_readiness, installation_checklist, environmental_conditions, networking_power_validation, engineer_signature, customer_signature, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("bid_id"), data.get("site_readiness", ""), data.get("installation_checklist", ""), data.get("environmental_conditions", ""), data.get("networking_power_validation", ""), data.get("engineer_signature", ""), data.get("customer_signature", ""), data.get("status", "draft"), now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM installation_qualification_forms WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.post("/api/biomedical/acceptance-testing")
def save_acceptance_testing(record: BiomedicalRecordIn):
    data = record.data
    conn = db()
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (record.equipment_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    cur = conn.execute("""
        INSERT INTO acceptance_testing_forms
        (equipment_id, client_id, bid_id, functionality, alarms, calibration_verification, electrical_safety, pass_fail_criteria, customer_approval, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("bid_id"), data.get("functionality", ""), data.get("alarms", ""), data.get("calibration_verification", ""), data.get("electrical_safety", ""), data.get("pass_fail_criteria", ""), data.get("customer_approval", ""), data.get("status", "draft"), now(), now()))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM acceptance_testing_forms WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    export_excel(EXCEL_PATH)
    return row

@app.get("/api/biomedical/reports/{report_name}")
def biomedical_report(report_name: str, format: str = "excel"):
    conn = db()
    queries = {
        "calibration-certificate": "SELECT * FROM equipment_calibrations ORDER BY calibration_date DESC",
        "equipment-history": "SELECT * FROM pm_history ORDER BY created_at DESC",
        "installation-report": "SELECT * FROM installation_qualification_forms ORDER BY updated_at DESC",
        "acceptance-test-report": "SELECT * FROM acceptance_testing_forms ORDER BY updated_at DESC",
        "contract-pdf": "SELECT hospital, contract_no, contract_start_date, contract_end_date, COUNT(*) AS equipment_count FROM pm_assets WHERE COALESCE(contract_no,'')!='' GROUP BY hospital, contract_no, contract_start_date, contract_end_date",
        "service-report": "SELECT * FROM service_calls ORDER BY updated_at DESC",
    }
    if report_name not in queries:
        conn.close()
        raise HTTPException(status_code=404, detail="Report not found")
    rows = [dict(r) for r in conn.execute(queries[report_name]).fetchall()]
    conn.close()
    return export_rows_response(report_name, rows, format, f"Biomedical {report_name.replace('-', ' ')}")


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
