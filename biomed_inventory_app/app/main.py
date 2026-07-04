from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from app.erp_api import router as erp_router
from app.mdmanser_api import router as mdmanser_router
from app.quotation_api import ensure_tables as ensure_quotation_tables
from app.quotation_api import router as quotation_router
from pathlib import Path
import sqlite3, os, shutil, urllib.parse, io, base64, json
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
app.include_router(mdmanser_router)
app.include_router(erp_router)
app.include_router(quotation_router)

PUBLIC_PATHS = {"/login", "/docs", "/openapi.json", "/redoc", "/mdmanser", "/cmm", "/static/mdmanser.html"}
PUBLIC_STATIC_SUFFIXES = (".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS:
        return await call_next(request)
    if path.startswith("/api/erp/mdmanser"):
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
    item_category: str = "spare_parts"

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
    po_date: str = ""
    contact_person: str = ""
    payment_terms: str = ""
    shipping_status: str = ""
    shipping_reference: str = ""
    reception_status: str = ""
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
    request_id: int | None = None
    request_item_id: int | None = None
    client_order_no: str = ""

class WarehouseReplenishmentRequest(BaseModel):
    inventory_item_id: int
    requested_qty: int = 1
    supplier: str = ""
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
    end_user: str = ""
    installation_data: str = ""
    warranty_expiration: str = ""
    delivery_doc: str = ""
    supplies: str = ""
    system_name: str = ""
    subsystem_name: str = ""

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
    department: str = ""
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

class CaseLineItemIn(BaseModel):
    requested_item: str
    quantity: int = 1
    item_type: str = "spare_part"
    unit_price: float = 0
    notes: str = ""
    related_equipment_serial: str = ""

class UnifiedCaseEntryIn(BaseModel):
    case_type: str
    client_hospital: str
    contact_person: str = ""
    department: str = ""
    request_source: str = "call"
    priority: str = "normal"
    line_items: list[CaseLineItemIn]
    notes: str = ""
    auto_create_po: bool = True
    auto_reserve_available: bool = True

CASE_TYPES = {
    "spare_parts_sale",
    "accessories_sale",
    "equipment_delivery",
    "installation",
    "corrective_maintenance",
    "preventive_maintenance",
    "warranty_call",
    "maintenance_contract",
    "calibration",
    "training",
    "demo",
    "recall_fmi",
}

REQUEST_SOURCE_ALIASES = {
    "whatsapp": "WhatsApp",
    "customer po": "PO",
    "customer_po": "PO",
    "purchase order": "PO",
}
REQUEST_SOURCES = {"call", "email", "WhatsApp", "bid", "PO", "internal"}
STOCK_ITEM_TYPES = {"spare_part", "accessory", "new_equipment"}
SERVICE_ITEM_TYPES = {"labor", "service", "maintenance_contract", "training", "demo", "calibration"}
LINE_ITEM_TYPES = STOCK_ITEM_TYPES | SERVICE_ITEM_TYPES
PROCUREMENT_STATUSES = {
    "not_ordered",
    "po_draft",
    "po_sent",
    "supplier_confirmed",
    "partially_received",
    "received",
    "cancelled",
}

DOCUMENT_PREFIXES = {
    "quotation": "QT",
    "pro_forma": "PF",
    "client_order": "CO",
    "purchase_order": "PO",
    "delivery_note": "DN",
    "invoice": "INV",
    "service_report": "SR",
    "pm_report": "PMR",
    "installation_report": "IR",
    "acceptance_test_report": "ATR",
}
GENERATABLE_DOCUMENT_TYPES = set(DOCUMENT_PREFIXES)
PARENT_DOCUMENT_PREFIXES = {
    "quotation": "OF",
    "pro_forma": "PF",
    "client_order": "CO",
    "purchase_order": "PO",
    "delivery_note": "DN",
    "invoice": "INV",
    "service_report": "SR",
    "pm_report": "PM",
    "installation_report": "IR",
    "acceptance_test_report": "AT",
    "calibration_certificate": "CAL",
    "contract": "CT",
}

IMPORT_STATUS_MAP = {
    "pending": "pending",
    "open": "pending",
    "in progress": "in_progress",
    "in_progress": "in_progress",
    "approved": "approved",
    "accepted": "approved",
    "rejected": "rejected",
    "ordered": "ordered",
    "delivered": "delivered",
    "invoiced": "invoiced",
    "closed": "closed",
    "blocked": "blocked",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}
BLOCKED_REASONS = {
    "none",
    "finance",
    "procurement",
    "service_engineer",
    "customer_availability",
    "supplier",
    "stock_shortage",
    "technical_issue",
    "management_approval",
    "waiting_payment",
    "waiting_client_approval",
    "missing_document",
}
BULK_TARGETS = {
    "cases": "cases",
    "crm_clients": "clients",
    "clients": "clients",
    "client_activities": "client_activities",
    "pending_calls": "cases",
    "customer_requests": "customer_requests",
    "sales_requests": "sales_requests",
    "offers": "quotations",
    "quotations": "quotations",
    "service_calls": "service_calls",
    "pm_tasks": "pm_tasks",
    "equipment": "pm_assets",
    "inventory_items": "inventory",
    "inventory": "inventory",
    "procurement_items": "customer_request_items",
    "procurement_requests": "procurement_requests",
    "purchase_orders": "purchase_orders",
    "departments": "departments",
}

SOP_WORKFLOWS = {
    "after_sales_sales": [
        "lead",
        "needs_detected",
        "offer_required",
        "parts_request_if_needed",
        "offer_sent",
        "follow_up",
        "deal_closed",
        "delivery_coordination",
        "installation_follow_up",
    ],
    "delivery_installation": [
        "upcoming_delivery",
        "shipment_ready",
        "site_readiness_follow_up",
        "reception_form",
        "delivery_order",
        "customer_appointment",
        "physical_delivery",
        "installation",
        "functional_test",
        "service_report",
        "signed_delivery_order",
        "archive",
        "accountant_notification",
        "equipment_registration",
    ],
    "preventive_maintenance": [
        "contract_new_installation_trigger",
        "pm_scheduled",
        "engineer_notified",
        "appointment_set",
        "checklist_prepared",
        "pm_done",
        "service_report_signed",
        "checklist_archived",
        "spare_part_need_detected",
    ],
    "corrective_maintenance": [
        "call_received",
        "coverage_checked",
        "call_registered",
        "engineer_informed",
        "quotation_if_charged_call",
        "customer_approval",
        "appointment_or_workshop_pickup",
        "service_visit",
        "service_report",
        "accountant_notified_for_invoice",
        "customer_satisfaction_follow_up",
    ],
    "calibration": [
        "calibration_requested",
        "equipment_identified",
        "appointment_set",
        "calibration_done",
        "certificate_attached",
        "next_due_date_recorded",
        "archive",
    ],
    "recall_fmi": [
        "notice_received",
        "affected_units_identified",
        "client_notified",
        "corrective_action_planned",
        "corrective_action_completed",
        "completion_status_recorded",
        "archive",
    ],
}

CASE_TYPE_WORKFLOW = {
    "spare_parts_sale": "after_sales_sales",
    "accessories_sale": "after_sales_sales",
    "training": "after_sales_sales",
    "demo": "after_sales_sales",
    "equipment_delivery": "delivery_installation",
    "installation": "delivery_installation",
    "preventive_maintenance": "preventive_maintenance",
    "maintenance_contract": "preventive_maintenance",
    "corrective_maintenance": "corrective_maintenance",
    "warranty_call": "corrective_maintenance",
    "calibration": "calibration",
    "recall_fmi": "recall_fmi",
}

def normalize_request_source(source: str = "") -> str:
    raw = (source or "call").strip()
    normalized = REQUEST_SOURCE_ALIASES.get(raw.lower(), raw)
    if normalized not in REQUEST_SOURCES:
        raise HTTPException(status_code=400, detail=f"Unsupported request source: {source}")
    return normalized

def validate_case_type(case_type: str = "") -> str:
    normalized = (case_type or "spare_parts_sale").strip()
    if normalized not in CASE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported case type: {case_type}")
    return normalized

def validate_item_type(item_type: str = "") -> str:
    normalized = (item_type or "spare_part").strip()
    if normalized not in LINE_ITEM_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported item/service type: {item_type}")
    return normalized

def workflow_key_for_case_type(case_type: str) -> str:
    return CASE_TYPE_WORKFLOW.get(validate_case_type(case_type), "after_sales_sales")

def workflow_states_for_case_type(case_type: str) -> list[str]:
    return SOP_WORKFLOWS[workflow_key_for_case_type(case_type)]

def initial_workflow_state(case_type: str) -> str:
    return workflow_states_for_case_type(case_type)[0]

def infer_case_type_from_lines(lines: list[CustomerRequestLineIn]) -> str:
    item_types = {validate_item_type(line.item_type) for line in lines}
    if "new_equipment" in item_types:
        return "equipment_delivery"
    if "maintenance_contract" in item_types:
        return "maintenance_contract"
    if "calibration" in item_types:
        return "calibration"
    if "labor" in item_types or "service" in item_types:
        return "corrective_maintenance"
    if "accessory" in item_types:
        return "accessories_sale"
    return "spare_parts_sale"

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

def normalize_inventory_category(category: str = "", device_family: str = "", description: str = "") -> str:
    text = " ".join([category or "", device_family or "", description or ""]).lower()
    if "accessor" in text:
        return "accessories"
    if "equipment" in text or "machine" in text or "system" in text:
        return "equipment"
    return "spare_parts"

def lookup_url_for(pn: str, description: str = "") -> str:
    query = f"{pn} {description} biomedical spare part GE Healthcare".strip()
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)

def generate_parent_case_reference(conn) -> str:
    year = date.today().year
    prefix = f"AS-{year}-"
    rows = conn.execute("""
        SELECT parent_case_reference FROM cases
        WHERE parent_case_reference LIKE ?
        UNION
        SELECT parent_case_reference FROM customer_requests
        WHERE parent_case_reference LIKE ?
    """, (prefix + "%", prefix + "%")).fetchall()
    highest = 0
    for row in rows:
        try:
            highest = max(highest, int(str(row["parent_case_reference"]).rsplit("-", 1)[-1]))
        except (TypeError, ValueError):
            continue
    return f"{prefix}{highest + 1:05d}"

def document_reference_for(parent_case_reference: str = "", doc_type: str = "") -> str:
    if not parent_case_reference:
        return ""
    return f"{PARENT_DOCUMENT_PREFIXES.get(doc_type, 'DOC')}-{parent_case_reference}"

def audit(conn, item_id, action, old_value="", new_value="", notes=""):
    conn.execute("""
        INSERT INTO audit_log (item_id, action, old_value, new_value, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (item_id, action, str(old_value), str(new_value), notes, now()))

def case_timeline(conn, parent_case_reference: str = "", parent_case_id: int | None = None, event_type: str = "",
                  title: str = "", status: str = "", user: str = "system", notes: str = "",
                  related_table: str = "", related_id: int | None = None):
    if not parent_case_reference and parent_case_id:
        row = conn.execute("SELECT parent_case_reference FROM cases WHERE id=?", (parent_case_id,)).fetchone()
        parent_case_reference = row["parent_case_reference"] if row else ""
    if not parent_case_reference and not parent_case_id:
        return
    conn.execute("""
        INSERT INTO case_timeline
        (parent_case_reference, parent_case_id, event_type, title, status, user, notes, related_table, related_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (parent_case_reference, parent_case_id, event_type, title, status, user, notes, related_table, related_id, now()))
    client_id = None
    department_id = None
    if parent_case_id:
        case_row = conn.execute("SELECT client_id, department_id FROM cases WHERE id=?", (parent_case_id,)).fetchone()
        if case_row:
            client_id = case_row["client_id"]
            department_id = case_row["department_id"] if "department_id" in case_row.keys() else None
    if client_id:
        activity_type = "sales" if related_table in {"customer_requests", "quotations", "sales_case_documents", "client_orders"} else "after_sales" if related_table in {"service_calls", "pm_tasks", "pm_assets", "equipment", "warranties", "fmi_notices", "equipment_recall_notices"} else "client_operations"
        conn.execute("""
            INSERT INTO client_activities
            (client_id, department_id, case_id, parent_case_reference, activity_type, source_table, source_id,
             title, status, responsible_person, activity_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (client_id, department_id, parent_case_id, parent_case_reference, activity_type, related_table,
              related_id, title or event_type, status, user, now(), notes, now(), now()))

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
            lookup_url TEXT,
            item_category TEXT DEFAULT 'spare_parts'
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
            po_date TEXT,
            contact_person TEXT,
            payment_terms TEXT,
            shipping_status TEXT,
            shipping_reference TEXT,
            reception_status TEXT,
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
            client_order_no TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inventory_id INTEGER UNIQUE,
            pn TEXT,
            description TEXT,
            device_family TEXT,
            barcode TEXT,
            default_location_id INTEGER,
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT UNIQUE,
            notes TEXT,
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
            end_user TEXT,
            installation_data TEXT,
            warranty_expiration TEXT,
            delivery_doc TEXT,
            supplies TEXT,
            system_name TEXT,
            subsystem_name TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manufacturer TEXT,
            model TEXT,
            equipment_family TEXT,
            modality TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(manufacturer, model)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pm_asset_id INTEGER UNIQUE,
            client_id INTEGER,
            department_id INTEGER,
            equipment_model_id INTEGER,
            asset_tag TEXT,
            serial_number TEXT,
            manufacturer TEXT,
            model TEXT,
            status TEXT,
            warranty_id INTEGER,
            contract_id INTEGER,
            parent_case_reference TEXT,
            parent_case_id INTEGER,
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
        CREATE TABLE IF NOT EXISTS client_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            department_name TEXT,
            floor_location TEXT,
            main_contact_name TEXT,
            phone TEXT,
            email TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(client_id, department_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            department_name TEXT,
            floor_location TEXT,
            main_contact_name TEXT,
            phone TEXT,
            email TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(client_id, department_name)
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
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            department_id INTEGER,
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
        CREATE TABLE IF NOT EXISTS client_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            department_id INTEGER,
            case_id INTEGER,
            parent_case_reference TEXT,
            activity_type TEXT,
            source_table TEXT,
            source_id INTEGER,
            reference TEXT,
            title TEXT,
            status TEXT,
            responsible_person TEXT,
            priority TEXT DEFAULT 'normal',
            due_date TEXT,
            blocked_reason TEXT DEFAULT 'none',
            client_informed INTEGER DEFAULT 0,
            activity_date TEXT,
            department TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
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
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref TEXT,
            description TEXT,
            category TEXT,
            product_type TEXT,
            brand TEXT,
            model TEXT,
            unit_price REAL DEFAULT 0,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quotation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER,
            product_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER,
            unit_price REAL DEFAULT 0,
            total_price REAL DEFAULT 0,
            notes TEXT,
            FOREIGN KEY (quotation_id) REFERENCES quotations(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            co_no TEXT UNIQUE,
            quotation_id INTEGER,
            customer_id INTEGER,
            status TEXT DEFAULT 'open',
            order_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (quotation_id) REFERENCES quotations(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customer_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_order_id INTEGER,
            quotation_item_id INTEGER,
            product_id INTEGER,
            ref TEXT,
            description TEXT,
            ordered_qty INTEGER,
            procured_qty INTEGER DEFAULT 0,
            received_qty INTEGER DEFAULT 0,
            delivered_qty INTEGER DEFAULT 0,
            pending_qty INTEGER,
            status TEXT,
            FOREIGN KEY (customer_order_id) REFERENCES customer_orders(id),
            FOREIGN KEY (quotation_item_id) REFERENCES quotation_items(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER,
            customer_order_id INTEGER,
            customer_order_item_id INTEGER,
            co_no TEXT,
            purchase_order_id INTEGER,
            po_no TEXT,
            supplier_id INTEGER,
            shipment_id INTEGER,
            reception_id INTEGER,
            delivery_order_id INTEGER,
            customer_id INTEGER,
            source TEXT DEFAULT 'customer_order',
            status TEXT DEFAULT 'pending_procurement',
            location TEXT,
            serial_number TEXT,
            barcode TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_no TEXT UNIQUE,
            supplier_id INTEGER,
            status TEXT DEFAULT 'pending',
            shipment_date TEXT,
            expected_arrival TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shipment_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER,
            purchase_order_item_id INTEGER,
            stock_item_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER,
            status TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS receptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reception_no TEXT UNIQUE,
            shipment_id INTEGER,
            received_date TEXT,
            status TEXT DEFAULT 'draft',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reception_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reception_id INTEGER,
            shipment_item_id INTEGER,
            stock_item_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER,
            received_qty INTEGER,
            status TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            do_no TEXT UNIQUE,
            customer_id INTEGER,
            customer_order_id INTEGER,
            status TEXT DEFAULT 'draft',
            delivery_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delivery_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_order_id INTEGER,
            stock_item_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER,
            source TEXT,
            status TEXT
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
        CREATE TABLE IF NOT EXISTS fmi_notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            department_id INTEGER,
            notice_type TEXT,
            manufacturer TEXT,
            affected_model TEXT,
            affected_serial_numbers TEXT,
            corrective_action TEXT,
            completion_status TEXT DEFAULT 'open',
            parent_case_reference TEXT,
            parent_case_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fmi_recalls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            department_id INTEGER,
            notice_type TEXT,
            manufacturer TEXT,
            affected_model TEXT,
            affected_serial_numbers TEXT,
            corrective_action TEXT,
            completion_status TEXT DEFAULT 'open',
            parent_case_reference TEXT,
            parent_case_id INTEGER,
            blocked_reason TEXT DEFAULT 'none',
            client_informed INTEGER DEFAULT 0,
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
        CREATE TABLE IF NOT EXISTS case_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            request_item_id INTEGER UNIQUE,
            inventory_item_id INTEGER,
            requested_item TEXT,
            item_type TEXT,
            quantity INTEGER DEFAULT 1,
            reserved_qty INTEGER DEFAULT 0,
            shortage_qty INTEGER DEFAULT 0,
            procurement_status TEXT DEFAULT 'not_ordered',
            parent_case_reference TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_request_id INTEGER UNIQUE,
            case_id INTEGER,
            client_id INTEGER,
            department_id INTEGER,
            equipment_id INTEGER,
            parent_case_reference TEXT,
            offer_reference TEXT,
            category TEXT,
            status TEXT DEFAULT 'request',
            stock_status TEXT DEFAULT 'unchecked',
            procurement_status TEXT DEFAULT 'not_ordered',
            blocked_reason TEXT DEFAULT 'none',
            responsible_person TEXT,
            next_action TEXT,
            progress_stage TEXT DEFAULT 'request',
            progress_percent INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'normal',
            due_date TEXT,
            client_informed INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_request_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sales_request_id INTEGER,
            customer_request_item_id INTEGER UNIQUE,
            inventory_item_id INTEGER,
            requested_item TEXT,
            category TEXT,
            quantity INTEGER DEFAULT 1,
            available_qty INTEGER DEFAULT 0,
            reserved_qty INTEGER DEFAULT 0,
            shortage_qty INTEGER DEFAULT 0,
            stock_status TEXT DEFAULT 'unchecked',
            procurement_status TEXT DEFAULT 'not_ordered',
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS procurement_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sales_request_item_id INTEGER,
            customer_request_item_id INTEGER UNIQUE,
            inventory_item_id INTEGER,
            client_id INTEGER,
            department_id INTEGER,
            sales_request_id INTEGER,
            purchase_order_id INTEGER,
            category TEXT,
            requested_item TEXT,
            requested_qty INTEGER DEFAULT 0,
            shortage_qty INTEGER DEFAULT 0,
            procurement_status TEXT DEFAULT 'not_ordered',
            supplier TEXT,
            expected_delivery_date TEXT,
            received_qty INTEGER DEFAULT 0,
            pending_qty INTEGER DEFAULT 0,
            responsible_person TEXT,
            blocked_reason TEXT DEFAULT 'none',
            priority TEXT DEFAULT 'normal',
            due_date TEXT,
            client_informed INTEGER DEFAULT 0,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS case_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_case_reference TEXT,
            parent_case_id INTEGER,
            event_type TEXT,
            title TEXT,
            status TEXT,
            user TEXT,
            notes TEXT,
            related_table TEXT,
            related_id INTEGER,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            import_type TEXT,
            filename TEXT,
            status TEXT DEFAULT 'preview',
            total_rows INTEGER DEFAULT 0,
            valid_rows INTEGER DEFAULT 0,
            error_rows INTEGER DEFAULT 0,
            created_by TEXT,
            created_at TEXT,
            committed_at TEXT,
            rolled_back_at TEXT,
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS import_batch_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER,
            row_no INTEGER,
            raw_data TEXT,
            mapped_data TEXT,
            validation_status TEXT,
            error_message TEXT,
            action TEXT,
            client_id INTEGER,
            department_id INTEGER,
            case_id INTEGER,
            request_id INTEGER,
            quotation_id INTEGER,
            parent_case_reference TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    for table_name in ["delivery_notes", "invoices", "service_reports", "pm_reports", "calibration_reports", "contracts"]:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER,
                doc_no TEXT,
                document_reference TEXT,
                parent_case_reference TEXT,
                parent_case_id INTEGER,
                client_id INTEGER,
                department_id INTEGER,
                request_id INTEGER,
                equipment_id INTEGER,
                status TEXT,
                amount REAL DEFAULT 0,
                notes TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS installation_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            doc_no TEXT,
            document_reference TEXT,
            parent_case_reference TEXT,
            parent_case_id INTEGER,
            client_id INTEGER,
            department_id INTEGER,
            request_id INTEGER,
            equipment_id INTEGER,
            status TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            invoice_id INTEGER,
            amount REAL DEFAULT 0,
            payment_date TEXT,
            status TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS communications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            department_id INTEGER,
            case_id INTEGER,
            communication_type TEXT,
            responsible_person TEXT,
            status TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            department_id INTEGER,
            case_id INTEGER,
            priority TEXT DEFAULT 'high',
            status TEXT DEFAULT 'open',
            blocked_reason TEXT DEFAULT 'none',
            responsible_person TEXT,
            due_date TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS warranties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipment_id INTEGER,
            client_id INTEGER,
            department_id INTEGER,
            warranty_start TEXT,
            warranty_end TEXT,
            status TEXT,
            vendor TEXT,
            notes TEXT,
            parent_case_reference TEXT,
            parent_case_id INTEGER,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            full_name TEXT,
            role TEXT,
            email TEXT,
            phone TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engineers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            engineer_name TEXT UNIQUE,
            email TEXT,
            phone TEXT,
            active INTEGER DEFAULT 1,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()

    cols = [r["name"] for r in conn.execute("PRAGMA table_info(inventory)").fetchall()]
    for col in ["barcode", "photo_url", "lookup_url", "client_id", "client_name", "reserved_qty", "item_category"]:
        if col not in cols:
            col_type = "INTEGER DEFAULT 0" if col == "reserved_qty" else "TEXT DEFAULT 'spare_parts'" if col == "item_category" else "TEXT"
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
                "failure_categories", "recurring_issue_flag", "equipment_name", "equipment_family",
                "installation_date", "calibration_required", "calibration_due_date", "last_service_date",
                "lifecycle_status", "eol_date", "eosl_date", "end_user", "installation_data",
                "warranty_expiration", "delivery_doc", "supplies", "system_name", "subsystem_name"]:
        if col not in pm_asset_cols:
            col_type = "REAL DEFAULT 0" if col in {"total_uptime_hours", "total_downtime_hours", "operational_percentage", "mtbf_hours"} else "INTEGER DEFAULT 0" if col in {"life_support", "outage_frequency", "recurring_issue_flag", "calibration_required"} else "TEXT"
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
        "city": "TEXT",
        "main_contact": "TEXT",
        "contact_email": "TEXT",
        "biomedical_department": "TEXT",
        "primary_engineer": "TEXT",
        "phone": "TEXT",
        "financial_status": "TEXT DEFAULT 'good standing'",
        "credit_balance": "REAL DEFAULT 0",
        "last_payment_date": "TEXT",
        "notes": "TEXT",
    }.items():
        if col not in client_cols:
            conn.execute(f"ALTER TABLE clients ADD COLUMN {col} {col_type}")

    po_item_cols = [r["name"] for r in conn.execute("PRAGMA table_info(purchase_order_items)").fetchall()]
    for col in ["request_id", "request_item_id"]:
        if col not in po_item_cols:
            conn.execute(f"ALTER TABLE purchase_order_items ADD COLUMN {col} INTEGER")
    if "client_order_no" not in po_item_cols:
        conn.execute("ALTER TABLE purchase_order_items ADD COLUMN client_order_no TEXT")

    quotation_cols = [r["name"] for r in conn.execute("PRAGMA table_info(quotations)").fetchall()]
    for col in ["request_id", "contact_person", "customer_id", "quotation_date", "valid_until"]:
        if col not in quotation_cols:
            col_type = "INTEGER" if col in {"request_id", "customer_id"} else "TEXT"
            conn.execute(f"ALTER TABLE quotations ADD COLUMN {col} {col_type}")

    po_cols = [r["name"] for r in conn.execute("PRAGMA table_info(purchase_orders)").fetchall()]
    for col in ["client_id", "request_id", "quotation_id", "contract_id", "invoice_id", "case_id", "supplier_id"]:
        if col not in po_cols:
            conn.execute(f"ALTER TABLE purchase_orders ADD COLUMN {col} INTEGER")
    for col in ["po_date", "contact_person", "payment_terms", "shipping_status", "shipping_reference", "reception_status"]:
        if col not in po_cols:
            conn.execute(f"ALTER TABLE purchase_orders ADD COLUMN {col} TEXT")

    po_item_cols = [r["name"] for r in conn.execute("PRAGMA table_info(purchase_order_items)").fetchall()]
    for col in ["purchase_order_id", "stock_item_id", "product_id"]:
        if col not in po_item_cols:
            conn.execute(f"ALTER TABLE purchase_order_items ADD COLUMN {col} INTEGER")
    for col in ["ref", "status"]:
        if col not in po_item_cols:
            conn.execute(f"ALTER TABLE purchase_order_items ADD COLUMN {col} TEXT")

    extra_table_columns = {
        "customer_requests": {
            "department": "TEXT",
            "department_id": "INTEGER",
            "contact_id": "INTEGER",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "external_reference": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "responsible_person": "TEXT",
            "priority": "TEXT DEFAULT 'normal'",
            "due_date": "TEXT",
        },
        "client_activities": {
            "department_id": "INTEGER",
            "case_id": "INTEGER",
            "activity_type": "TEXT",
            "title": "TEXT",
            "description": "TEXT",
            "status": "TEXT DEFAULT 'open'",
            "date": "TEXT",
            "created_by": "TEXT",
            "blocked_notes": "TEXT",
        },
        "sales_requests": {
            "blocked_notes": "TEXT",
        },
        "procurement_requests": {
            "case_id": "INTEGER",
            "case_item_id": "INTEGER",
            "sales_request_item_id": "INTEGER",
            "customer_request_item_id": "INTEGER",
            "client_id": "INTEGER",
            "department_id": "INTEGER",
            "sales_request_id": "INTEGER",
            "purchase_order_id": "INTEGER",
            "category": "TEXT",
            "requested_item": "TEXT",
            "expected_delivery_date": "TEXT",
            "expected_date": "TEXT",
            "received_qty": "INTEGER DEFAULT 0",
            "pending_qty": "INTEGER DEFAULT 0",
            "responsible_person": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "supplier": "TEXT",
            "priority": "TEXT DEFAULT 'normal'",
            "due_date": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "notes": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "blocked_notes": "TEXT",
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
            "notes": "TEXT",
            "department": "TEXT",
            "department_id": "INTEGER",
            "request_source": "TEXT",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "external_reference": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "responsible_person": "TEXT",
            "due_date": "TEXT",
        },
        "quotations": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "document_reference": "TEXT",
            "department_id": "INTEGER",
            "external_reference": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "responsible_person": "TEXT",
            "due_date": "TEXT",
        },
        "client_orders": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "document_reference": "TEXT",
            "department_id": "INTEGER",
            "external_reference": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "responsible_person": "TEXT",
            "due_date": "TEXT",
        },
        "purchase_orders": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "document_reference": "TEXT",
            "department_id": "INTEGER",
            "external_reference": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "responsible_person": "TEXT",
            "due_date": "TEXT",
        },
        "sales_case_documents": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "document_reference": "TEXT",
            "department_id": "INTEGER",
            "external_reference": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "responsible_person": "TEXT",
            "due_date": "TEXT",
        },
        "stock_movements": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
        },
        "customer_request_items": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "responsible_person": "TEXT",
            "due_date": "TEXT",
        },
        "inventory": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
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
        "departments": {
            "department_name": "TEXT",
            "main_contact_name": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
        "contacts": {
            "role": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
        "equipment_models": {
            "equipment_family": "TEXT",
            "notes": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
        },
        "equipment": {
            "pm_asset_id": "INTEGER",
            "warranty_id": "INTEGER",
            "contract_id": "INTEGER",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "created_at": "TEXT",
            "updated_at": "TEXT",
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
        "pm_assets": {
            "department_id": "INTEGER",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "service_calls": {
            "request_id": "INTEGER",
            "call_no": "TEXT",
            "engineer": "TEXT",
            "issue": "TEXT",
            "resolution": "TEXT",
            "opened_at": "TEXT",
            "closed_at": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
            "priority": "TEXT DEFAULT 'normal'",
            "response_time_hours": "REAL DEFAULT 0",
            "progress_state": "TEXT",
            "invoice_required": "INTEGER DEFAULT 0",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "pm_tasks": {
            "asset_id": "INTEGER",
            "task_name": "TEXT",
            "description": "TEXT",
            "checklist": "TEXT",
            "assigned_to": "TEXT",
            "due_date": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
            "report_status": "TEXT",
            "checklist_status": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "priority": "TEXT DEFAULT 'normal'",
            "equipment_id": "INTEGER",
        },
        "pm_history": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
        },
        "equipment_bids": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "equipment_calibrations": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
            "result": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "equipment_uptime_events": {
            "outage_reason": "TEXT",
            "response_time_hours": "REAL DEFAULT 0",
            "repair_time_hours": "REAL DEFAULT 0",
        },
        "equipment_recall_notices": {
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
            "affected_model": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "fmi_notices": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "fmi_recalls": {
            "blocked_notes": "TEXT",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "delivery_notes": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "invoices": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "service_reports": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "pm_reports": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "calibration_reports": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "installation_reports": {
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
        },
        "contracts": {
            "document_id": "INTEGER",
            "doc_no": "TEXT",
            "document_reference": "TEXT",
            "parent_case_reference": "TEXT",
            "parent_case_id": "INTEGER",
            "department_id": "INTEGER",
            "request_id": "INTEGER",
            "equipment_id": "INTEGER",
            "amount": "REAL DEFAULT 0",
            "notes": "TEXT",
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
            "due_date": "TEXT",
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
            "blocked_reason": "TEXT DEFAULT 'none'",
            "blocked_notes": "TEXT",
            "client_informed": "INTEGER DEFAULT 0",
            "date_informed": "TEXT",
            "informed_by": "TEXT",
            "communication_method": "TEXT",
            "informed_notes": "TEXT",
            "informed_attachment": "TEXT",
        },
        "equipment_compatibility": {
            "equipment_model": "TEXT",
            "compatible_consumables": "TEXT",
            "compatible_accessories": "TEXT",
            "compatible_part_numbers": "TEXT",
            "alternatives_substitutes": "TEXT",
        },
        "pm_checklist_templates": {
            "pass_fail_items": "TEXT",
            "measurement_values": "TEXT",
            "comments": "TEXT",
            "engineer_signature": "TEXT",
            "customer_signature": "TEXT",
        },
        "installation_qualification_forms": {
            "power_network_validation": "TEXT",
        },
        "acceptance_testing_forms": {
            "functional_tests": "TEXT",
            "pass_fail": "TEXT",
        },
    }
    for table, columns in extra_table_columns.items():
        existing_cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        for col, col_type in columns.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_inventory_items_inventory_id ON inventory_items(inventory_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_case_items_request_item_id ON case_items(request_item_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_procurement_requests_customer_request_item_id ON procurement_requests(customer_request_item_id)")

    ensure_clients_from_existing_data(conn)
    sync_core_reference_tables(conn)
    ensure_quotation_tables(conn)
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

def clean_excel_value(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()

def normalize_import_status(status: str = "") -> str:
    text = str(status or "pending").strip().lower().replace("-", " ")
    return IMPORT_STATUS_MAP.get(text, text.replace(" ", "_") or "pending")

def normalize_blocked_reason(reason: str = "") -> str:
    text = str(reason or "none").strip().lower().replace(" ", "_").replace("-", "_")
    return text if text in BLOCKED_REASONS else "none"

def import_line_quantity(requirement: str = "") -> tuple[int, str]:
    text = str(requirement or "").strip()
    if not text:
        return 1, ""
    first = text.split(maxsplit=1)[0]
    if first.isdigit():
        qty = max(1, int(first))
        return qty, text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else text
    return 1, text

def infer_case_type_from_requirement(requirement: str = "") -> str:
    text = str(requirement or "").lower()
    if any(token in text for token in ["recall", "fmi", "field modification"]):
        return "recall_fmi"
    if "calibration" in text or "calibrate" in text:
        return "calibration"
    if "pm" in text or "preventive" in text or "maintenance contract" in text:
        return "preventive_maintenance"
    if "install" in text or "delivery" in text:
        return "installation"
    if "accessor" in text:
        return "accessories_sale"
    if any(token in text for token in ["service", "repair", "corrective", "labor"]):
        return "corrective_maintenance"
    return "spare_parts_sale"

def infer_item_type_from_requirement(requirement: str = "") -> str:
    text = str(requirement or "").lower()
    if "accessor" in text:
        return "accessory"
    if any(token in text for token in ["pm", "service", "repair", "install", "calibration", "labor", "maintenance"]):
        return "service"
    if any(token in text for token in ["equipment", "machine", "monitor", "ventilator"]):
        return "new_equipment"
    return "spare_part"

def infer_case_type_from_category(category: str = "", requirement: str = "") -> str:
    text = str(category or "").strip().lower().replace("-", " ").replace("_", " ")
    if "accessor" in text:
        return "accessories_sale"
    if "equipment" in text:
        return "equipment_delivery"
    if text in {"pm", "preventive maintenance"} or "maintenance" in text:
        return "preventive_maintenance"
    if "service" in text:
        return "corrective_maintenance"
    return infer_case_type_from_requirement(requirement)

def infer_item_type_from_category(category: str = "", requirement: str = "") -> str:
    text = str(category or "").strip().lower().replace("-", " ").replace("_", " ")
    if "accessor" in text:
        return "accessory"
    if "equipment" in text:
        return "new_equipment"
    if text in {"pm", "preventive maintenance"}:
        return "maintenance_contract"
    if "service" in text:
        return "service"
    return infer_item_type_from_requirement(requirement)

def workflow_state_for_import_status(case_type: str, status: str) -> str:
    states = workflow_states_for_case_type(case_type)
    status = normalize_import_status(status)
    index_map = {
        "pending": 0,
        "in_progress": min(2, len(states) - 1),
        "approved": min(5, len(states) - 1),
        "ordered": min(6, len(states) - 1),
        "delivered": min(len(states) - 2, len(states) - 1),
        "invoiced": len(states) - 1,
        "closed": len(states) - 1,
        "blocked": min(2, len(states) - 1),
        "cancelled": 0,
        "rejected": 0,
    }
    return states[index_map.get(status, 0)]

def default_pending_offer_field_map(df) -> dict:
    return {
        "hospital": find_col(df, ["hospital", "Hospital", "client", "Client", "customer", "Customer", "hospital/client name"]),
        "location": find_col(df, ["location", "Location", "city", "City", "area", "Area"]),
        "offer_reference": find_col(df, ["offer reference", "Offer Ref", "offer_ref", "Offer Reference", "reference", "Ref", "quotation", "Quotation"]),
        "status": find_col(df, ["status", "Status"]),
        "requirement": find_col(df, ["requirement", "Requirement", "description", "Description", "item", "Item", "request", "Request"]),
        "category": find_col(df, ["category", "Category", "type", "Type", "request category"]),
        "department": find_col(df, ["department", "Department", "dept", "Dept"]),
        "equipment": find_col(df, ["equipment", "Equipment", "machine", "Machine", "asset", "Asset"]),
        "notes": find_col(df, ["notes", "Notes", "comment", "Comment"]),
        "responsible_person": find_col(df, ["responsible person", "Responsible Person", "responsible", "Owner", "engineer", "Engineer"]),
        "date": find_col(df, ["date", "Date", "created", "Created", "request date", "Offer Date"]),
        "blocked_reason": find_col(df, ["blocked by", "Blocked By", "blocked_reason", "Blocked Reason", "blocker"]),
    }

def read_import_dataframe(contents: bytes, filename: str = ""):
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(io.BytesIO(contents))
    return pd.read_excel(io.BytesIO(contents))

def parse_pending_offer_dataframe(df, field_map: dict | None = None) -> list[dict]:
    field_map = {**default_pending_offer_field_map(df), **(field_map or {})}
    rows = []
    for idx, raw in df.fillna("").iterrows():
        mapped = {}
        raw_data = {str(col): clean_excel_value(raw.get(col, "")) for col in df.columns}
        for field, column in field_map.items():
            mapped[field] = clean_excel_value(raw.get(column, "")) if column else ""
        mapped["status"] = normalize_import_status(mapped.get("status"))
        mapped["blocked_reason"] = normalize_blocked_reason(mapped.get("blocked_reason") if mapped.get("status") == "blocked" else mapped.get("blocked_reason"))
        if mapped["status"] == "blocked" and mapped["blocked_reason"] == "none":
            mapped["blocked_reason"] = "missing_document"
        errors = []
        if not mapped.get("hospital"):
            errors.append("hospital/client name is required")
        if not mapped.get("offer_reference"):
            errors.append("offer reference is required")
        if not mapped.get("requirement"):
            errors.append("requirement is required")
        mapped["row_no"] = int(idx) + 2
        mapped["raw_data"] = raw_data
        mapped["validation_status"] = "error" if errors else "valid"
        mapped["errors"] = errors
        rows.append(mapped)
    return rows

def find_case_by_reference(conn, reference: str = ""):
    ref = str(reference or "").strip()
    if not ref:
        return None
    case = conn.execute("""
        SELECT * FROM cases
        WHERE parent_case_reference=? OR external_reference=? OR case_no=?
        ORDER BY id DESC LIMIT 1
    """, (ref, ref, ref)).fetchone()
    if case:
        return case
    linked = conn.execute("""
        SELECT parent_case_reference FROM quotations
        WHERE quotation_no=? OR document_reference=? OR parent_case_reference=? OR external_reference=?
        UNION SELECT parent_case_reference FROM sales_case_documents
        WHERE doc_no=? OR document_reference=? OR parent_case_reference=? OR external_reference=?
        LIMIT 1
    """, (ref, ref, ref, ref, ref, ref, ref, ref)).fetchone()
    if linked and linked["parent_case_reference"]:
        return conn.execute("SELECT * FROM cases WHERE parent_case_reference=? ORDER BY id DESC LIMIT 1", (linked["parent_case_reference"],)).fetchone()
    return None

def upsert_import_quote_document(conn, request_id: int, client_id: int, department_id: int | None, case_id: int,
                                 parent_ref: str, offer_ref: str, status: str, requirement: str,
                                 responsible_person: str = "", blocked_reason: str = "none"):
    existing_quote = conn.execute("""
        SELECT * FROM quotations
        WHERE quotation_no=? OR external_reference=? OR parent_case_reference=?
        ORDER BY id DESC LIMIT 1
    """, (offer_ref, offer_ref, parent_ref)).fetchone()
    if existing_quote:
        quotation_id = existing_quote["id"]
        conn.execute("""
            UPDATE quotations
            SET status=?, notes=COALESCE(NULLIF(?, ''), notes), request_id=COALESCE(request_id, ?),
                client_id=COALESCE(client_id, ?), department_id=COALESCE(department_id, ?),
                parent_case_reference=?, parent_case_id=?, document_reference=?,
                external_reference=?, responsible_person=?, blocked_reason=?, updated_at=?
            WHERE id=?
        """, (status, requirement, request_id, client_id, department_id, parent_ref, case_id,
              document_reference_for(parent_ref, "quotation"), offer_ref, responsible_person, blocked_reason, now(), quotation_id))
    else:
        cur = conn.execute("""
            INSERT INTO quotations
            (client_id, equipment_id, service_call_id, quotation_no, quote_date, status, amount, notes, created_at, updated_at,
             request_id, contact_person, parent_case_reference, parent_case_id, document_reference, department_id,
             external_reference, responsible_person, blocked_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (client_id, None, None, offer_ref, date.today().isoformat(), status, 0, requirement, now(), now(),
              request_id, responsible_person, parent_ref, case_id, document_reference_for(parent_ref, "quotation"), department_id,
              offer_ref, responsible_person, blocked_reason))
        quotation_id = cur.lastrowid
    existing_doc = conn.execute("""
        SELECT * FROM sales_case_documents
        WHERE request_id=? AND doc_type='quotation' AND (doc_no=? OR external_reference=? OR parent_case_reference=?)
        ORDER BY id DESC LIMIT 1
    """, (request_id, offer_ref, offer_ref, parent_ref)).fetchone()
    if existing_doc:
        conn.execute("""
            UPDATE sales_case_documents
            SET status=?, notes=COALESCE(NULLIF(?, ''), notes), parent_case_reference=?, parent_case_id=?,
                document_reference=?, department_id=COALESCE(department_id, ?), quotation_id=?,
                external_reference=?, responsible_person=?, blocked_reason=?, updated_at=?
            WHERE id=?
        """, (status, requirement, parent_ref, case_id, document_reference_for(parent_ref, "quotation"),
              department_id, quotation_id, offer_ref, responsible_person, blocked_reason, now(), existing_doc["id"]))
        document_id = existing_doc["id"]
    else:
        cur = conn.execute("""
            INSERT INTO sales_case_documents
            (request_id, client_id, doc_type, doc_no, status, quotation_id, amount, notes, created_at, updated_at,
             parent_case_reference, parent_case_id, document_reference, department_id, external_reference,
             responsible_person, blocked_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (request_id, client_id, "quotation", offer_ref, status, quotation_id, 0, requirement, now(), now(),
              parent_ref, case_id, document_reference_for(parent_ref, "quotation"), department_id, offer_ref,
              responsible_person, blocked_reason))
        document_id = cur.lastrowid
    return quotation_id, document_id

def commit_pending_offer_rows(conn, rows: list[dict], batch_id: int | None = None, user: str = "system", create_missing_hospitals: bool = True):
    results = []
    for mapped in rows:
        errors = list(mapped.get("errors") or [])
        if mapped.get("validation_status") == "error" and errors:
            results.append({"row_no": mapped.get("row_no"), "status": "error", "errors": errors})
            continue
        hospital = str(mapped.get("hospital") or "").strip()
        offer_ref = str(mapped.get("offer_reference") or "").strip()
        requirement = str(mapped.get("requirement") or "").strip()
        if not hospital or not offer_ref or not requirement:
            errors = [msg for msg, ok in [
                ("hospital/client name is required", bool(hospital)),
                ("offer reference is required", bool(offer_ref)),
                ("requirement is required", bool(requirement)),
            ] if not ok]
            results.append({"row_no": mapped.get("row_no"), "status": "error", "errors": errors})
            continue
        client_id = ensure_client(conn, hospital, city=mapped.get("location", ""), address=mapped.get("location", "")) if create_missing_hospitals else None
        if not client_id:
            results.append({"row_no": mapped.get("row_no"), "status": "error", "errors": ["hospital was not found and create_missing_hospitals is false"]})
            continue
        if mapped.get("location"):
            conn.execute("""
                UPDATE clients
                SET city=COALESCE(NULLIF(city, ''), ?),
                    address=COALESCE(NULLIF(address, ''), ?),
                    updated_at=?
                WHERE id=?
            """, (mapped.get("location", ""), mapped.get("location", ""), now(), client_id))
        department_id = ensure_department(conn, client_id, mapped.get("department", ""), main_contact_name=mapped.get("responsible_person", "")) if mapped.get("department") else None
        status = normalize_import_status(mapped.get("status"))
        blocked_reason = normalize_blocked_reason(mapped.get("blocked_reason"))
        case_type = infer_case_type_from_category(mapped.get("category", ""), requirement)
        workflow_state = workflow_state_for_import_status(case_type, status)
        quantity, clean_requirement = import_line_quantity(requirement)
        item_type = infer_item_type_from_category(mapped.get("category", ""), requirement)
        existing_case = find_case_by_reference(conn, offer_ref)
        action = "updated" if existing_case else "created"
        if existing_case:
            case_id = existing_case["id"]
            parent_ref = existing_case["parent_case_reference"] or (offer_ref if offer_ref.startswith("AS-") else generate_parent_case_reference(conn))
            request_id = existing_case["request_id"]
            if not request_id:
                cur_req = conn.execute("""
                    INSERT INTO customer_requests
                    (case_no, client_id, client_hospital, contact_person, request_source, status, notes, created_at, updated_at,
                     department, department_id, parent_case_reference, parent_case_id, external_reference, blocked_reason,
                     blocked_notes, responsible_person, due_date, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (existing_case["case_no"], client_id, hospital, mapped.get("responsible_person", ""), "email", status,
                      mapped.get("notes", "") or requirement, now(), now(), mapped.get("department", ""), department_id,
                      parent_ref, case_id, offer_ref, blocked_reason, mapped.get("notes", ""),
                      mapped.get("responsible_person", ""), mapped.get("date", ""), existing_case["priority"] or "normal"))
                request_id = cur_req.lastrowid
            conn.execute("""
                UPDATE cases
                SET client_id=?, department_id=COALESCE(?, department_id), department=COALESCE(NULLIF(?, ''), department),
                    status=?, workflow_state=?, priority=COALESCE(NULLIF(?, ''), priority),
                    notes=COALESCE(NULLIF(?, ''), notes), external_reference=COALESCE(NULLIF(external_reference, ''), ?),
                    blocked_reason=?, blocked_notes=COALESCE(NULLIF(?, ''), blocked_notes),
                    responsible_person=COALESCE(NULLIF(?, ''), responsible_person),
                    due_date=COALESCE(NULLIF(?, ''), due_date), parent_case_reference=?, parent_case_id=COALESCE(parent_case_id, ?),
                    request_id=COALESCE(request_id, ?), updated_at=?
                WHERE id=?
            """, (client_id, department_id, mapped.get("department", ""), status, workflow_state, mapped.get("priority", ""),
                  mapped.get("notes", "") or requirement, offer_ref, blocked_reason, mapped.get("notes", ""),
                  mapped.get("responsible_person", ""), mapped.get("date", ""), parent_ref, case_id, request_id, now(), case_id))
            if request_id:
                conn.execute("""
                    UPDATE customer_requests
                    SET client_id=?, client_hospital=?, department_id=COALESCE(?, department_id),
                        department=COALESCE(NULLIF(?, ''), department), status=?, notes=COALESCE(NULLIF(?, ''), notes),
                        external_reference=COALESCE(NULLIF(external_reference, ''), ?), blocked_reason=?,
                        blocked_notes=COALESCE(NULLIF(?, ''), blocked_notes), responsible_person=COALESCE(NULLIF(?, ''), responsible_person),
                        due_date=COALESCE(NULLIF(?, ''), due_date), updated_at=?
                    WHERE id=?
                """, (client_id, hospital, department_id, mapped.get("department", ""), status, mapped.get("notes", "") or requirement,
                      offer_ref, blocked_reason, mapped.get("notes", ""), mapped.get("responsible_person", ""),
                      mapped.get("date", ""), now(), request_id))
        else:
            parent_ref = offer_ref if offer_ref.startswith("AS-") else generate_parent_case_reference(conn)
            case_no = f"CASE-IMPORT-{datetime.now().strftime('%y%m%d%H%M%S%f')}"
            cur_req = conn.execute("""
                INSERT INTO customer_requests
                (case_no, client_id, client_hospital, contact_person, request_source, status, notes, created_at, updated_at,
                 department, department_id, parent_case_reference, external_reference, blocked_reason, blocked_notes,
                 responsible_person, due_date, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_no, client_id, hospital, mapped.get("responsible_person", ""), "email", status,
                  mapped.get("notes", "") or requirement, now(), now(), mapped.get("department", ""), department_id,
                  parent_ref, offer_ref, blocked_reason, mapped.get("notes", ""), mapped.get("responsible_person", ""),
                  mapped.get("date", ""), "normal"))
            request_id = cur_req.lastrowid
            cur_case = conn.execute("""
                INSERT INTO cases
                (case_no, case_type, client_id, request_id, priority, status, workflow_state, created_at, updated_at,
                 notes, department, department_id, request_source, parent_case_reference, external_reference,
                 blocked_reason, blocked_notes, responsible_person, due_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (case_no, case_type, client_id, request_id, "normal", status, workflow_state, now(), now(),
                  mapped.get("notes", "") or requirement, mapped.get("department", ""), department_id, "email",
                  parent_ref, offer_ref, blocked_reason, mapped.get("notes", ""), mapped.get("responsible_person", ""),
                  mapped.get("date", "")))
            case_id = cur_case.lastrowid
            conn.execute("UPDATE cases SET parent_case_id=? WHERE id=?", (case_id, case_id))
            conn.execute("UPDATE customer_requests SET parent_case_id=? WHERE id=?", (case_id, request_id))
            conn.execute("""
                INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
                VALUES (?, ?, ?, ?, ?)
            """, (case_id, workflow_state, now(), user, f"Imported from offer reference {offer_ref}"))
        existing_line = conn.execute("""
            SELECT id FROM customer_request_items
            WHERE request_id=? AND lower(trim(requested_item))=lower(trim(?))
            LIMIT 1
        """, (request_id, clean_requirement or requirement)).fetchone()
        if existing_line:
            conn.execute("""
                UPDATE customer_request_items
                SET quantity=?, item_type=?, notes=COALESCE(NULLIF(?, ''), notes), blocked_reason=?, responsible_person=?, due_date=?, updated_at=?
                WHERE id=?
            """, (quantity, item_type, mapped.get("notes", ""), blocked_reason, mapped.get("responsible_person", ""),
                  mapped.get("date", ""), now(), existing_line["id"]))
        else:
            conn.execute("""
                INSERT INTO customer_request_items
                (request_id, requested_item, item_type, quantity, unit_price, notes, related_equipment_serial,
                 requested_qty, procurement_status, blocked_reason, responsible_person, due_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (request_id, clean_requirement or requirement, item_type, quantity, 0, mapped.get("notes", ""),
                  mapped.get("equipment", ""), quantity, "not_ordered", blocked_reason, mapped.get("responsible_person", ""),
                  mapped.get("date", ""), now(), now()))
        quotation_id, document_id = upsert_import_quote_document(
            conn, request_id, client_id, department_id, case_id, parent_ref, offer_ref, status, requirement,
            mapped.get("responsible_person", ""), blocked_reason
        )
        conn.execute("""
            UPDATE cases SET quotation_id=COALESCE(quotation_id, ?), updated_at=? WHERE id=?
        """, (quotation_id, now(), case_id))
        case_timeline(conn, parent_ref, case_id, "import", f"Pending offer import {action}", status, user, offer_ref, "import_batches", batch_id)
        if status == "blocked":
            case_timeline(conn, parent_ref, case_id, "blocked", "Case blocked", blocked_reason, user, mapped.get("notes", ""), "cases", case_id)
        if batch_id:
            conn.execute("""
                UPDATE import_batch_rows
                SET action=?, client_id=?, department_id=?, case_id=?, request_id=?, quotation_id=?,
                    parent_case_reference=?, validation_status='imported', updated_at=?
                WHERE batch_id=? AND row_no=?
            """, (action, client_id, department_id, case_id, request_id, quotation_id, parent_ref, now(), batch_id, mapped.get("row_no")))
        results.append({
            "row_no": mapped.get("row_no"),
            "status": "imported",
            "action": action,
            "client_id": client_id,
            "department_id": department_id,
            "case_id": case_id,
            "request_id": request_id,
            "quotation_id": quotation_id,
            "parent_case_reference": parent_ref,
            "offer_reference": offer_ref,
        })
    return results

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

def ensure_contact(conn, client_id: int | None, name: str = "", department: str = "", email: str = "", phone: str = "") -> int | None:
    clean_name = str(name or "").strip()
    if not client_id or not clean_name:
        return None
    existing = conn.execute(
        "SELECT * FROM crm_contacts WHERE client_id=? AND lower(trim(name))=lower(trim(?))",
        (client_id, clean_name),
    ).fetchone()
    role = department or (existing["role"] if existing else "")
    if existing:
        conn.execute("""
            UPDATE crm_contacts
            SET role=COALESCE(NULLIF(?, ''), role),
                email=COALESCE(NULLIF(?, ''), email),
                phone=COALESCE(NULLIF(?, ''), phone),
                updated_at=?
            WHERE id=?
        """, (role, email, phone, now(), existing["id"]))
        conn.execute("""
            INSERT INTO contacts (id, client_id, name, role, email, phone, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET client_id=excluded.client_id, name=excluded.name,
                role=excluded.role, email=excluded.email, phone=excluded.phone, updated_at=excluded.updated_at
        """, (existing["id"], client_id, clean_name, role, email, phone, existing["notes"] if "notes" in existing.keys() else "", existing["created_at"] if "created_at" in existing.keys() else now(), now()))
        return existing["id"]
    cur = conn.execute("""
        INSERT INTO crm_contacts (client_id, name, role, email, phone, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (client_id, clean_name, department, email, phone, "Created from unified case entry", now(), now()))
    conn.execute("""
        INSERT INTO contacts (id, client_id, name, role, email, phone, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cur.lastrowid, client_id, clean_name, department, email, phone, "Created from unified case entry", now(), now()))
    return cur.lastrowid

def ensure_department(conn, client_id: int | None, department_name: str = "", **defaults) -> int | None:
    if not client_id:
        return None
    clean_name = str(department_name or "").strip() or "Biomedical Department"
    existing = conn.execute("""
        SELECT id FROM client_departments
        WHERE client_id=? AND lower(trim(department_name))=lower(trim(?))
    """, (client_id, clean_name)).fetchone()
    if existing:
        conn.execute("""
            UPDATE client_departments
            SET floor_location=COALESCE(NULLIF(?, ''), floor_location),
                main_contact_name=COALESCE(NULLIF(?, ''), main_contact_name),
                phone=COALESCE(NULLIF(?, ''), phone),
                email=COALESCE(NULLIF(?, ''), email),
                notes=COALESCE(NULLIF(?, ''), notes),
                updated_at=?
            WHERE id=?
        """, (
            defaults.get("floor_location", ""),
            defaults.get("main_contact_name", ""),
            defaults.get("phone", ""),
            defaults.get("email", ""),
            defaults.get("notes", ""),
            now(),
            existing["id"],
        ))
        conn.execute("""
            INSERT INTO departments (id, client_id, department_name, floor_location, main_contact_name, phone, email, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET client_id=excluded.client_id, department_name=excluded.department_name,
                floor_location=excluded.floor_location, main_contact_name=excluded.main_contact_name,
                phone=excluded.phone, email=excluded.email, notes=excluded.notes, updated_at=excluded.updated_at
        """, (
            existing["id"], client_id, clean_name, defaults.get("floor_location", ""),
            defaults.get("main_contact_name", ""), defaults.get("phone", ""), defaults.get("email", ""),
            defaults.get("notes", ""), now(), now()
        ))
        return existing["id"]
    cur = conn.execute("""
        INSERT INTO client_departments
        (client_id, department_name, floor_location, main_contact_name, phone, email, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id,
        clean_name,
        defaults.get("floor_location", ""),
        defaults.get("main_contact_name", ""),
        defaults.get("phone", ""),
        defaults.get("email", ""),
        defaults.get("notes", ""),
        now(),
        now(),
    ))
    conn.execute("""
        INSERT INTO departments (id, client_id, department_name, floor_location, main_contact_name, phone, email, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cur.lastrowid,
        client_id,
        clean_name,
        defaults.get("floor_location", ""),
        defaults.get("main_contact_name", ""),
        defaults.get("phone", ""),
        defaults.get("email", ""),
        defaults.get("notes", ""),
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
            for row in conn.execute("""
                SELECT DISTINCT department, contact_email
                FROM pm_assets
                WHERE client_id=? AND COALESCE(department, '') != ''
            """, (client_id,)).fetchall():
                department_id = ensure_department(
                    conn,
                    client_id,
                    row["department"],
                    email=row["contact_email"] or "",
                    notes="Discovered from installed equipment",
                )
                conn.execute("""
                    UPDATE pm_assets SET department_id=?
                    WHERE client_id=? AND lower(trim(COALESCE(department, '')))=lower(trim(?))
                """, (department_id, client_id, row["department"]))

def sync_core_reference_tables(conn):
    for row in conn.execute("SELECT * FROM client_departments").fetchall():
        conn.execute("""
            INSERT OR IGNORE INTO departments
            (id, client_id, department_name, floor_location, main_contact_name, phone, email, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["id"], row["client_id"], row["department_name"], row["floor_location"], row["main_contact_name"],
            row["phone"], row["email"], row["notes"], row["created_at"], row["updated_at"]
        ))
    for row in conn.execute("SELECT * FROM crm_contacts").fetchall():
        department_id = None
        if row["role"]:
            dept = conn.execute("""
                SELECT id FROM departments
                WHERE client_id=? AND lower(trim(department_name))=lower(trim(?))
            """, (row["client_id"], row["role"])).fetchone()
            department_id = dept["id"] if dept else None
        conn.execute("""
            INSERT OR IGNORE INTO contacts
            (id, client_id, department_id, name, role, email, phone, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (row["id"], row["client_id"], department_id, row["name"], row["role"], row["email"], row["phone"], row["notes"], row["created_at"], row["updated_at"]))
    for row in conn.execute("SELECT DISTINCT COALESCE(location, '') AS location FROM inventory WHERE COALESCE(location, '') != ''").fetchall():
        conn.execute("""
            INSERT OR IGNORE INTO stock_locations (location_name, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (row["location"], "Discovered from inventory", now(), now()))
    for row in conn.execute("SELECT * FROM inventory").fetchall():
        loc = conn.execute("SELECT id FROM stock_locations WHERE location_name=?", (row["location"],)).fetchone()
        conn.execute("""
            INSERT OR IGNORE INTO inventory_items
            (id, inventory_id, pn, description, device_family, barcode, default_location_id, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (row["id"], row["id"], row["pn"], row["description"], row["device_family"], row["barcode"], loc["id"] if loc else None, 1, row["updated_at"] or now(), row["updated_at"] or now()))
    for row in conn.execute("SELECT * FROM pm_assets").fetchall():
        if row["manufacturer"] or row["model"]:
            conn.execute("""
                INSERT OR IGNORE INTO equipment_models (manufacturer, model, equipment_family, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (row["manufacturer"], row["model"], detect_family(" ".join([row["manufacturer"] or "", row["model"] or ""])), "Discovered from installed equipment", now(), now()))
        model = conn.execute("""
            SELECT id FROM equipment_models
            WHERE COALESCE(manufacturer, '')=COALESCE(?, '') AND COALESCE(model, '')=COALESCE(?, '')
        """, (row["manufacturer"], row["model"])).fetchone()
        conn.execute("""
            INSERT OR IGNORE INTO equipment
            (id, pm_asset_id, client_id, department_id, equipment_model_id, asset_tag, serial_number, manufacturer, model, status, parent_case_reference, parent_case_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (row["id"], row["id"], row["client_id"], row["department_id"] if "department_id" in row.keys() else None, model["id"] if model else None, row["asset_tag"], row["serial_number"], row["manufacturer"], row["model"], row["status"], row["parent_case_reference"] if "parent_case_reference" in row.keys() else "", row["parent_case_id"] if "parent_case_id" in row.keys() else None, row["created_at"], row["updated_at"]))
        conn.execute("""
            UPDATE equipment
            SET client_id=?, department_id=?, equipment_model_id=?, asset_tag=?, serial_number=?,
                manufacturer=?, model=?, status=?, parent_case_reference=?, parent_case_id=?, updated_at=?
            WHERE pm_asset_id=?
        """, (
            row["client_id"], row["department_id"] if "department_id" in row.keys() else None,
            model["id"] if model else None, row["asset_tag"], row["serial_number"], row["manufacturer"],
            row["model"], row["status"], row["parent_case_reference"] if "parent_case_reference" in row.keys() else "",
            row["parent_case_id"] if "parent_case_id" in row.keys() else None, row["updated_at"], row["id"]
        ))
        if row["warranty_start"] or row["warranty_end"]:
            existing = conn.execute("SELECT id FROM warranties WHERE equipment_id=?", (row["id"],)).fetchone()
            status = row["warranty_status"] or warranty_status(row["warranty_end"])
            if existing:
                conn.execute("""
                    UPDATE warranties SET client_id=?, department_id=?, warranty_start=?, warranty_end=?, status=?, vendor=?, notes=?, updated_at=?
                    WHERE id=?
                """, (row["client_id"], row["department_id"] if "department_id" in row.keys() else None, row["warranty_start"], row["warranty_end"], status, row["vendor"], row["warranty_notes"], now(), existing["id"]))
            else:
                conn.execute("""
                    INSERT INTO warranties
                    (equipment_id, client_id, department_id, warranty_start, warranty_end, status, vendor, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (row["id"], row["client_id"], row["department_id"] if "department_id" in row.keys() else None, row["warranty_start"], row["warranty_end"], status, row["vendor"], row["warranty_notes"], now(), now()))
    for row in conn.execute("SELECT * FROM equipment_recall_notices").fetchall():
        conn.execute("""
            INSERT OR IGNORE INTO fmi_notices
            (id, equipment_id, client_id, notice_type, manufacturer, affected_model, affected_serial_numbers, corrective_action, completion_status, parent_case_reference, parent_case_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (row["id"], row["equipment_id"], row["client_id"], row["notice_type"], row["manufacturer"], row["affected_model"] if "affected_model" in row.keys() else "", row["affected_serial_numbers"], row["corrective_actions"], row["completion_status"], row["parent_case_reference"] if "parent_case_reference" in row.keys() else "", row["parent_case_id"] if "parent_case_id" in row.keys() else None, row["created_at"], row["updated_at"]))
    for row in conn.execute("SELECT * FROM fmi_notices").fetchall():
        conn.execute("""
            INSERT OR IGNORE INTO fmi_recalls
            (id, equipment_id, client_id, department_id, notice_type, manufacturer, affected_model,
             affected_serial_numbers, corrective_action, completion_status, parent_case_reference,
             parent_case_id, blocked_reason, client_informed, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["id"], row["equipment_id"], row["client_id"], row["department_id"], row["notice_type"],
            row["manufacturer"], row["affected_model"], row["affected_serial_numbers"], row["corrective_action"],
            row["completion_status"], row["parent_case_reference"], row["parent_case_id"],
            row["blocked_reason"] if "blocked_reason" in row.keys() else "none",
            row["client_informed"] if "client_informed" in row.keys() else 0,
            row["created_at"], row["updated_at"],
        ))
    for row in conn.execute("""
        SELECT i.*, c.id AS case_id, c.parent_case_reference
        FROM customer_request_items i
        JOIN customer_requests r ON r.id=i.request_id
        LEFT JOIN cases c ON c.request_id=r.id
    """).fetchall():
        conn.execute("""
            INSERT OR IGNORE INTO case_items
            (case_id, request_item_id, inventory_item_id, requested_item, item_type, quantity, reserved_qty, shortage_qty, procurement_status, parent_case_reference, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["case_id"], row["id"], row["inventory_item_id"], row["requested_item"], row["item_type"],
            row["quantity"], row["reserved_qty"], row["shortage_qty"], row["procurement_status"],
            row["parent_case_reference"], row["created_at"], row["updated_at"]
        ))
    for req in conn.execute("""
        SELECT r.*, c.id AS case_id, c.case_type, c.workflow_state, c.priority,
               c.responsible_person AS case_responsible, c.due_date AS case_due_date,
               q.quotation_no AS offer_reference
        FROM customer_requests r
        LEFT JOIN cases c ON c.request_id=r.id
        LEFT JOIN quotations q ON q.request_id=r.id
    """).fetchall():
        lines = [dict(line) for line in conn.execute("SELECT * FROM customer_request_items WHERE request_id=?", (req["id"],)).fetchall()]
        category = sales_category_for_lines(lines, req["case_type"] if "case_type" in req.keys() else "")
        stock_statuses = {line.get("stock_status") for line in lines}
        procurement_statuses = {line.get("procurement_status") for line in lines}
        stock_status = "available" if stock_statuses and stock_statuses <= {"available", "reserved", "invoiced"} else "partial" if any(s in {"available", "reserved", "partially_available", "partially_reserved"} for s in stock_statuses) else "unavailable" if lines else "unchecked"
        procurement_status = "received" if procurement_statuses and procurement_statuses <= {"received"} else next((s for s in ["partially_received", "supplier_confirmed", "po_sent", "po_draft", "not_ordered"] if s in procurement_statuses), "not_ordered")
        progress = progress_for_case(dict(req), [dict(d) for d in conn.execute("SELECT * FROM sales_case_documents WHERE request_id=?", (req["id"],)).fetchall()], lines) if req["case_id"] else {"current_stage": "request", "percent": 0, "next_action": "quotation"}
        conn.execute("""
            INSERT INTO sales_requests
            (customer_request_id, case_id, client_id, department_id, parent_case_reference, offer_reference,
             category, status, stock_status, procurement_status, blocked_reason, responsible_person, next_action,
             progress_stage, progress_percent, priority, due_date, client_informed, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(customer_request_id) DO UPDATE SET case_id=excluded.case_id, client_id=excluded.client_id,
                department_id=excluded.department_id, parent_case_reference=excluded.parent_case_reference,
                offer_reference=excluded.offer_reference, category=excluded.category, status=excluded.status,
                stock_status=excluded.stock_status, procurement_status=excluded.procurement_status,
                blocked_reason=excluded.blocked_reason, responsible_person=excluded.responsible_person,
                next_action=excluded.next_action, progress_stage=excluded.progress_stage,
                progress_percent=excluded.progress_percent, priority=excluded.priority, due_date=excluded.due_date,
                client_informed=excluded.client_informed, notes=excluded.notes, updated_at=excluded.updated_at
        """, (
            req["id"], req["case_id"], req["client_id"], req["department_id"] if "department_id" in req.keys() else None,
            req["parent_case_reference"], req["offer_reference"] or req["external_reference"] if "external_reference" in req.keys() else "",
            category, req["status"], stock_status, procurement_status,
            req["blocked_reason"] if "blocked_reason" in req.keys() else "none",
            req["responsible_person"] if "responsible_person" in req.keys() and req["responsible_person"] else req["case_responsible"],
            progress["next_action"], progress["current_stage"], progress["percent"], req["priority"] if "priority" in req.keys() else req["priority"],
            req["due_date"] if "due_date" in req.keys() and req["due_date"] else req["case_due_date"],
            req["client_informed"] if "client_informed" in req.keys() else 0,
            req["notes"], req["created_at"], now(),
        ))
        sales_request_id = conn.execute("SELECT id FROM sales_requests WHERE customer_request_id=?", (req["id"],)).fetchone()["id"]
        for line in lines:
            line_category = normalize_sales_category(line.get("item_type") or category)
            conn.execute("""
                INSERT INTO sales_request_items
                (sales_request_id, customer_request_item_id, inventory_item_id, requested_item, category, quantity,
                 available_qty, reserved_qty, shortage_qty, stock_status, procurement_status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_request_item_id) DO UPDATE SET sales_request_id=excluded.sales_request_id,
                    inventory_item_id=excluded.inventory_item_id, requested_item=excluded.requested_item,
                    category=excluded.category, quantity=excluded.quantity, available_qty=excluded.available_qty,
                    reserved_qty=excluded.reserved_qty, shortage_qty=excluded.shortage_qty,
                    stock_status=excluded.stock_status, procurement_status=excluded.procurement_status,
                    notes=excluded.notes, updated_at=excluded.updated_at
            """, (
                sales_request_id, line["id"], line.get("inventory_item_id"), line.get("requested_item", ""),
                line_category, int(line.get("quantity") or 0), int(line.get("available_qty") or 0),
                int(line.get("reserved_qty") or 0), int(line.get("shortage_qty") or 0),
                line.get("stock_status") or "unchecked", line.get("procurement_status") or "not_ordered",
                line.get("notes") or "", line.get("created_at") or now(), now(),
            ))
            shortage = int(line.get("shortage_qty") or 0)
            if shortage > 0 or line.get("procurement_status") in PROCUREMENT_STATUSES - {"received", "cancelled"}:
                sri = conn.execute("SELECT id FROM sales_request_items WHERE customer_request_item_id=?", (line["id"],)).fetchone()
                conn.execute("""
                    INSERT INTO procurement_requests
                    (sales_request_item_id, customer_request_item_id, inventory_item_id, client_id, department_id,
                     sales_request_id, category, requested_item, requested_qty, shortage_qty, procurement_status,
                     received_qty, pending_qty, responsible_person, blocked_reason, priority, due_date, client_informed,
                     notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(customer_request_item_id) DO UPDATE SET sales_request_item_id=excluded.sales_request_item_id,
                        inventory_item_id=excluded.inventory_item_id, client_id=excluded.client_id,
                        department_id=excluded.department_id, sales_request_id=excluded.sales_request_id,
                        category=excluded.category, requested_item=excluded.requested_item,
                        requested_qty=excluded.requested_qty, shortage_qty=excluded.shortage_qty,
                        procurement_status=excluded.procurement_status, received_qty=excluded.received_qty,
                        pending_qty=excluded.pending_qty, responsible_person=excluded.responsible_person,
                        blocked_reason=excluded.blocked_reason, priority=excluded.priority,
                        due_date=excluded.due_date, client_informed=excluded.client_informed,
                        notes=excluded.notes, updated_at=excluded.updated_at
                """, (
                    sri["id"] if sri else None, line["id"], line.get("inventory_item_id"), req["client_id"],
                    req["department_id"] if "department_id" in req.keys() else None, sales_request_id, line_category,
                    line.get("requested_item", ""), int(line.get("quantity") or 0), shortage,
                    line.get("procurement_status") or "not_ordered", int(line.get("delivered_qty") or 0),
                    max(0, shortage - int(line.get("delivered_qty") or 0)),
                    line.get("responsible_person") or (req["responsible_person"] if "responsible_person" in req.keys() else ""),
                    line.get("blocked_reason") or "none", req["priority"] if "priority" in req.keys() else "normal",
                    line.get("due_date") or (req["due_date"] if "due_date" in req.keys() else ""),
                    req["client_informed"] if "client_informed" in req.keys() else 0,
                    line.get("notes") or "", line.get("created_at") or now(), now(),
                ))
    engineer_names = set()
    for row in conn.execute("SELECT engineer FROM pm_assets WHERE COALESCE(engineer, '') != ''").fetchall():
        engineer_names.add(row["engineer"].strip())
    for row in conn.execute("SELECT engineer FROM service_calls WHERE COALESCE(engineer, '') != ''").fetchall():
        engineer_names.add(row["engineer"].strip())
    for row in conn.execute("SELECT assigned_to FROM pm_tasks WHERE COALESCE(assigned_to, '') != ''").fetchall():
        engineer_names.add(row["assigned_to"].strip())
    for name in sorted(n for n in engineer_names if n):
        conn.execute("""
            INSERT OR IGNORE INTO engineers (engineer_name, active, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, 1, "Discovered from ERP activity", now(), now()))

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

def service_hospital_follow_up_data(conn, client_id: int, department_id: int | None = None):
    client = crm_client_row(conn, client_id)
    hospital_name = client["name"]
    today = date.today()
    renewal_until = today + timedelta(days=90)
    dept_clause = " AND COALESCE(department_id, 0)=?" if department_id else ""
    dept_params = (department_id,) if department_id else ()

    upcoming_sales_deliveries = [dict(r) for r in conn.execute(f"""
        SELECT cr.id, cr.case_no, cr.client_hospital, cr.contact_person, cr.status,
               cr.updated_at, cr.notes,
               COUNT(cri.id) AS line_count,
               COALESCE(SUM(cri.quantity), 0) AS requested_qty,
               COALESCE(SUM(cri.delivered_qty), 0) AS delivered_qty,
               COALESCE(SUM(MAX(COALESCE(cri.quantity, 0) - COALESCE(cri.delivered_qty, 0), 0)), 0) AS pending_delivery_qty
        FROM customer_requests cr
        LEFT JOIN customer_request_items cri ON cri.request_id=cr.id
        WHERE cr.client_id=?
          {dept_clause}
          AND lower(COALESCE(cr.status, 'open')) NOT IN ('completed', 'invoiced', 'cancelled', 'closed')
        GROUP BY cr.id
        ORDER BY cr.updated_at DESC
        LIMIT 50
    """, (client_id, *dept_params)).fetchall()]

    calls_pending = [dict(r) for r in conn.execute(f"""
        SELECT s.*, a.asset_tag, a.model, a.serial_number, a.department
        FROM service_calls s
        LEFT JOIN pm_assets a ON a.id=s.equipment_id
        WHERE s.client_id=?
          {dept_clause}
          AND lower(COALESCE(s.status, 'open')) NOT IN ('closed', 'resolved', 'cancelled')
        ORDER BY COALESCE(s.opened_at, s.created_at) DESC
        LIMIT 50
    """, (client_id, *dept_params)).fetchall()]

    offers_pending = [dict(r) for r in conn.execute(f"""
        SELECT q.*, a.asset_tag, a.model, a.serial_number
        FROM quotations q
        LEFT JOIN pm_assets a ON a.id=q.equipment_id
        WHERE q.client_id=?
          {dept_clause}
          AND lower(COALESCE(q.status, 'draft')) IN ('draft', 'pending', 'open', 'sent', 'in_progress', 'follow_up', 'waiting_client_approval')
        ORDER BY COALESCE(q.quote_date, q.updated_at, q.created_at) DESC
        LIMIT 50
    """, (client_id, *dept_params)).fetchall()]

    contract_rows = [dict(r) for r in conn.execute("""
        SELECT MIN(a.id) AS equipment_id, a.client_id, a.hospital, a.contract_no,
               MIN(a.contract_start_date) AS contract_start_date,
               MAX(a.contract_end_date) AS contract_end_date,
               COUNT(*) AS equipment_count,
               GROUP_CONCAT(DISTINCT COALESCE(a.asset_tag, a.serial_number, a.model)) AS impacted_equipment
        FROM pm_assets a
        WHERE (a.client_id=? OR lower(trim(a.hospital))=lower(trim(?)))
          AND COALESCE(a.contract_no, '') != ''
        GROUP BY a.client_id, a.hospital, a.contract_no
        ORDER BY COALESCE(a.contract_end_date, ''), a.hospital, a.contract_no
    """, (client_id, hospital_name)).fetchall()]
    contract_renewals_pending = []
    for row in contract_rows:
        end = parse_iso_date(row.get("contract_end_date"))
        if end and end < today:
            status = "expired"
        elif end and end <= renewal_until:
            status = "renewal_pending"
        else:
            status = "active"
        row["renewal_status"] = status
        row["contract_id"] = contract_link_id(row.get("hospital", ""), row.get("contract_no", ""))
        if status in {"expired", "renewal_pending"}:
            contract_renewals_pending.append(row)

    fmi_impacted_equipment = [dict(r) for r in conn.execute("""
        SELECT r.id, 'recall' AS source, a.department_id, r.notice_type, r.notice_no, r.manufacturer,
               r.affected_serial_numbers, r.completion_status, r.corrective_actions AS corrective_action,
               r.notes, r.created_at, r.updated_at,
               a.id AS equipment_id, a.asset_tag, a.model, a.serial_number, a.department, a.next_pm_date, a.status AS pm_status
        FROM equipment_recall_notices r
        LEFT JOIN pm_assets a ON a.id=r.equipment_id
        WHERE r.client_id=?
          AND lower(COALESCE(r.completion_status, 'open')) NOT IN ('completed', 'closed', 'cancelled')
        UNION ALL
        SELECT f.id, 'fmi' AS source, f.department_id, f.notice_type, '' AS notice_no, f.manufacturer,
               f.affected_serial_numbers, f.completion_status, f.corrective_action,
               f.notes, f.created_at, f.updated_at,
               a.id AS equipment_id, a.asset_tag, a.model, a.serial_number, a.department, a.next_pm_date, a.status AS pm_status
        FROM fmi_recalls f
        LEFT JOIN pm_assets a ON a.id=f.equipment_id
        WHERE f.client_id=?
          AND lower(COALESCE(f.completion_status, 'open')) NOT IN ('completed', 'closed', 'cancelled')
        ORDER BY 12 DESC
        LIMIT 50
    """, (client_id, client_id)).fetchall()]
    if department_id:
        fmi_impacted_equipment = [
            row for row in fmi_impacted_equipment
            if row.get("department_id") == department_id
        ]

    equipment_pm_status = []
    for row in conn.execute("""
        SELECT a.*, c.name AS client_name
        FROM pm_assets a
        LEFT JOIN clients c ON c.id=a.client_id
        WHERE a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))
        ORDER BY COALESCE(a.next_pm_date, ''), a.department, a.asset_tag
        LIMIT 100
    """, (client_id, hospital_name)).fetchall():
        item = enrich_pm_asset(row)
        item["pm_status"] = item.get("timing_status")
        item["warranty_status"] = warranty_status(item.get("warranty_end", ""))
        if not department_id or item.get("department_id") == department_id:
            equipment_pm_status.append(item)

    return {
        "summary": {
            "upcoming_sales_deliveries": len(upcoming_sales_deliveries),
            "calls_pending": len(calls_pending),
            "offers_pending": len(offers_pending),
            "contract_renewals_pending": len(contract_renewals_pending),
            "fmi_impacted_equipment": len(fmi_impacted_equipment),
            "pm_due": sum(1 for item in equipment_pm_status if item.get("timing_status") in {"due_today", "due_this_week", "overdue"}),
            "pm_overdue": sum(1 for item in equipment_pm_status if item.get("timing_status") == "overdue"),
        },
        "upcoming_sales_deliveries": upcoming_sales_deliveries,
        "calls_pending": calls_pending,
        "offers_pending": offers_pending,
        "contract_renewals_pending": contract_renewals_pending,
        "fmi_impacted_equipment": fmi_impacted_equipment,
        "equipment_pm_status": equipment_pm_status,
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

def normalize_sales_category(value: str = "") -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"accessory", "accessories"}:
        return "accessories"
    if text in {"new_equipment", "equipment", "machine", "machines"}:
        return "equipment"
    if text in {"service", "labor", "pm", "preventive_maintenance", "maintenance_contract", "calibration"}:
        return "service"
    return "spare_parts"

def sales_category_for_lines(lines: list[dict], case_type: str = "") -> str:
    types = {normalize_sales_category(line.get("item_type", "")) for line in lines}
    if "equipment" in types or case_type in {"equipment_delivery", "installation"}:
        return "equipment"
    if "accessories" in types or case_type == "accessories_sale":
        return "accessories"
    if "service" in types or case_type in {"corrective_maintenance", "preventive_maintenance", "maintenance_contract", "calibration"}:
        return "service"
    return "spare_parts"

def progress_for_case(case_row: dict, docs: list[dict], lines: list[dict]) -> dict:
    doc_types = {d.get("doc_type") for d in docs}
    line_statuses = {l.get("stock_status") for l in lines}
    procurement_statuses = {l.get("procurement_status") for l in lines}
    case_type = case_row.get("case_type", "")
    if case_type in {"corrective_maintenance", "warranty_call", "training"}:
        stages = [
            ("call received", True),
            ("assigned", bool(case_row.get("engineer_id"))),
            ("scheduled", case_row.get("workflow_state") in {"appointment_or_workshop_pickup", "service_visit", "service_report", "accountant_notified_for_invoice", "customer_satisfaction_follow_up"}),
            ("visited", case_row.get("workflow_state") in {"service_visit", "service_report", "accountant_notified_for_invoice", "customer_satisfaction_follow_up"}),
            ("report submitted", "service_report" in doc_types),
            ("invoiced/closed", "invoice" in doc_types or case_row.get("status") in {"completed", "closed"}),
        ]
    elif case_type in {"preventive_maintenance", "maintenance_contract"}:
        stages = [
            ("scheduled", case_row.get("workflow_state") in {"pm_scheduled", "engineer_notified", "appointment_set", "checklist_prepared", "pm_done", "service_report_signed", "checklist_archived"}),
            ("assigned", bool(case_row.get("engineer_id"))),
            ("checklist prepared", case_row.get("workflow_state") in {"checklist_prepared", "pm_done", "service_report_signed", "checklist_archived"}),
            ("completed", case_row.get("workflow_state") in {"pm_done", "service_report_signed", "checklist_archived"}),
            ("report signed", "pm_report" in doc_types),
            ("archived", case_row.get("workflow_state") == "checklist_archived"),
        ]
    elif case_type in {"equipment_delivery", "installation"}:
        stages = [
            ("delivery planned", case_row.get("workflow_state") in {"upcoming_delivery", "shipment_ready", "site_readiness_follow_up", "delivery_order", "customer_appointment", "physical_delivery", "installation", "functional_test", "service_report", "equipment_registration"}),
            ("delivered", "delivery_note" in doc_types or case_row.get("workflow_state") in {"physical_delivery", "installation", "functional_test", "service_report", "equipment_registration"}),
            ("installed", case_row.get("workflow_state") in {"installation", "functional_test", "service_report", "equipment_registration"}),
            ("tested", "acceptance_test_report" in doc_types or case_row.get("workflow_state") in {"functional_test", "service_report", "equipment_registration"}),
            ("accepted", "acceptance_test_report" in doc_types or case_row.get("workflow_state") == "equipment_registration"),
            ("warranty active", case_row.get("workflow_state") == "equipment_registration"),
        ]
    elif any(l.get("item_type") in {"spare_part", "accessory"} for l in lines):
        stages = [
            ("request", True),
            ("stock check", bool(lines)),
            ("reserved/shortage", bool(line_statuses & {"reserved", "partially_reserved", "available", "partially_available", "unavailable"})),
            ("PO created", bool(procurement_statuses & {"po_draft", "po_sent", "supplier_confirmed", "partially_received", "received"})),
            ("received", "received" in procurement_statuses),
            ("delivered", "delivery_note" in doc_types or "delivered" in line_statuses),
            ("invoiced", "invoice" in doc_types or "invoiced" in line_statuses),
        ]
    else:
        stages = [
            ("request", True),
            ("quotation", "quotation" in doc_types),
            ("approval", case_row.get("workflow_state") in {"deal_closed", "delivery_coordination", "installation_follow_up"} or "client_order" in doc_types),
            ("client order", "client_order" in doc_types),
            ("delivery", "delivery_note" in doc_types),
            ("invoice", "invoice" in doc_types),
            ("paid", any(str(d.get("status", "")).lower() == "paid" for d in docs if d.get("doc_type") == "invoice")),
        ]
    done = sum(1 for _, ok in stages if ok)
    current_stage = next((label for label, ok in reversed(stages) if ok), stages[0][0] if stages else "")
    next_action = next((label for label, ok in stages if not ok), "complete")
    return {
        "stages": [{"label": label, "done": bool(ok)} for label, ok in stages],
        "percent": round((done / len(stages)) * 100) if stages else 0,
        "current_stage": current_stage,
        "next_action": next_action,
        "stage_count": len(stages),
        "completed_stages": done,
    }

def parent_reference_groups(conn, client_id: int | None = None, department_id: int | None = None):
    where = ["COALESCE(parent_case_reference, '') != ''"]
    params = []
    if client_id:
        where.append("client_id=?")
        params.append(client_id)
    if department_id:
        where.append("department_id=?")
        params.append(department_id)
    cases = [dict(r) for r in conn.execute(f"""
        SELECT * FROM cases
        WHERE {' AND '.join(where)}
        ORDER BY updated_at DESC, id DESC
    """, params).fetchall()]
    groups = []
    for case_row in cases:
        ref = case_row.get("parent_case_reference")
        request_id = case_row.get("request_id")
        docs = [dict(r) for r in conn.execute("SELECT * FROM sales_case_documents WHERE parent_case_reference=? ORDER BY created_at", (ref,)).fetchall()]
        lines = [dict(r) for r in conn.execute("""
            SELECT cri.*
            FROM customer_request_items cri
            JOIN customer_requests cr ON cr.id=cri.request_id
            WHERE cr.parent_case_reference=?
            ORDER BY cri.id
        """, (ref,)).fetchall()]
        timeline = [dict(r) for r in conn.execute("""
            SELECT * FROM case_timeline
            WHERE parent_case_reference=?
            ORDER BY created_at, id
        """, (ref,)).fetchall()]
        if not timeline:
            request_row = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone() if request_id else None
            if request_row:
                timeline.append({"event_type": "case_created", "title": "Customer request created", "status": request_row["status"], "created_at": request_row["created_at"], "notes": request_row["notes"]})
            for doc in docs:
                timeline.append({"event_type": "document_created", "title": doc["doc_type"].replace("_", " ").title(), "status": doc["status"], "created_at": doc["created_at"], "notes": doc["doc_no"]})
        groups.append({
            "parent_case_reference": ref,
            "case_id": case_row.get("id"),
            "case_no": case_row.get("case_no"),
            "case_type": case_row.get("case_type"),
            "status": case_row.get("status"),
            "workflow_state": case_row.get("workflow_state"),
            "priority": case_row.get("priority"),
            "blocked_reason": case_row.get("blocked_reason") or "none",
            "blocked_notes": case_row.get("blocked_notes") or "",
            "responsible_person": case_row.get("responsible_person") or "",
            "due_date": case_row.get("due_date") or "",
            "external_reference": case_row.get("external_reference") or "",
            "last_update": case_row.get("updated_at") or "",
            "request_id": request_id,
            "department_id": case_row.get("department_id"),
            "documents": docs,
            "line_items": lines,
            "timeline": timeline,
            "progress": progress_for_case(case_row, docs, lines),
        })
    return groups

def case_progress_items(conn, client_id: int, department_id: int | None = None):
    items = []
    for group in parent_reference_groups(conn, client_id, department_id):
        progress = group.get("progress") or {}
        items.append({
            "parent_case_reference": group.get("parent_case_reference"),
            "external_reference": group.get("external_reference"),
            "case_id": group.get("case_id"),
            "case_no": group.get("case_no"),
            "case_type": group.get("case_type"),
            "status": group.get("status"),
            "workflow_state": group.get("workflow_state"),
            "department_id": group.get("department_id"),
            "percent": progress.get("percent", 0),
            "current_stage": progress.get("current_stage", ""),
            "next_action": progress.get("next_action", ""),
            "blocked_reason": group.get("blocked_reason") or "none",
            "responsible_person": group.get("responsible_person") or "",
            "due_date": group.get("due_date") or "",
            "last_update": group.get("last_update") or "",
        })
    return items

def blocked_item_rows(conn, client_id: int | None = None, department_id: int | None = None, limit: int = 200):
    sources = []
    filters = []
    params = []
    if client_id:
        filters.append("client_id=?")
        params.append(client_id)
    if department_id:
        filters.append("department_id=?")
        params.append(department_id)
    where = " AND ".join(filters)
    if where:
        where = " AND " + where
    queries = [
        ("case", "cases", "case_no", "notes", "updated_at"),
        ("request", "customer_requests", "case_no", "notes", "updated_at"),
        ("quotation", "quotations", "quotation_no", "notes", "updated_at"),
        ("client_order", "client_orders", "client_order_no", "notes", "updated_at"),
        ("purchase_order", "purchase_orders", "po_no", "notes", "updated_at"),
        ("service_call", "service_calls", "call_no", "issue", "updated_at"),
        ("pm_task", "pm_tasks", "task_name", "notes", "updated_at"),
        ("equipment", "pm_assets", "asset_tag", "notes", "updated_at"),
        ("delivery", "delivery_notes", "doc_no", "notes", "updated_at"),
        ("invoice", "invoices", "doc_no", "notes", "updated_at"),
    ]
    for item_type, table, label_col, notes_col, date_col in queries:
        table_cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if not {"blocked_reason", label_col}.issubset(table_cols):
            continue
        local_filters = []
        local_params = []
        if client_id and "client_id" in table_cols:
            local_filters.append("client_id=?")
            local_params.append(client_id)
        if department_id and "department_id" in table_cols:
            local_filters.append("department_id=?")
            local_params.append(department_id)
        local_where = (" AND " + " AND ".join(local_filters)) if local_filters else ""
        parent_expr = "COALESCE(parent_case_reference, '')" if "parent_case_reference" in table_cols else "''"
        client_expr = "COALESCE(client_id, '')" if "client_id" in table_cols else "''"
        department_expr = "COALESCE(department_id, '')" if "department_id" in table_cols else "''"
        notes_expr = f"COALESCE({notes_col}, '')" if notes_col in table_cols else "''"
        updated_expr = f"COALESCE({date_col}, created_at)" if date_col in table_cols and "created_at" in table_cols else (date_col if date_col in table_cols else "''")
        rows = conn.execute(f"""
            SELECT id, {label_col} AS label,
                   {parent_expr} AS parent_case_reference,
                   {client_expr} AS client_id,
                   {department_expr} AS department_id,
                   COALESCE(blocked_reason, 'none') AS blocked_reason,
                   COALESCE(blocked_notes, '') AS blocked_notes,
                   {notes_expr} AS notes,
                   {updated_expr} AS updated_at
            FROM {table}
            WHERE COALESCE(blocked_reason, 'none') NOT IN ('', 'none') {local_where}
            ORDER BY updated_at DESC
            LIMIT ?
        """, [*local_params, limit]).fetchall()
        for row in rows:
            sources.append({"type": item_type, **dict(row)})
    sources.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return sources[:limit]

def department_progress_rows(conn, client_id: int):
    client = crm_client_row(conn, client_id)
    departments = [dict(r) for r in conn.execute("SELECT * FROM departments WHERE client_id=? ORDER BY department_name", (client_id,)).fetchall()]
    rows = []
    today = date.today()
    for dept in departments:
        dept_id = dept["id"]
        equipment = [dict(r) for r in conn.execute("""
            SELECT * FROM pm_assets
            WHERE (client_id=? OR lower(trim(hospital))=lower(trim(?))) AND department_id=?
        """, (client_id, client["name"], dept_id)).fetchall()]
        equipment_ids = [e["id"] for e in equipment]
        placeholders = ",".join("?" for _ in equipment_ids) or "NULL"
        pm_tasks = [dict(r) for r in conn.execute(f"""
            SELECT * FROM pm_tasks
            WHERE department_id=? OR asset_id IN ({placeholders})
        """, [dept_id, *equipment_ids]).fetchall()]
        service_calls = [dict(r) for r in conn.execute(f"""
            SELECT * FROM service_calls
            WHERE client_id=? AND (department_id=? OR equipment_id IN ({placeholders}))
        """, [client_id, dept_id, *equipment_ids]).fetchall()]
        cases = [dict(r) for r in conn.execute("SELECT * FROM cases WHERE client_id=? AND department_id=?", (client_id, dept_id)).fetchall()]
        pending_installations = sum(
            1 for c in cases
            if c.get("case_type") in {"installation", "equipment_delivery"}
            and str(c.get("status", "")).lower() not in {"closed", "completed", "cancelled", "delivered"}
        )
        pm_due = sum(1 for e in equipment if pm_timing_status(e.get("next_pm_date", ""), e.get("status", "")) in {"due_today", "due_this_week"})
        pm_overdue = sum(1 for e in equipment if pm_timing_status(e.get("next_pm_date", ""), e.get("status", "")) == "overdue")
        pm_completed = sum(1 for t in pm_tasks if str(t.get("status", "")).lower() in {"completed", "closed"})
        open_calls = sum(1 for s in service_calls if str(s.get("status", "")).lower() not in {"closed", "resolved", "cancelled"})
        warranty_active = sum(1 for e in equipment if warranty_status(e.get("warranty_end", "")) in {"active", "expiring_soon"})
        contract_active = sum(1 for e in equipment if e.get("contract_no") and (not parse_iso_date(e.get("contract_end_date")) or parse_iso_date(e.get("contract_end_date")) >= today))
        blocked_items = len(blocked_item_rows(conn, client_id, dept_id, 500))
        total_signals = len(equipment) + len(cases) + len(service_calls) + len(pm_tasks)
        risk = pm_overdue + open_calls + pending_installations + blocked_items
        percent = 100 if total_signals == 0 else max(0, min(100, round(((total_signals - risk) / max(total_signals, 1)) * 100)))
        if blocked_items or pm_overdue:
            progress_status = "blocked" if blocked_items else "overdue"
        elif open_calls or pending_installations or pm_due:
            progress_status = "in_progress"
        else:
            progress_status = "healthy"
        rows.append({
            **dept,
            "equipment_count": len(equipment),
            "pm_due": pm_due,
            "pm_completed": pm_completed,
            "pm_overdue": pm_overdue,
            "open_service_calls": open_calls,
            "pending_installations": pending_installations,
            "active_warranty_equipment": warranty_active,
            "active_contract_coverage": contract_active,
            "blocked_items": blocked_items,
            "overall_progress_percent": percent,
            "overall_progress_status": progress_status,
        })
    return rows

def equipment_detail_data(conn, equipment_id: int):
    eq = conn.execute("""
        SELECT e.*, a.*, c.name AS client_name, d.department_name,
               w.warranty_start, w.warranty_end, w.status AS warranty_status
        FROM equipment e
        LEFT JOIN pm_assets a ON a.id=e.pm_asset_id
        LEFT JOIN clients c ON c.id=e.client_id
        LEFT JOIN departments d ON d.id=e.department_id
        LEFT JOIN warranties w ON w.equipment_id=e.id
        WHERE e.id=?
    """, (equipment_id,)).fetchone()
    if not eq:
        raise HTTPException(status_code=404, detail="Equipment not found")
    data = dict(eq)
    pm_asset_id = data.get("pm_asset_id") or equipment_id
    data["service_history"] = [dict(r) for r in conn.execute("""
        SELECT * FROM service_calls
        WHERE equipment_id=? OR equipment_id=?
        ORDER BY COALESCE(opened_at, created_at) DESC
    """, (equipment_id, pm_asset_id)).fetchall()]
    data["pm_history"] = [dict(r) for r in conn.execute("SELECT * FROM pm_history WHERE asset_id=? ORDER BY created_at DESC", (pm_asset_id,)).fetchall()]
    data["pm_tasks"] = [dict(r) for r in conn.execute("SELECT * FROM pm_tasks WHERE asset_id=? ORDER BY COALESCE(due_date, ''), id DESC", (pm_asset_id,)).fetchall()]
    data["calibration_history"] = [dict(r) for r in conn.execute("SELECT * FROM equipment_calibrations WHERE equipment_id=? ORDER BY COALESCE(calibration_date, created_at) DESC", (pm_asset_id,)).fetchall()]
    data["fmi_recall_notices"] = [dict(r) for r in conn.execute("SELECT * FROM equipment_recall_notices WHERE equipment_id=? ORDER BY updated_at DESC", (pm_asset_id,)).fetchall()]
    data["installation_reports"] = [dict(r) for r in conn.execute("SELECT * FROM installation_reports WHERE equipment_id=? ORDER BY updated_at DESC", (pm_asset_id,)).fetchall()]
    data["acceptance_testing_reports"] = [dict(r) for r in conn.execute("SELECT * FROM acceptance_testing_forms WHERE equipment_id=? ORDER BY updated_at DESC", (pm_asset_id,)).fetchall()]
    return data

def traceability_data(conn, reference: str):
    ref = str(reference or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="reference is required")
    case_row = conn.execute("""
        SELECT * FROM cases
        WHERE parent_case_reference=? OR case_no=?
        ORDER BY id DESC LIMIT 1
    """, (ref, ref)).fetchone()
    if not case_row:
        doc = conn.execute("""
            SELECT parent_case_reference FROM sales_case_documents
            WHERE doc_no=? OR document_reference=?
            UNION SELECT parent_case_reference FROM quotations WHERE quotation_no=? OR document_reference=?
            UNION SELECT parent_case_reference FROM client_orders WHERE client_order_no=? OR document_reference=?
            UNION SELECT parent_case_reference FROM purchase_orders WHERE po_no=? OR document_reference=?
            LIMIT 1
        """, (ref, ref, ref, ref, ref, ref, ref, ref)).fetchone()
        if doc and doc["parent_case_reference"]:
            ref = doc["parent_case_reference"]
            case_row = conn.execute("SELECT * FROM cases WHERE parent_case_reference=? ORDER BY id DESC LIMIT 1", (ref,)).fetchone()
    if not case_row:
        raise HTTPException(status_code=404, detail="Parent case reference not found")
    case_data = dict(case_row)
    parent_ref = case_data.get("parent_case_reference")
    request_ids = [r["id"] for r in conn.execute("SELECT id FROM customer_requests WHERE parent_case_reference=?", (parent_ref,)).fetchall()]
    request_placeholders = ",".join("?" for _ in request_ids) or "NULL"
    customer_requests = [request_with_lines(conn, rid) for rid in request_ids]
    documents = [dict(r) for r in conn.execute("SELECT * FROM sales_case_documents WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    quotations = [dict(r) for r in conn.execute("SELECT * FROM quotations WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    client_orders = [dict(r) for r in conn.execute("SELECT * FROM client_orders WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    purchase_orders = [dict(r) for r in conn.execute("SELECT * FROM purchase_orders WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    stock_movements = [dict(r) for r in conn.execute(f"""
        SELECT * FROM stock_movements
        WHERE parent_case_reference=?
           OR request_id IN ({request_placeholders})
        ORDER BY created_at
    """, [parent_ref, *request_ids]).fetchall()]
    service_calls = [dict(r) for r in conn.execute("SELECT * FROM service_calls WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    pm_reports = [dict(r) for r in conn.execute("SELECT * FROM pm_reports WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    service_reports = [dict(r) for r in conn.execute("SELECT * FROM service_reports WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    delivery_notes = [dict(r) for r in conn.execute("SELECT * FROM delivery_notes WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    invoices = [dict(r) for r in conn.execute("SELECT * FROM invoices WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    contracts = [dict(r) for r in conn.execute("SELECT * FROM contracts WHERE parent_case_reference=? ORDER BY created_at", (parent_ref,)).fetchall()]
    equipment_history = [dict(r) for r in conn.execute("""
        SELECT h.*, a.asset_tag, a.model, a.serial_number
        FROM pm_history h
        LEFT JOIN pm_assets a ON a.id=h.asset_id
        WHERE h.parent_case_reference=?
           OR a.parent_case_reference=?
        ORDER BY h.created_at
    """, (parent_ref, parent_ref)).fetchall()]
    engineer_activities = [dict(r) for r in conn.execute("""
        SELECT 'service_call' AS activity_type, call_no AS reference, engineer, status, issue AS notes, updated_at AS activity_at
        FROM service_calls WHERE parent_case_reference=?
        UNION ALL
        SELECT 'pm_history' AS activity_type, a.asset_tag AS reference, h.engineer, h.action AS status, h.notes, h.created_at AS activity_at
        FROM pm_history h LEFT JOIN pm_assets a ON a.id=h.asset_id
        WHERE h.parent_case_reference=?
        ORDER BY activity_at
    """, (parent_ref, parent_ref)).fetchall()]
    timeline = [dict(r) for r in conn.execute("SELECT * FROM case_timeline WHERE parent_case_reference=? ORDER BY created_at, id", (parent_ref,)).fetchall()]
    return {
        "parent_case_reference": parent_ref,
        "case": case_data,
        "timeline": timeline,
        "customer_requests": customer_requests,
        "offers": quotations,
        "quotations": quotations,
        "client_orders": client_orders,
        "purchase_orders": purchase_orders,
        "stock_reservations": [line for req in customer_requests for line in req.get("lines", []) if int(line.get("reserved_qty") or 0) > 0],
        "stock_movements": stock_movements,
        "deliveries": delivery_notes,
        "delivery_notes": delivery_notes,
        "invoices": invoices,
        "service_reports": service_reports,
        "pm_reports": pm_reports,
        "engineer_activities": engineer_activities,
        "contracts": contracts,
        "equipment_history": equipment_history,
        "documents": documents,
    }

def crm_client_dashboard_data(conn, client_id: int, department_id: int | None = None):
    client = crm_client_row(conn, client_id)
    metrics = crm_client_metrics(conn, client)
    departments = [dict(r) for r in conn.execute("SELECT * FROM client_departments WHERE client_id=? ORDER BY department_name", (client_id,)).fetchall()]
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
    purchase_orders = [dict(r) for r in conn.execute("""
        SELECT * FROM purchase_orders
        WHERE client_id=?
           OR request_id IN (SELECT id FROM customer_requests WHERE client_id=?)
           OR case_id IN (SELECT id FROM cases WHERE client_id=?)
        ORDER BY updated_at DESC
    """, (client_id, client_id, client_id)).fetchall()]
    cases = [dict(r) for r in conn.execute("""
        SELECT * FROM cases
        WHERE client_id=?
        ORDER BY updated_at DESC, id DESC
    """, (client_id,)).fetchall()]
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
    all_equipment = list(equipment)
    all_requests = list(requests)
    all_service_calls = list(service_calls)
    all_pending_items = list(pending_items)
    if department_id:
        equipment_ids = {e["id"] for e in equipment if e.get("department_id") == department_id}
        request_ids = {r["id"] for r in requests if r.get("department_id") == department_id}
        equipment = [e for e in equipment if e.get("department_id") == department_id]
        requests = [r for r in requests if r.get("department_id") == department_id]
        orders = [o for o in orders if o.get("department_id") in {department_id, None, ""} and (not o.get("request_id") or o.get("request_id") in request_ids)]
        purchase_orders = [p for p in purchase_orders if p.get("department_id") == department_id or p.get("request_id") in request_ids]
        cases = [c for c in cases if c.get("department_id") == department_id]
        docs = [d for d in docs if d.get("department_id") == department_id or d.get("request_id") in request_ids]
        offers = [o for o in offers if o.get("department_id") == department_id or o.get("request_id") in request_ids]
        service_calls = [s for s in service_calls if s.get("department_id") == department_id or s.get("equipment_id") in equipment_ids or s.get("request_id") in request_ids]
        equipment_history = [h for h in equipment_history if h.get("asset_id") in equipment_ids]
        engineer_activities = [a for a in engineer_activities if a.get("equipment_id") in equipment_ids or a.get("request_id") in request_ids]
        pending_items = [p for p in pending_items if p.get("request_id") in request_ids]
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
    department_summaries = []
    for dept in departments:
        dept_id = dept["id"]
        dept_equipment = [e for e in all_equipment if e.get("department_id") == dept_id]
        dept_equipment_ids = {e["id"] for e in dept_equipment}
        dept_requests = [r for r in all_requests if r.get("department_id") == dept_id]
        dept_request_ids = {r["id"] for r in dept_requests}
        department_summaries.append({
            **dept,
            "equipment_count": len(dept_equipment),
            "warranty_machines": sum(1 for e in dept_equipment if warranty_status(e.get("warranty_end", "")) in {"active", "expiring_soon"}),
            "pm_due": sum(1 for e in dept_equipment if pm_timing_status(e.get("next_pm_date", ""), e.get("status", "")) in {"due_today", "due_this_week", "overdue"}),
            "open_service_calls": sum(1 for s in all_service_calls if s.get("department_id") == dept_id or s.get("equipment_id") in dept_equipment_ids),
            "pending_spare_parts": sum(1 for p in all_pending_items if p.get("request_id") in dept_request_ids and p.get("item_type") == "spare_part"),
        })
    department_progress = department_progress_rows(conn, client_id)
    if department_id:
        department_progress = [d for d in department_progress if d.get("id") == department_id]
    blocked_items = blocked_item_rows(conn, client_id, department_id, 200)
    parent_timelines = parent_reference_groups(conn, client_id, department_id)
    progress_items = case_progress_items(conn, client_id, department_id)
    sales_spare_parts = [p for p in pending_items if p.get("item_type") == "spare_part"]
    sales_accessories = [p for p in pending_items if p.get("item_type") == "accessory"]
    sales_new_equipment = [r for r in requests if any((line.get("item_type") == "new_equipment") for line in request_with_lines(conn, r["id"]).get("lines", []))] if requests else []
    open_cases = [c for c in cases if str(c.get("status", "")).lower() not in {"completed", "closed", "cancelled"}]
    active_contracts = [dict(c) for c in conn.execute("SELECT * FROM contracts WHERE client_id=? AND lower(COALESCE(status, 'active')) NOT IN ('expired', 'cancelled', 'closed') ORDER BY updated_at DESC", (client_id,)).fetchall()]
    warranty_rows = [dict(r) for r in conn.execute("SELECT * FROM warranties WHERE client_id=? ORDER BY COALESCE(warranty_end, '') DESC", (client_id,)).fetchall()]
    fmi_rows = [dict(r) for r in conn.execute("SELECT * FROM equipment_recall_notices WHERE client_id=? ORDER BY updated_at DESC", (client_id,)).fetchall()]
    delivery_rows = [d for d in docs if d.get("doc_type") in {"delivery_note", "installation_report", "acceptance_test_report"}]
    notes_rows = [dict(r) for r in conn.execute("SELECT * FROM crm_communications WHERE client_id=? ORDER BY created_at DESC LIMIT 50", (client_id,)).fetchall()]
    service_follow_up = service_hospital_follow_up_data(conn, client_id, department_id)
    return {
        "client": {**client, **metrics},
        "departments": departments,
        "department_summaries": department_summaries,
        "department_progress": department_progress,
        "active_department_id": department_id,
        "parent_timelines": parent_timelines,
        "progress_items": progress_items,
        "blocked_items": blocked_items,
        "contacts": contacts,
        "equipment": equipment,
        "offers": offers,
        "documents": docs,
        "requests": requests,
        "cases": cases,
        "orders": orders,
        "purchase_orders": purchase_orders,
        "service_calls": service_calls,
        "engineer_activities": engineer_activities,
        "equipment_history": equipment_history,
        "pending_items": pending_items,
        "financials": financials,
        "sales": {
            "spare_parts": sales_spare_parts,
            "accessories": sales_accessories,
            "prospects_leads": [r for r in requests if str(r.get("status", "")).lower() in {"open", "pending", "lead"}],
            "new_equipment": sales_new_equipment,
            "eol_eosl": [e for e in equipment if str(e.get("status", "")).lower() in {"eol", "eosl", "retired"} or str(e.get("lifecycle_status", "")).lower() in {"eol", "eosl", "retired"}],
        },
        "after_sales": {
            "equipment": equipment,
            "pm": [dict(r) for r in conn.execute("""
                SELECT t.*, a.asset_tag, a.hospital, a.department, a.model, a.serial_number
                FROM pm_tasks t LEFT JOIN pm_assets a ON a.id=t.asset_id
                WHERE a.client_id=? OR lower(trim(a.hospital))=lower(trim(?))
                ORDER BY COALESCE(t.due_date, ''), t.status
            """, (client_id, client["name"])).fetchall()],
            "contracts": active_contracts,
            "warranties": warranty_rows,
            "fmi_recall": fmi_rows,
            "installation_delivery": delivery_rows,
            "service_calls_reports": service_calls,
        },
        "client_operations": {
            "financial_status": financials,
            "pending_payments": unpaid_invoices,
            "invoices": invoices,
            "client_communication": notes_rows,
            "client_availability": [b for b in blocked_items if "customer" in str(b.get("blocked_reason", "")).lower() or "availability" in str(b.get("blocked_reason", "")).lower()],
            "approval_status": [r for r in requests if str(r.get("status", "")).lower() in {"pending", "approved", "rejected", "waiting_client_approval"}],
            "blocked_items": blocked_items,
            "escalations": [c for c in open_cases if str(c.get("priority", "")).lower() in {"urgent", "high", "critical"} or (c.get("blocked_reason") or "none") != "none"],
            "satisfaction": [n for n in notes_rows if "satisfaction" in str(n.get("type", "")).lower() or "satisfaction" in str(n.get("note", "")).lower()],
        },
        "service_follow_up": service_follow_up,
        "timeline": [event for group in parent_timelines for event in group.get("timeline", [])],
        "notes": notes_rows,
        "counts": {
            "offers": offer_counts,
            "requests": request_counts,
            "orders": order_counts,
            "cases_open": sum(1 for c in cases if str(c.get("status", "")).lower() not in {"completed", "closed", "cancelled"}),
            "pending_procurement": sum(1 for p in purchase_orders if str(p.get("status", "")).lower() not in {"received", "closed", "cancelled"}),
            "service_open": sum(1 for c in service_calls if str(c.get("status", "")).lower() not in {"closed", "resolved", "cancelled"}),
            "pm_due": sum(1 for e in equipment if pm_timing_status(e.get("next_pm_date", ""), e.get("status", "")) in {"due_today", "due_this_week", "overdue"}),
            "pm_overdue": sum(1 for e in equipment if pm_timing_status(e.get("next_pm_date", ""), e.get("status", "")) == "overdue"),
            "warranty_equipment": sum(1 for e in equipment if warranty_status(e.get("warranty_end", "")) in {"active", "expiring_soon"}),
            "contract_covered_equipment": sum(1 for e in equipment if e.get("contract_no")),
            "blocked_items": len(blocked_items),
            "urgent_items": sum(1 for c in open_cases if str(c.get("priority", "")).lower() in {"urgent", "high", "critical"}),
            "pending_installations_deliveries": sum(1 for c in cases if c.get("case_type") in {"installation", "equipment_delivery"} and str(c.get("status", "")).lower() not in {"completed", "closed", "cancelled"}),
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
    delivery_installation = [dict(r) for r in conn.execute("""
        SELECT b.*, c.name AS client_name
        FROM equipment_bids b
        LEFT JOIN clients c ON c.id=b.client_id
        WHERE lower(COALESCE(b.installation_status, 'pending')) NOT IN ('completed', 'registered', 'cancelled')
           OR lower(COALESCE(b.acceptance_status, 'pending')) NOT IN ('completed', 'accepted', 'cancelled')
        ORDER BY b.updated_at DESC
        LIMIT 20
    """).fetchall()]
    calibrations = [dict(r) for r in conn.execute("""
        SELECT cal.*, a.asset_tag, a.model, a.serial_number, c.name AS client_name
        FROM equipment_calibrations cal
        LEFT JOIN pm_assets a ON a.id=cal.equipment_id
        LEFT JOIN clients c ON c.id=cal.client_id
        WHERE COALESCE(cal.next_due_date, '') = ''
           OR cal.next_due_date <= ?
        ORDER BY COALESCE(cal.next_due_date, ''), cal.updated_at DESC
        LIMIT 20
    """, ((today + timedelta(days=30)).isoformat(),)).fetchall()]
    recalls = [dict(r) for r in conn.execute("""
        SELECT r.*, a.asset_tag, a.model, a.serial_number, c.name AS client_name
        FROM equipment_recall_notices r
        LEFT JOIN pm_assets a ON a.id=r.equipment_id
        LEFT JOIN clients c ON c.id=r.client_id
        WHERE lower(COALESCE(r.completion_status, 'open')) NOT IN ('completed', 'closed', 'cancelled')
        ORDER BY r.updated_at DESC
        LIMIT 20
    """).fetchall()]
    case_pipeline = [dict(r) for r in conn.execute("""
        SELECT cases.*, c.name AS client_name
        FROM cases
        LEFT JOIN clients c ON c.id=cases.client_id
        WHERE lower(COALESCE(cases.status, 'open')) NOT IN ('completed', 'closed', 'cancelled')
        ORDER BY cases.updated_at DESC
        LIMIT 30
    """).fetchall()]
    return {
        "metrics": {
            "open_service_calls": len(service_calls),
            "pm_visits_due": len(pm_due),
            "active_contracts": len(active_contracts),
            "expiring_contracts": len(expiring_contracts),
            "reports_pending": len(report_rows),
            "engineer_workload": sum(w["total"] for w in workload.values()),
            "warranty_equipment_needing_pm": len(warranty_pm),
            "delivery_installations": len(delivery_installation),
            "calibrations_due": len(calibrations),
            "open_recalls_fmi": len(recalls),
            "open_cases": len(case_pipeline),
        },
        "case_pipeline": case_pipeline,
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
        "delivery_installation": delivery_installation,
        "calibrations": calibrations,
        "recalls": recalls,
        "reports_pending": report_rows,
        "engineer_workload": sorted(workload.values(), key=lambda item: item["total"], reverse=True),
        "hospital_crm": hospital_dashboard_rows(conn),
        "warranty_pm": warranty_pm[:20],
        "submodules": [
            {"name": "Hospital CRM", "path": "/aftersales/hospital-crm", "existing_route": "/crm", "description": "Hospital follow-up for pending calls, offers, deliveries, contract renewals, FMI impact, and PM status."},
            {"name": "Dashboard", "path": "/aftersales", "existing_route": "/aftersales", "description": "Unified workload, case pipeline, service, PM, delivery, calibration, and recall overview."},
            {"name": "Service Calls", "path": "/aftersales/service-calls", "existing_route": "/crm", "description": "Corrective maintenance, labor, spare parts + installation, assignments, statuses, and service history."},
            {"name": "PM Tracking", "path": "/aftersales/pm", "existing_route": "/aftersales/pm", "description": "Schedules, due lists, completed PMs, engineer assignment, PM reports, and warranty PM tracking."},
            {"name": "Contracts", "path": "/aftersales/contracts", "existing_route": "/aftersales/contracts", "description": "Maintenance contracts, warranty contracts, covered equipment, dates, and status."},
            {"name": "Delivery & Installation", "path": "/aftersales/delivery-installation", "existing_route": "/equipment-registry", "description": "Delivery readiness, reception, physical delivery, installation, acceptance testing, and equipment registration."},
            {"name": "Calibration", "path": "/aftersales/calibration", "existing_route": "/equipment-registry/calibration", "description": "Calibration history, due dates, certificates, standards used, and results."},
            {"name": "FMI / Recall", "path": "/aftersales/fmi-recall", "existing_route": "/equipment-registry/recalls", "description": "Manufacturer notices, affected models and serials, corrective actions, and completion status."},
            {"name": "Reports", "path": "/aftersales/reports", "existing_route": "/aftersales/pm/reports", "description": "Service, PM, engineer, client, and equipment history reports."},
        ],
    }

def hospital_dashboard_rows(conn):
    ensure_clients_from_existing_data(conn)
    clients = [dict(r) for r in conn.execute("SELECT * FROM clients ORDER BY name").fetchall()]
    rows = []
    today = date.today()
    month_end = today + timedelta(days=30)
    for client in clients:
        client_id = client["id"]
        name = client["name"]
        metrics = crm_client_metrics(conn, client)
        open_cases = conn.execute("""
            SELECT COUNT(*) AS c FROM cases
            WHERE client_id=? AND lower(COALESCE(status, 'open')) NOT IN ('completed', 'closed', 'cancelled')
        """, (client_id,)).fetchone()["c"]
        pending_calls = conn.execute("""
            SELECT COUNT(*) AS c FROM service_calls
            WHERE client_id=? AND lower(COALESCE(status, 'open')) NOT IN ('closed', 'resolved', 'cancelled')
        """, (client_id,)).fetchone()["c"]
        pending_offers = conn.execute("""
            SELECT COUNT(*) AS c FROM quotations
            WHERE client_id=? AND lower(COALESCE(status, 'draft')) IN ('draft', 'pending', 'open', 'sent', 'in_progress', 'follow_up')
        """, (client_id,)).fetchone()["c"]
        sales_orders = conn.execute("""
            SELECT COUNT(*) AS c FROM customer_requests
            WHERE client_id=? AND lower(COALESCE(status, 'open')) NOT IN ('completed', 'invoiced', 'cancelled')
        """, (client_id,)).fetchone()["c"]
        spare_parts = conn.execute("""
            SELECT COUNT(*) AS c
            FROM customer_request_items i
            JOIN customer_requests r ON r.id=i.request_id
            WHERE r.client_id=? AND i.item_type='spare_part'
              AND COALESCE(i.invoiced_qty,0) < COALESCE(i.quantity,0)
        """, (client_id,)).fetchone()["c"]
        accessories = conn.execute("""
            SELECT COUNT(*) AS c
            FROM customer_request_items i
            JOIN customer_requests r ON r.id=i.request_id
            WHERE r.client_id=? AND i.item_type='accessory'
              AND COALESCE(i.invoiced_qty,0) < COALESCE(i.quantity,0)
        """, (client_id,)).fetchone()["c"]
        pending_deliveries = conn.execute("""
            SELECT COUNT(*) AS c
            FROM customer_request_items i
            JOIN customer_requests r ON r.id=i.request_id
            WHERE r.client_id=? AND COALESCE(i.delivered_qty,0) < COALESCE(i.quantity,0)
              AND lower(COALESCE(r.status, 'open')) NOT IN ('cancelled')
        """, (client_id,)).fetchone()["c"]
        pending_procurement = conn.execute("""
            SELECT COUNT(*) AS c
            FROM customer_request_items i
            JOIN customer_requests r ON r.id=i.request_id
            WHERE r.client_id=?
              AND COALESCE(i.procurement_status,'') IN ('po_draft','po_sent','supplier_confirmed','partially_received','not_ordered')
              AND COALESCE(i.shortage_qty,0) > 0
        """, (client_id,)).fetchone()["c"]
        unpaid_invoices = conn.execute("""
            SELECT COUNT(*) AS c
            FROM sales_case_documents
            WHERE client_id=? AND doc_type='invoice'
              AND lower(COALESCE(status, 'issued')) NOT IN ('paid', 'cancelled')
        """, (client_id,)).fetchone()["c"]
        urgent_issues = conn.execute("""
            SELECT COUNT(*) AS c FROM cases
            WHERE client_id=? AND lower(COALESCE(priority, 'normal')) IN ('urgent', 'high', 'critical')
              AND lower(COALESCE(status, 'open')) NOT IN ('completed', 'closed', 'cancelled')
        """, (client_id,)).fetchone()["c"]
        blocked_items = len(blocked_item_rows(conn, client_id, None, 500))
        pm_overdue = conn.execute("""
            SELECT COUNT(*) AS c FROM pm_assets
            WHERE (client_id=? OR lower(trim(hospital))=lower(trim(?)))
              AND COALESCE(next_pm_date, '') < ?
              AND lower(COALESCE(status, '')) NOT IN ('completed', 'closed', 'retired')
        """, (client_id, name, today.isoformat())).fetchone()["c"]
        pending_installations = conn.execute("""
            SELECT COUNT(*) AS c FROM cases
            WHERE client_id=? AND case_type IN ('installation', 'equipment_delivery')
              AND lower(COALESCE(status, 'open')) NOT IN ('completed', 'closed', 'cancelled', 'delivered')
        """, (client_id,)).fetchone()["c"]
        contract_rows = [dict(r) for r in conn.execute("""
            SELECT contract_end_date FROM pm_assets
            WHERE (client_id=? OR lower(trim(hospital))=lower(trim(?)))
              AND COALESCE(contract_no, '') != ''
        """, (client_id, name)).fetchall()]
        if not contract_rows:
            contract_status = "no contract"
        elif any((parse_iso_date(r.get("contract_end_date")) and parse_iso_date(r.get("contract_end_date")) < today) for r in contract_rows):
            contract_status = "expired"
        elif any((parse_iso_date(r.get("contract_end_date")) and parse_iso_date(r.get("contract_end_date")) <= month_end) for r in contract_rows):
            contract_status = "expiring soon"
        else:
            contract_status = "active"
        activity_types = [r["activity_type"] for r in conn.execute("""
            SELECT DISTINCT activity_type FROM client_activities
            WHERE client_id=? AND COALESCE(activity_type, '') != ''
            UNION
            SELECT DISTINCT case_type AS activity_type FROM cases
            WHERE client_id=? AND COALESCE(case_type, '') != ''
            ORDER BY activity_type
        """, (client_id, client_id)).fetchall()]
        modality_rows = [r["modality"] for r in conn.execute("""
            SELECT DISTINCT COALESCE(em.modality, a.equipment_family, '') AS modality
            FROM equipment e
            LEFT JOIN pm_assets a ON a.id=e.pm_asset_id
            LEFT JOIN equipment_models em ON em.id=e.equipment_model_id
            WHERE e.client_id=? AND COALESCE(COALESCE(em.modality, a.equipment_family), '') != ''
            ORDER BY modality
        """, (client_id,)).fetchall()]
        client_order_refs = [r["client_order_no"] for r in conn.execute("""
            SELECT DISTINCT client_order_no FROM client_orders
            WHERE client_id=? OR lower(trim(client_name))=lower(trim(?))
            ORDER BY client_order_no
        """, (client_id, name)).fetchall()]
        purchase_order_refs = [r["po_no"] for r in conn.execute("""
            SELECT DISTINCT po_no FROM purchase_orders
            WHERE client_id=? OR request_id IN (SELECT id FROM customer_requests WHERE client_id=?)
            ORDER BY po_no
        """, (client_id, client_id)).fetchall()]
        service_follow_up = service_hospital_follow_up_data(conn, client_id)
        follow_up_summary = service_follow_up["summary"]
        rows.append({
            **client,
            **metrics,
            "open_cases": int(open_cases or 0),
            "pending_calls": int(pending_calls or 0),
            "pending_offers": int(pending_offers or 0),
            "open_sales_orders": int(sales_orders or 0),
            "open_spare_parts_orders": int(spare_parts or 0),
            "open_accessories_orders": int(accessories or 0),
            "pending_spare_parts_accessories": int((spare_parts or 0) + (accessories or 0)),
            "open_service_orders": metrics["open_service_calls"],
            "pm_due": metrics["upcoming_pms"],
            "pm_overdue": int(pm_overdue or 0),
            "maintenance_contract_status": contract_status,
            "active_maintenance_contract": contract_status in {"active", "expiring soon"},
            "machines_under_warranty": metrics["under_warranty"],
            "warranty_equipment_count": metrics["under_warranty"],
            "unpaid_invoices": int(unpaid_invoices or 0),
            "pending_deliveries": int(pending_deliveries or 0),
            "pending_installations_deliveries": int((pending_installations or 0) + (pending_deliveries or 0)),
            "pending_procurement": int(pending_procurement or 0),
            "contract_renewals_pending": follow_up_summary["contract_renewals_pending"],
            "fmi_impacted_equipment": follow_up_summary["fmi_impacted_equipment"],
            "service_follow_up_score": (
                follow_up_summary["calls_pending"]
                + follow_up_summary["offers_pending"]
                + follow_up_summary["contract_renewals_pending"]
                + follow_up_summary["fmi_impacted_equipment"]
                + follow_up_summary["pm_overdue"]
            ),
            "blocked_items_count": int(blocked_items or 0),
            "urgent_open_issues": int(urgent_issues or 0),
            "urgent_items_count": int(urgent_issues or 0),
            "activity_types": ", ".join(activity_types),
            "modalities": ", ".join(modality_rows),
            "client_order_refs": ", ".join(client_order_refs),
            "purchase_order_refs": ", ".join(purchase_order_refs),
        })
    return rows

def commercial_next_no(conn, table: str, no_col: str, prefix: str) -> str:
    year = date.today().year
    row = conn.execute(f"SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM {table}").fetchone()
    next_id = int(row["next_id"] or 1)
    while True:
        candidate = f"{prefix}-{year}-{next_id:05d}"
        exists = conn.execute(f"SELECT 1 FROM {table} WHERE {no_col}=?", (candidate,)).fetchone()
        if not exists:
            return candidate
        next_id += 1

def create_product(payload: dict):
    conn = db()
    try:
        ts = now()
        cur = conn.execute("""
            INSERT INTO products
            (ref, description, category, product_type, brand, model, unit_price, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.get("ref", ""),
            payload.get("description", ""),
            payload.get("category", ""),
            payload.get("product_type", ""),
            payload.get("brand", ""),
            payload.get("model", ""),
            float(payload.get("unit_price") or 0),
            int(payload.get("active", 1)),
            ts,
        ))
        conn.commit()
        return dict(conn.execute("SELECT * FROM products WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()

def create_commercial_quotation(customer_id: int, items: list[dict], quotation_no: str = "", status: str = "draft",
                                quotation_date: str = "", valid_until: str = "", notes: str = ""):
    conn = db()
    try:
        quotation_no = quotation_no or commercial_next_no(conn, "quotations", "quotation_no", "QT")
        quote_date = quotation_date or date.today().isoformat()
        ts = now()
        cur = conn.execute("""
            INSERT INTO quotations
            (quotation_no, client_id, customer_id, status, quote_date, quotation_date, valid_until, amount, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (quotation_no, customer_id, customer_id, status, quote_date, quote_date, valid_until, 0, notes, ts, ts))
        quotation_id = cur.lastrowid
        total = 0.0
        for item in items:
            product = None
            if item.get("product_id"):
                product = conn.execute("SELECT * FROM products WHERE id=?", (item["product_id"],)).fetchone()
            ref = item.get("ref") or (product["ref"] if product else "")
            description = item.get("description") or (product["description"] if product else "")
            unit_price = float(item.get("unit_price") if item.get("unit_price") is not None else (product["unit_price"] if product else 0))
            qty = int(item.get("qty") or 1)
            line_total = float(item.get("total_price") if item.get("total_price") is not None else qty * unit_price)
            total += line_total
            conn.execute("""
                INSERT INTO quotation_items
                (quotation_id, product_id, ref, description, qty, unit_price, total_price, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (quotation_id, item.get("product_id"), ref, description, qty, unit_price, line_total, item.get("notes", "")))
        conn.execute("UPDATE quotations SET amount=?, updated_at=? WHERE id=?", (total, ts, quotation_id))
        conn.commit()
        return {
            "quotation": dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone()),
            "items": [dict(r) for r in conn.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY id", (quotation_id,)).fetchall()],
        }
    finally:
        conn.close()

def approve_quotation(quotation_id: int):
    conn = db()
    try:
        quotation = conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone()
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        existing = conn.execute("SELECT * FROM customer_orders WHERE quotation_id=?", (quotation_id,)).fetchone()
        if existing:
            return {
                "customer_order": dict(existing),
                "items": [dict(r) for r in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=? ORDER BY id", (existing["id"],)).fetchall()],
                "stock_items": [dict(r) for r in conn.execute("SELECT * FROM stock_items WHERE customer_order_id=? ORDER BY id", (existing["id"],)).fetchall()],
            }
        quotation_items = [dict(r) for r in conn.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY id", (quotation_id,)).fetchall()]
        if not quotation_items:
            raise HTTPException(status_code=400, detail="Quotation has no items")
        customer_id = quotation["customer_id"] if "customer_id" in quotation.keys() and quotation["customer_id"] else quotation["client_id"]
        co_no = commercial_next_no(conn, "customer_orders", "co_no", "CO")
        ts = now()
        cur = conn.execute("""
            INSERT INTO customer_orders
            (co_no, quotation_id, customer_id, status, order_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (co_no, quotation_id, customer_id, "open", date.today().isoformat(), quotation["notes"] if "notes" in quotation.keys() else "", ts))
        customer_order_id = cur.lastrowid
        for item in quotation_items:
            qty = int(item.get("qty") or 0)
            co_item_cur = conn.execute("""
                INSERT INTO customer_order_items
                (customer_order_id, quotation_item_id, product_id, ref, description, ordered_qty,
                 procured_qty, received_qty, delivered_qty, pending_qty, status)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """, (
                customer_order_id,
                item["id"],
                item.get("product_id"),
                item.get("ref", ""),
                item.get("description", ""),
                qty,
                qty,
                "pending_procurement",
            ))
            conn.execute("""
                INSERT INTO stock_items
                (product_id, ref, description, qty, customer_order_id, customer_order_item_id, co_no,
                 customer_id, source, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("product_id"),
                item.get("ref", ""),
                item.get("description", ""),
                qty,
                customer_order_id,
                co_item_cur.lastrowid,
                co_no,
                customer_id,
                "customer_order",
                "pending_procurement",
                ts,
                ts,
            ))
        conn.execute("UPDATE quotations SET status='approved', updated_at=? WHERE id=?", (ts, quotation_id))
        conn.commit()
        return {
            "customer_order": dict(conn.execute("SELECT * FROM customer_orders WHERE id=?", (customer_order_id,)).fetchone()),
            "items": [dict(r) for r in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
            "stock_items": [dict(r) for r in conn.execute("SELECT * FROM stock_items WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
        }
    finally:
        conn.close()

def update_customer_order_status(conn, customer_order_id: int):
    rows = [dict(r) for r in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=?", (customer_order_id,)).fetchall()]
    if not rows:
        return
    ordered = sum(int(r.get("ordered_qty") or 0) for r in rows)
    procured = sum(int(r.get("procured_qty") or 0) for r in rows)
    delivered = sum(int(r.get("delivered_qty") or 0) for r in rows)
    if delivered >= ordered:
        status = "delivered"
    elif delivered > 0:
        status = "partially_delivered"
    elif procured >= ordered:
        status = "procured"
    elif procured > 0:
        status = "partially_procured"
    else:
        status = "open"
    conn.execute("UPDATE customer_orders SET status=? WHERE id=?", (status, customer_order_id))

def create_purchase_order_from_stock_items(supplier_id: int, stock_item_ids: list[int], notes: str = ""):
    conn = db()
    try:
        if not stock_item_ids:
            raise HTTPException(status_code=400, detail="No stock items selected")
        po_no = commercial_next_no(conn, "purchase_orders", "po_no", "PO")
        ts = now()
        cur = conn.execute("""
            INSERT INTO purchase_orders
            (po_no, supplier_id, supplier, status, po_date, expected_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (po_no, supplier_id, str(supplier_id or ""), "draft", date.today().isoformat(), "", notes, ts, ts))
        purchase_order_id = cur.lastrowid
        touched_orders = set()
        for stock_item_id in stock_item_ids:
            item = conn.execute("SELECT * FROM stock_items WHERE id=?", (stock_item_id,)).fetchone()
            if not item:
                raise HTTPException(status_code=404, detail=f"Stock item {stock_item_id} not found")
            if item["status"] in {"delivered", "cancelled"}:
                raise HTTPException(status_code=400, detail=f"Stock item {stock_item_id} cannot be ordered")
            conn.execute("""
                INSERT INTO purchase_order_items
                (purchase_order_id, po_no, stock_item_id, product_id, ref, pn, description, qty, received_qty, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (
                purchase_order_id,
                po_no,
                item["id"],
                item["product_id"],
                item["ref"],
                item["ref"],
                item["description"],
                item["qty"],
                "ordered",
                ts,
                ts,
            ))
            conn.execute("""
                UPDATE stock_items
                SET purchase_order_id=?, po_no=?, supplier_id=?, status='ordered', updated_at=?
                WHERE id=?
            """, (purchase_order_id, po_no, supplier_id, ts, item["id"]))
            conn.execute("""
                UPDATE customer_order_items
                SET procured_qty=MIN(ordered_qty, COALESCE(procured_qty, 0) + ?), status='ordered'
                WHERE id=?
            """, (int(item["qty"] or 0), item["customer_order_item_id"]))
            touched_orders.add(item["customer_order_id"])
        for customer_order_id in touched_orders:
            update_customer_order_status(conn, customer_order_id)
        conn.commit()
        return {
            "purchase_order": dict(conn.execute("SELECT * FROM purchase_orders WHERE id=?", (purchase_order_id,)).fetchone()),
            "items": [dict(r) for r in conn.execute("SELECT * FROM purchase_order_items WHERE purchase_order_id=? ORDER BY id", (purchase_order_id,)).fetchall()],
        }
    finally:
        conn.close()

def create_shipment_from_purchase_order_items(purchase_order_item_ids: list[int], supplier_id: int | None = None,
                                              shipment_no: str = "", notes: str = ""):
    conn = db()
    try:
        if not purchase_order_item_ids:
            raise HTTPException(status_code=400, detail="No purchase order items selected")
        shipment_no = shipment_no or commercial_next_no(conn, "shipments", "shipment_no", "SH")
        ts = now()
        cur = conn.execute("""
            INSERT INTO shipments
            (shipment_no, supplier_id, status, shipment_date, expected_arrival, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (shipment_no, supplier_id, "shipped", date.today().isoformat(), "", notes, ts))
        shipment_id = cur.lastrowid
        stock_item_ids = []
        for poi_id in purchase_order_item_ids:
            item = conn.execute("SELECT * FROM purchase_order_items WHERE id=?", (poi_id,)).fetchone()
            if not item:
                raise HTTPException(status_code=404, detail=f"Purchase order item {poi_id} not found")
            conn.execute("""
                INSERT INTO shipment_items
                (shipment_id, purchase_order_item_id, stock_item_id, ref, description, qty, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (shipment_id, item["id"], item["stock_item_id"], item["ref"] or item["pn"], item["description"], item["qty"], "shipped"))
            stock_item_ids.append(item["stock_item_id"])
        conn.executemany("UPDATE stock_items SET shipment_id=?, status='shipped', updated_at=? WHERE id=?", [(shipment_id, ts, sid) for sid in stock_item_ids])
        conn.commit()
        return {
            "shipment": dict(conn.execute("SELECT * FROM shipments WHERE id=?", (shipment_id,)).fetchone()),
            "items": [dict(r) for r in conn.execute("SELECT * FROM shipment_items WHERE shipment_id=? ORDER BY id", (shipment_id,)).fetchall()],
        }
    finally:
        conn.close()

def receive_shipment(shipment_id: int):
    conn = db()
    try:
        shipment_items = [dict(r) for r in conn.execute("SELECT * FROM shipment_items WHERE shipment_id=? ORDER BY id", (shipment_id,)).fetchall()]
        if not shipment_items:
            raise HTTPException(status_code=400, detail="Shipment has no items")
        reception_no = commercial_next_no(conn, "receptions", "reception_no", "RC")
        ts = now()
        cur = conn.execute("""
            INSERT INTO receptions
            (reception_no, shipment_id, received_date, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (reception_no, shipment_id, date.today().isoformat(), "received", "", ts))
        reception_id = cur.lastrowid
        touched_items = []
        touched_co_items = []
        for item in shipment_items:
            conn.execute("""
                INSERT INTO reception_items
                (reception_id, shipment_item_id, stock_item_id, ref, description, qty, received_qty, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (reception_id, item["id"], item["stock_item_id"], item["ref"], item["description"], item["qty"], item["qty"], "received"))
            stock_item = conn.execute("SELECT * FROM stock_items WHERE id=?", (item["stock_item_id"],)).fetchone()
            touched_items.append(item["stock_item_id"])
            if stock_item:
                touched_co_items.append((int(item["qty"] or 0), stock_item["customer_order_item_id"]))
        conn.executemany("UPDATE stock_items SET reception_id=?, status='in_stock', updated_at=? WHERE id=?", [(reception_id, ts, sid) for sid in touched_items])
        for qty, co_item_id in touched_co_items:
            conn.execute("""
                UPDATE customer_order_items
                SET received_qty=MIN(ordered_qty, COALESCE(received_qty, 0) + ?), status='in_stock'
                WHERE id=?
            """, (qty, co_item_id))
        conn.execute("UPDATE shipments SET status='arrived' WHERE id=?", (shipment_id,))
        conn.commit()
        return {
            "reception": dict(conn.execute("SELECT * FROM receptions WHERE id=?", (reception_id,)).fetchone()),
            "items": [dict(r) for r in conn.execute("SELECT * FROM reception_items WHERE reception_id=? ORDER BY id", (reception_id,)).fetchall()],
        }
    finally:
        conn.close()

def create_delivery_order(customer_id: int, customer_order_id: int, stock_item_ids: list[int], notes: str = ""):
    conn = db()
    try:
        if not stock_item_ids:
            raise HTTPException(status_code=400, detail="No stock items selected")
        do_no = commercial_next_no(conn, "delivery_orders", "do_no", "DO")
        ts = now()
        cur = conn.execute("""
            INSERT INTO delivery_orders
            (do_no, customer_id, customer_order_id, status, delivery_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (do_no, customer_id, customer_order_id, "draft", date.today().isoformat(), notes, ts))
        delivery_order_id = cur.lastrowid
        touched_co_items = []
        for stock_item_id in stock_item_ids:
            item = conn.execute("SELECT * FROM stock_items WHERE id=?", (stock_item_id,)).fetchone()
            if not item:
                raise HTTPException(status_code=404, detail=f"Stock item {stock_item_id} not found")
            if item["status"] != "in_stock":
                raise HTTPException(status_code=400, detail="Only in-stock items can be delivered")
            source = "reception" if item["reception_id"] else "existing_stock"
            conn.execute("""
                INSERT INTO delivery_order_items
                (delivery_order_id, stock_item_id, ref, description, qty, source, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (delivery_order_id, item["id"], item["ref"], item["description"], item["qty"], source, "delivered"))
            conn.execute("UPDATE stock_items SET delivery_order_id=?, status='delivered', updated_at=? WHERE id=?", (delivery_order_id, ts, item["id"]))
            touched_co_items.append((int(item["qty"] or 0), item["customer_order_item_id"]))
        for qty, co_item_id in touched_co_items:
            conn.execute("""
                UPDATE customer_order_items
                SET delivered_qty=MIN(ordered_qty, COALESCE(delivered_qty, 0) + ?),
                    pending_qty=MAX(ordered_qty - MIN(ordered_qty, COALESCE(delivered_qty, 0) + ?), 0),
                    status='delivered'
                WHERE id=?
            """, (qty, qty, co_item_id))
        update_customer_order_status(conn, customer_order_id)
        conn.execute("UPDATE delivery_orders SET status='delivered' WHERE id=?", (delivery_order_id,))
        conn.commit()
        return {
            "delivery_order": dict(conn.execute("SELECT * FROM delivery_orders WHERE id=?", (delivery_order_id,)).fetchone()),
            "items": [dict(r) for r in conn.execute("SELECT * FROM delivery_order_items WHERE delivery_order_id=? ORDER BY id", (delivery_order_id,)).fetchall()],
        }
    finally:
        conn.close()

def sales_dashboard_data(conn, category: str = ""):
    sync_core_reference_tables(conn)
    selected = normalize_sales_category(category) if category else ""
    where = "WHERE sr.category=?" if selected else ""
    params = [selected] if selected else []
    requests = [dict(r) for r in conn.execute(f"""
        SELECT sr.*, c.name AS client_name, d.department_name, e.asset_tag, e.serial_number
        FROM sales_requests sr
        LEFT JOIN clients c ON c.id=sr.client_id
        LEFT JOIN departments d ON d.id=sr.department_id
        LEFT JOIN equipment e ON e.id=sr.equipment_id
        {where}
        ORDER BY sr.updated_at DESC, sr.id DESC
    """, params).fetchall()]
    items = [dict(r) for r in conn.execute("""
        SELECT sri.*, sr.customer_request_id, sr.parent_case_reference, sr.offer_reference,
               c.name AS client_name, d.department_name
        FROM sales_request_items sri
        JOIN sales_requests sr ON sr.id=sri.sales_request_id
        LEFT JOIN clients c ON c.id=sr.client_id
        LEFT JOIN departments d ON d.id=sr.department_id
        WHERE (? = '' OR sri.category=?)
        ORDER BY sri.updated_at DESC, sri.id DESC
    """, (selected, selected)).fetchall()]
    return {
        "sections": {
            "spare_parts": [r for r in requests if r.get("category") == "spare_parts"],
            "accessories": [r for r in requests if r.get("category") == "accessories"],
            "equipment": [r for r in requests if r.get("category") == "equipment"],
        },
        "requests": requests,
        "items": items,
        "progress_stages": ["request", "quotation", "approval", "client_order", "stock/procurement", "delivery", "invoice", "paid/closed"],
        "bulk_targets": ["sales_requests", "procurement_requests"],
    }

def procurement_dashboard_data(conn, category: str = ""):
    sync_core_reference_tables(conn)
    selected = normalize_sales_category(category) if category else ""
    minimum_stock_alerts = [dict(r) for r in conn.execute("""
        SELECT i.id, i.pn, i.description, COALESCE(i.location, '') AS location,
               COALESCE(i.physical_qty, 0) - COALESCE(i.reserved_qty, 0) AS current_quantity,
               CASE WHEN COALESCE(i.system_qty, 0) > 0 THEN i.system_qty ELSE 1 END AS minimum_quantity,
               MAX((CASE WHEN COALESCE(i.system_qty, 0) > 0 THEN i.system_qty ELSE 1 END) - (COALESCE(i.physical_qty, 0) - COALESCE(i.reserved_qty, 0)), 1) AS suggested_reorder_quantity,
               COALESCE(i.device_family, '') AS category,
               '' AS supplier
        FROM inventory i
        WHERE (COALESCE(i.physical_qty, 0) - COALESCE(i.reserved_qty, 0)) < (CASE WHEN COALESCE(i.system_qty, 0) > 0 THEN i.system_qty ELSE 1 END)
          AND (? = '' OR COALESCE(i.item_category, CASE WHEN lower(COALESCE(i.device_family, '')) LIKE '%accessor%' THEN 'accessories' ELSE 'spare_parts' END)=?)
        ORDER BY suggested_reorder_quantity DESC, i.pn
        LIMIT 200
    """, (selected, selected)).fetchall()]
    requested_shortages = [dict(r) for r in conn.execute("""
        SELECT pr.*, c.name AS client_name, d.department_name, sr.offer_reference,
               sr.parent_case_reference, sr.customer_request_id
        FROM procurement_requests pr
        LEFT JOIN sales_requests sr ON sr.id=pr.sales_request_id
        LEFT JOIN clients c ON c.id=pr.client_id
        LEFT JOIN departments d ON d.id=pr.department_id
        WHERE COALESCE(pr.shortage_qty, 0) > 0
          AND (? = '' OR pr.category=?)
        ORDER BY pr.updated_at DESC, pr.id DESC
    """, (selected, selected)).fetchall()]
    incoming_ordered_items = [dict(r) for r in conn.execute("""
        SELECT poi.*, po.id AS purchase_order_id, po.supplier, po.status AS po_status,
               po.expected_date AS expected_delivery_date,
               COALESCE(poi.received_qty, 0) AS received_quantity,
               MAX(COALESCE(poi.qty, 0) - COALESCE(poi.received_qty, 0), 0) AS pending_quantity,
               COALESCE(pr.category, CASE WHEN lower(COALESCE(poi.device_family, '')) LIKE '%accessor%' THEN 'accessories' ELSE 'spare_parts' END) AS category,
               c.name AS client_name, sr.offer_reference, sr.parent_case_reference
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.po_no=poi.po_no
        LEFT JOIN procurement_requests pr ON pr.customer_request_item_id=poi.request_item_id
        LEFT JOIN sales_requests sr ON sr.id=pr.sales_request_id
        LEFT JOIN clients c ON c.id=pr.client_id
        WHERE lower(COALESCE(po.status, 'open')) NOT IN ('received', 'closed', 'cancelled')
          AND (? = '' OR COALESCE(pr.category, CASE WHEN lower(COALESCE(poi.device_family, '')) LIKE '%accessor%' THEN 'accessories' ELSE 'spare_parts' END)=?)
        ORDER BY COALESCE(po.expected_date, ''), poi.updated_at DESC
    """, (selected, selected)).fetchall()]
    return {
        "minimum_stock_alerts": minimum_stock_alerts,
        "requested_shortages": requested_shortages,
        "incoming_ordered_items": incoming_ordered_items,
        "categories": ["spare_parts", "accessories", "equipment"],
        "procurement_statuses": sorted(PROCUREMENT_STATUSES),
    }

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

def case_identity_for_request(conn, request_id: int):
    row = conn.execute("""
        SELECT c.id AS case_id, c.parent_case_reference, c.department_id, c.client_id
        FROM cases c
        WHERE c.request_id=?
        ORDER BY c.id DESC
        LIMIT 1
    """, (request_id,)).fetchone()
    if row and row["parent_case_reference"]:
        return {
            "parent_case_id": row["case_id"],
            "parent_case_reference": row["parent_case_reference"],
            "department_id": row["department_id"],
            "client_id": row["client_id"],
        }
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if req and req["parent_case_reference"]:
        return {
            "parent_case_id": req["parent_case_id"],
            "parent_case_reference": req["parent_case_reference"],
            "department_id": req["department_id"],
            "client_id": req["client_id"],
        }
    return {"parent_case_id": None, "parent_case_reference": "", "department_id": None, "client_id": req["client_id"] if req else None}

def sync_reference_registry(conn, doc_type: str, document_id: int, doc_no: str, document_reference: str,
                            parent_case_reference: str, parent_case_id: int | None, client_id: int | None,
                            department_id: int | None, request_id: int | None, status: str = "",
                            amount: float = 0, notes: str = ""):
    table_map = {
        "delivery_note": "delivery_notes",
        "invoice": "invoices",
        "service_report": "service_reports",
        "pm_report": "pm_reports",
        "installation_report": "installation_reports",
        "calibration_certificate": "calibration_reports",
        "contract": "contracts",
    }
    table = table_map.get(doc_type)
    if not table:
        return
    existing = conn.execute(f"SELECT id FROM {table} WHERE document_id=?", (document_id,)).fetchone()
    if existing:
        conn.execute(f"""
            UPDATE {table}
            SET doc_no=?, document_reference=?, parent_case_reference=?, parent_case_id=?,
                client_id=?, department_id=?, request_id=?, status=?, amount=?, notes=?, updated_at=?
            WHERE id=?
        """, (doc_no, document_reference, parent_case_reference, parent_case_id, client_id, department_id, request_id, status, amount, notes, now(), existing["id"]))
        return
    conn.execute(f"""
        INSERT INTO {table}
        (document_id, doc_no, document_reference, parent_case_reference, parent_case_id, client_id, department_id, request_id, status, amount, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (document_id, doc_no, document_reference, parent_case_reference, parent_case_id, client_id, department_id, request_id, status, amount, notes, now(), now()))

def create_sales_document(conn, request_id: int, doc_type: str, status: str = "draft", notes: str = "", source_document_id: int | None = None, line_quantities: dict[int, int] | None = None):
    if doc_type not in GENERATABLE_DOCUMENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported document type: {doc_type}")
    req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        raise HTTPException(status_code=404, detail="Customer request not found")
    case_identity = case_identity_for_request(conn, request_id)
    parent_case_reference = case_identity["parent_case_reference"]
    parent_case_id = case_identity["parent_case_id"]
    department_id = case_identity["department_id"]
    prefix = DOCUMENT_PREFIXES.get(doc_type, "DOC")
    existing = conn.execute("SELECT * FROM sales_case_documents WHERE request_id=? AND doc_type=? ORDER BY id DESC LIMIT 1", (request_id, doc_type)).fetchone()
    if existing and doc_type not in {"delivery_note", "invoice"}:
        if parent_case_reference and not existing["parent_case_reference"]:
            document_reference = document_reference_for(parent_case_reference, doc_type)
            conn.execute("""
                UPDATE sales_case_documents
                SET parent_case_reference=?, parent_case_id=?, document_reference=?, department_id=?, updated_at=?
                WHERE id=?
            """, (parent_case_reference, parent_case_id, document_reference, department_id, now(), existing["id"]))
            sync_reference_registry(conn, doc_type, existing["id"], existing["doc_no"], document_reference, parent_case_reference, parent_case_id, req["client_id"], department_id, request_id, existing["status"], existing["amount"], existing["notes"])
            existing = conn.execute("SELECT * FROM sales_case_documents WHERE id=?", (existing["id"],)).fetchone()
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
    document_reference = document_reference_for(parent_case_reference, doc_type)
    cur = conn.execute("""
        INSERT INTO sales_case_documents
        (request_id, client_id, doc_type, doc_no, status, source_document_id, amount, notes, created_at, updated_at,
         parent_case_reference, parent_case_id, document_reference, department_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (request_id, req["client_id"], doc_type, doc_no, status, source_document_id, amount, notes, now(), now(),
          parent_case_reference, parent_case_id, document_reference, department_id))
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
    sync_reference_registry(conn, doc_type, document_id, doc_no, document_reference, parent_case_reference, parent_case_id, req["client_id"], department_id, request_id, status, amount, notes)
    case_timeline(conn, parent_case_reference, parent_case_id, "document_created", f"{doc_type.replace('_', ' ').title()} created", status, "system", doc_no, "sales_case_documents", document_id)
    return dict(conn.execute("SELECT * FROM sales_case_documents WHERE id=?", (document_id,)).fetchone())

def latest_sales_document(conn, request_id: int, doc_type: str):
    row = conn.execute("SELECT * FROM sales_case_documents WHERE request_id=? AND doc_type=? ORDER BY id DESC LIMIT 1", (request_id, doc_type)).fetchone()
    return dict(row) if row else None

def refresh_case_links(conn, request_id: int):
    if not request_id:
        return
    identity = case_identity_for_request(conn, request_id)
    parent_case_reference = identity["parent_case_reference"]
    parent_case_id = identity["parent_case_id"]
    department_id = identity["department_id"]
    quotation = conn.execute("SELECT id FROM quotations WHERE request_id=? ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    client_order = conn.execute("SELECT id FROM client_orders WHERE request_id=? ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    purchase_order = conn.execute("SELECT id FROM purchase_orders WHERE request_id=? ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    delivery_note = conn.execute("SELECT id FROM sales_case_documents WHERE request_id=? AND doc_type='delivery_note' ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    invoice = conn.execute("SELECT id FROM sales_case_documents WHERE request_id=? AND doc_type='invoice' ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    conn.execute("""
        UPDATE cases
        SET quotation_id=COALESCE(?, quotation_id),
            client_order_id=COALESCE(?, client_order_id),
            purchase_order_id=COALESCE(?, purchase_order_id),
            delivery_note_id=COALESCE(?, delivery_note_id),
            invoice_id=COALESCE(?, invoice_id),
            updated_at=?
        WHERE request_id=?
    """, (
        quotation["id"] if quotation else None,
        client_order["id"] if client_order else None,
        purchase_order["id"] if purchase_order else None,
        delivery_note["id"] if delivery_note else None,
        invoice["id"] if invoice else None,
        now(),
        request_id,
    ))
    if parent_case_reference:
        conn.execute("""
            UPDATE customer_requests
            SET parent_case_reference=?, parent_case_id=COALESCE(parent_case_id, ?), department_id=COALESCE(department_id, ?), updated_at=?
            WHERE id=?
        """, (parent_case_reference, parent_case_id, department_id, now(), request_id))
        conn.execute("""
            UPDATE sales_case_documents
            SET parent_case_reference=?, parent_case_id=?, department_id=COALESCE(department_id, ?),
                document_reference=COALESCE(NULLIF(document_reference, ''), '')
            WHERE request_id=?
        """, (parent_case_reference, parent_case_id, department_id, request_id))
        for doc in conn.execute("SELECT * FROM sales_case_documents WHERE request_id=?", (request_id,)).fetchall():
            document_reference = doc["document_reference"] or document_reference_for(parent_case_reference, doc["doc_type"])
            conn.execute("""
                UPDATE sales_case_documents
                SET document_reference=?, parent_case_reference=?, parent_case_id=?, department_id=COALESCE(department_id, ?)
                WHERE id=?
            """, (document_reference, parent_case_reference, parent_case_id, department_id, doc["id"]))
            sync_reference_registry(conn, doc["doc_type"], doc["id"], doc["doc_no"], document_reference, parent_case_reference, parent_case_id, doc["client_id"], doc["department_id"] or department_id, request_id, doc["status"], doc["amount"], doc["notes"])
        conn.execute("""
            UPDATE quotations
            SET parent_case_reference=?, parent_case_id=?, department_id=COALESCE(department_id, ?),
                document_reference=COALESCE(NULLIF(document_reference, ''), ?)
            WHERE request_id=?
        """, (parent_case_reference, parent_case_id, department_id, document_reference_for(parent_case_reference, "quotation"), request_id))
        conn.execute("""
            UPDATE client_orders
            SET parent_case_reference=?, parent_case_id=?, department_id=COALESCE(department_id, ?),
                document_reference=COALESCE(NULLIF(document_reference, ''), ?)
            WHERE request_id=?
        """, (parent_case_reference, parent_case_id, department_id, document_reference_for(parent_case_reference, "client_order"), request_id))
        conn.execute("""
            UPDATE purchase_orders
            SET parent_case_reference=?, parent_case_id=?, department_id=COALESCE(department_id, ?),
                document_reference=COALESCE(NULLIF(document_reference, ''), ?)
            WHERE request_id=?
        """, (parent_case_reference, parent_case_id, department_id, document_reference_for(parent_case_reference, "purchase_order"), request_id))
        conn.execute("""
            UPDATE service_calls
            SET parent_case_reference=?, parent_case_id=?, department_id=COALESCE(department_id, ?)
            WHERE request_id=?
        """, (parent_case_reference, parent_case_id, department_id, request_id))

def advance_case_for_request(conn, request_id: int, state: str, notes: str = "", user: str = "system"):
    row = conn.execute("SELECT id, case_type, parent_case_reference FROM cases WHERE request_id=? ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    if not row:
        return
    allowed = workflow_states_for_case_type(row["case_type"])
    if state not in allowed:
        return
    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (row["id"], state, now(), user, notes))
    conn.execute("UPDATE cases SET workflow_state=?, updated_at=? WHERE id=?", (state, now(), row["id"]))
    case_timeline(conn, row["parent_case_reference"], row["id"], "workflow_state", state.replace("_", " ").title(), state, user, notes, "cases", row["id"])

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
        return FileResponse(BASE_DIR / "static" / "portal.html")
    return RedirectResponse(url="/login", status_code=303)

@app.get("/login")
def login_page(request: Request, error: str = ""):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
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
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/login?error=Invalid%20credentials", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/portal")
@app.get("/home")
def portal():
    return FileResponse(BASE_DIR / "static" / "portal.html")

@app.get("/dashboard")
def dashboard_page():
    return FileResponse(BASE_DIR / "static" / "dashboard.html")

@app.get("/inventory")
@app.get("/warehouse")
@app.get("/warehouse/{section:path}")
def inventory_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/procurement")
@app.get("/procurement/{section:path}")
def procurement_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "procurement.html")

@app.get("/sales")
@app.get("/sales/{section:path}")
def sales_page(section: str = ""):
    if section.strip("/") == "quotations":
        return FileResponse(BASE_DIR / "static" / "quotations.html")
    return FileResponse(BASE_DIR / "static" / "sales.html")

@app.get("/equipment-registry")
@app.get("/equipment-registry/{section:path}")
@app.get("/equipment-database")
@app.get("/equipment-database/{section:path}")
def equipment_registry_page(section: str = ""):
    if section or False:
        return FileResponse(BASE_DIR / "static" / "equipment_database.html")
    return FileResponse(BASE_DIR / "static" / "equipment_database.html")

@app.get("/financials")
@app.get("/finance")
@app.get("/finance/{section:path}")
def financials_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/reports")
def reports_page():
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/admin")
@app.get("/administration")
@app.get("/administration/{section:path}")
def admin_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "module_page.html")

@app.get("/imports")
@app.get("/admin/imports")
def imports_page():
    return FileResponse(BASE_DIR / "static" / "imports.html")

@app.get("/mdmanser")
def mdmanser_page():
    return RedirectResponse(url="/static/mdmanser.html", status_code=303)

@app.get("/mdmanser-data")
@app.get("/mdmanser/data")
def mdmanser_data_page():
    return FileResponse(BASE_DIR / "static" / "mdmanser_data.html")

@app.get("/cmm")
def cmm_page():
    return RedirectResponse(url="/static/mdmanser.html", status_code=303)

@app.get("/crm")
def crm_page():
    return FileResponse(BASE_DIR / "static" / "crm.html")

@app.get("/clients")
def clients_page():
    return FileResponse(BASE_DIR / "static" / "crm.html")

@app.get("/crm/client/{client_id}")
@app.get("/crm/client/{client_id}/{section:path}")
def crm_client_page(client_id: int, section: str = ""):
    return FileResponse(BASE_DIR / "static" / "crm_client.html")

@app.get("/departments")
def departments_page():
    return FileResponse(BASE_DIR / "static" / "core_list.html")

@app.get("/equipment")
def equipment_page():
    return FileResponse(BASE_DIR / "static" / "core_list.html")

@app.get("/cases")
def cases_page():
    return FileResponse(BASE_DIR / "static" / "core_list.html")

@app.get("/sales-cases")
def sales_cases_page():
    return RedirectResponse(url="/sales", status_code=303)

@app.get("/aftersales")
@app.get("/after-sales")
def after_sales_dashboard_alias():
    return FileResponse(BASE_DIR / "static" / "after_sales.html")

@app.get("/aftersales/pm")
@app.get("/aftersales/pm/{path:path}")
@app.get("/after-sales/pm")
@app.get("/after-sales/pm/{path:path}")
@app.get("/aftersales/pm-tracking")
@app.get("/aftersales/pm-tracking/{path:path}")
@app.get("/after-sales/pm-tracking")
@app.get("/after-sales/pm-tracking/{path:path}")
def after_sales_pm_alias(path: str = ""):
    return FileResponse(BASE_DIR / "static" / "pm.html")

@app.get("/aftersales/contracts")
@app.get("/aftersales/contracts/{path:path}")
@app.get("/after-sales/contracts")
@app.get("/after-sales/contracts/{path:path}")
def after_sales_contracts_alias(path: str = ""):
    return FileResponse(BASE_DIR / "static" / "pm" / "index.html")

@app.get("/aftersales/reports")
@app.get("/after-sales/reports")
def after_sales_reports_alias():
    return RedirectResponse(url="/aftersales/pm/reports", status_code=303)

@app.get("/aftersales/{section:path}")
@app.get("/after-sales/{section:path}")
def after_sales_page(section: str = ""):
    return FileResponse(BASE_DIR / "static" / "after_sales.html")

@app.get("/pm")
@app.get("/pm/")
@app.get("/pm/{path:path}")
def pm_page(path: str = ""):
    return FileResponse(BASE_DIR / "static" / "pm" / "index.html")


@app.get("/api/crm/clients")
def crm_clients(q: str = "", city: str = "", location: str = "", contract_status: str = "",
                active_contract: str = "", warranty_equipment: str = "", engineer: str = "",
                status: str = "", financial_status: str = ""):
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
        if location and location.lower() not in " ".join(str(row.get(k, "")) for k in ["city", "address"]).lower():
            matches = False
        if contract_status and row.get("contract_status") != contract_status:
            matches = False
        if active_contract:
            wants = active_contract.lower() in {"yes", "true", "1", "active"}
            if bool(row.get("active_contracts")) != wants:
                matches = False
        if warranty_equipment:
            wants = warranty_equipment.lower() in {"yes", "true", "1", "active"}
            if bool(row.get("under_warranty")) != wants:
                matches = False
        if engineer and engineer.lower() not in str(row.get("primary_engineer", "")).lower():
            matches = False
        if status and row.get("status") != status:
            matches = False
        if financial_status and financial_status.lower() not in str(row.get("financial_status", "")).lower():
            matches = False
        if matches:
            result.append(row)
    conn.close()
    return result

@app.get("/api/hospitals")
def hospitals_dashboard():
    conn = db()
    rows = hospital_dashboard_rows(conn)
    conn.commit()
    conn.close()
    return rows

@app.get("/api/sales/dashboard")
def sales_dashboard(category: str = ""):
    conn = db()
    data = sales_dashboard_data(conn, category)
    conn.commit()
    conn.close()
    return data

@app.get("/api/procurement/dashboard")
def procurement_dashboard(category: str = ""):
    conn = db()
    data = procurement_dashboard_data(conn, category)
    conn.commit()
    conn.close()
    return data

@app.post("/api/warehouse/replenishment-requests")
def create_warehouse_replenishment_request(payload: WarehouseReplenishmentRequest):
    if payload.requested_qty <= 0:
        raise HTTPException(status_code=400, detail="Requested quantity must be greater than zero")
    conn = db()
    item = conn.execute("SELECT * FROM inventory WHERE id=?", (payload.inventory_item_id,)).fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Warehouse item not found")
    category = normalize_inventory_category(item["item_category"] if "item_category" in item.keys() else "", item["device_family"], item["description"])
    existing = conn.execute("""
        SELECT * FROM procurement_requests
        WHERE inventory_item_id=?
          AND customer_request_item_id IS NULL
          AND lower(COALESCE(procurement_status, 'not_ordered')) NOT IN ('received', 'closed', 'cancelled')
        ORDER BY id DESC LIMIT 1
    """, (item["id"],)).fetchone()
    note = payload.notes or f"Minimum stock replenishment request for {item['pn'] or item['description']}"
    if existing:
        new_qty = max(int(existing["requested_qty"] or 0), payload.requested_qty)
        conn.execute("""
            UPDATE procurement_requests
            SET requested_qty=?, shortage_qty=?, pending_qty=?, supplier=?, notes=?, updated_at=?
            WHERE id=?
        """, (new_qty, new_qty, new_qty, payload.supplier or existing["supplier"] or "", note, now(), existing["id"]))
        request_id = existing["id"]
        action = "updated"
    else:
        cur = conn.execute("""
            INSERT INTO procurement_requests
            (inventory_item_id, category, requested_item, requested_qty, shortage_qty, procurement_status,
             supplier, pending_qty, priority, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["id"],
            category,
            item["description"] or item["pn"],
            payload.requested_qty,
            payload.requested_qty,
            "not_ordered",
            payload.supplier,
            payload.requested_qty,
            "normal",
            note,
            now(),
            now(),
        ))
        request_id = cur.lastrowid
        action = "created"
    audit(conn, item["id"], "WAREHOUSE_REPLENISHMENT_REQUEST", "", {"procurement_request_id": request_id, "qty": payload.requested_qty}, note)
    conn.commit()
    conn.close()
    return {"id": request_id, "action": action, "message": f"Replenishment request {action}"}

@app.get("/api/clients")
def list_clients(q: str = "", status: str = ""):
    return crm_clients(q=q, status=status)

@app.post("/api/clients")
def save_client(client: CRMClient, request: Request):
    return create_crm_client(client, request)

@app.get("/api/departments")
def list_departments(client_id: int | None = None):
    conn = db()
    where = "WHERE client_id=?" if client_id else ""
    params = [client_id] if client_id else []
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM departments {where} ORDER BY department_name", params).fetchall()]
    conn.close()
    return rows

@app.post("/api/departments")
def save_department(payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    client_id = payload.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    conn = db()
    crm_client_row(conn, int(client_id))
    department_id = ensure_department(
        conn,
        int(client_id),
        payload.get("department_name", ""),
        floor_location=payload.get("floor_location", ""),
        main_contact_name=payload.get("main_contact_name", ""),
        phone=payload.get("phone", ""),
        email=payload.get("email", ""),
        notes=payload.get("notes", ""),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM departments WHERE id=?", (department_id,)).fetchone())
    conn.close()
    return row

@app.put("/api/departments/{department_id}")
def update_department(department_id: int, payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    existing = conn.execute("SELECT * FROM departments WHERE id=?", (department_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Department not found")
    conn.execute("""
        UPDATE departments
        SET department_name=COALESCE(NULLIF(?, ''), department_name),
            floor_location=?, main_contact_name=?, phone=?, email=?, notes=?, updated_at=?
        WHERE id=?
    """, (
        payload.get("department_name", existing["department_name"]), payload.get("floor_location", existing["floor_location"]),
        payload.get("main_contact_name", existing["main_contact_name"]), payload.get("phone", existing["phone"]),
        payload.get("email", existing["email"]), payload.get("notes", existing["notes"]), now(), department_id
    ))
    conn.execute("""
        UPDATE client_departments
        SET department_name=(SELECT department_name FROM departments WHERE id=?),
            floor_location=(SELECT floor_location FROM departments WHERE id=?),
            main_contact_name=(SELECT main_contact_name FROM departments WHERE id=?),
            phone=(SELECT phone FROM departments WHERE id=?),
            email=(SELECT email FROM departments WHERE id=?),
            notes=(SELECT notes FROM departments WHERE id=?),
            updated_at=?
        WHERE id=?
    """, (department_id, department_id, department_id, department_id, department_id, department_id, now(), department_id))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM departments WHERE id=?", (department_id,)).fetchone())
    conn.close()
    return row

@app.get("/api/equipment")
def list_equipment(client_id: int | None = None, department_id: int | None = None, q: str = ""):
    conn = db()
    sync_core_reference_tables(conn)
    where, params = [], []
    if client_id:
        where.append("e.client_id=?")
        params.append(client_id)
    if department_id:
        where.append("e.department_id=?")
        params.append(department_id)
    if q:
        where.append("(e.asset_tag LIKE ? OR e.serial_number LIKE ? OR e.manufacturer LIKE ? OR e.model LIKE ? OR a.equipment_name LIKE ? OR a.equipment_family LIKE ?)")
        params.extend([f"%{q}%"] * 6)
    sql = """
        SELECT e.id, e.pm_asset_id, e.client_id, e.department_id, e.equipment_model_id,
               COALESCE(a.equipment_name, e.asset_tag, e.model) AS equipment_name,
               COALESCE(a.equipment_family, em.equipment_family, '') AS equipment_family,
               e.asset_tag, e.serial_number, e.manufacturer, e.model,
               COALESCE(a.status, e.status) AS status,
               COALESCE(a.lifecycle_status, '') AS lifecycle_status,
               a.location, a.installation_date, a.installation_data,
               a.end_user, a.warranty_expiration, a.delivery_doc, a.supplies,
               a.system_name, a.subsystem_name,
               a.contract_no, a.contract_start_date, a.contract_end_date,
               a.frequency_days AS pm_frequency_days, a.last_pm_date, a.next_pm_date,
               a.last_service_date, a.calibration_required, a.calibration_due_date,
               a.risk_level AS risk_classification, a.life_support, a.criticality_level, a.department_risk_level,
               a.total_uptime_hours, a.total_downtime_hours, a.operational_percentage, a.mtbf_hours,
               a.blocked_reason, a.client_informed,
               c.name AS client_name, d.department_name,
               COALESCE(w.warranty_start, a.warranty_start) AS warranty_start,
               COALESCE(w.warranty_end, a.warranty_end, a.warranty_expiration) AS warranty_end,
               COALESCE(w.status, a.warranty_status) AS warranty_status
        FROM equipment e
        LEFT JOIN pm_assets a ON a.id=e.pm_asset_id
        LEFT JOIN equipment_models em ON em.id=e.equipment_model_id
        LEFT JOIN clients c ON c.id=e.client_id
        LEFT JOIN departments d ON d.id=e.department_id
        LEFT JOIN warranties w ON w.equipment_id=e.id
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY c.name, d.department_name, e.asset_tag"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.commit()
    conn.close()
    return rows

@app.get("/api/equipment/{equipment_id}")
def get_equipment(equipment_id: int):
    conn = db()
    sync_core_reference_tables(conn)
    row = equipment_detail_data(conn, equipment_id)
    conn.commit()
    conn.close()
    return row

@app.post("/api/equipment")
def create_equipment(payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    asset_tag = str(payload.get("asset_tag", "")).strip()
    if not asset_tag:
        raise HTTPException(status_code=400, detail="asset_tag is required")
    conn = db()
    client_id = payload.get("client_id")
    hospital = payload.get("hospital", "")
    if client_id:
        client = crm_client_row(conn, int(client_id))
        hospital = hospital or client["name"]
    department_id = payload.get("department_id")
    department = payload.get("department", "")
    if department_id and not department:
        dept = conn.execute("SELECT department_name FROM departments WHERE id=?", (department_id,)).fetchone()
        department = dept["department_name"] if dept else ""
    try:
        cur = conn.execute("""
            INSERT INTO pm_assets
            (asset_tag, serial_number, manufacturer, model, department, hospital, location, engineer, contact_email,
             contract_no, contract_start_date, contract_end_date, frequency_days, next_pm_date, last_pm_date, status,
             notes, linked_inventory_pn, barcode, created_at, updated_at, client_id, department_id,
             equipment_name, equipment_family, installation_date, warranty_start, warranty_end, calibration_required,
             calibration_due_date, risk_level, life_support, lifecycle_status, last_service_date,
             end_user, installation_data, warranty_expiration, delivery_doc, supplies, system_name, subsystem_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            asset_tag, payload.get("serial_number", ""), payload.get("manufacturer", ""), payload.get("model", ""),
            department, hospital, payload.get("location", ""), payload.get("engineer", ""), payload.get("contact_email", ""),
            payload.get("contract_no", ""), payload.get("contract_start_date", ""), payload.get("contract_end_date", ""),
            int(payload.get("frequency_days") or 180), payload.get("next_pm_date", ""), payload.get("last_pm_date", ""),
            payload.get("status", "Installed"), payload.get("notes", ""), payload.get("linked_inventory_pn", ""),
            payload.get("barcode", ""), now(), now(), client_id, department_id,
            payload.get("equipment_name", ""), payload.get("equipment_family", ""), payload.get("installation_date", ""),
            payload.get("warranty_start_date", payload.get("warranty_start", "")),
            payload.get("warranty_end_date", payload.get("warranty_end", "")),
            int(bool(payload.get("calibration_required", False))), payload.get("calibration_due_date", ""),
            payload.get("risk_classification", payload.get("risk_level", "medium")),
            int(bool(payload.get("life_support", False))), payload.get("lifecycle_status", payload.get("status", "active")),
            payload.get("last_service_date", ""),
            payload.get("end_user", ""), payload.get("installation_data", ""),
            payload.get("warranty_expiration", payload.get("warranty_end_date", payload.get("warranty_end", ""))),
            payload.get("delivery_doc", ""), payload.get("supplies", ""),
            payload.get("system_name", ""), payload.get("subsystem_name", ""),
        ))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Asset tag already exists")
    conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                 (cur.lastrowid, "ASSET_CREATED", "Equipment created from core API", payload.get("engineer", ""), now()))
    sync_core_reference_tables(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment WHERE pm_asset_id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row

@app.put("/api/equipment/{equipment_id}")
def update_equipment(equipment_id: int, payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    existing = conn.execute("SELECT * FROM equipment WHERE id=?", (equipment_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    pm_asset_id = existing["pm_asset_id"]
    conn.execute("""
        UPDATE pm_assets
        SET serial_number=COALESCE(?, serial_number), manufacturer=COALESCE(?, manufacturer),
            model=COALESCE(?, model), department=COALESCE(?, department),
            hospital=COALESCE(?, hospital), location=COALESCE(?, location),
            engineer=COALESCE(?, engineer), status=COALESCE(?, status),
            notes=COALESCE(?, notes), client_id=COALESCE(?, client_id),
            department_id=COALESCE(?, department_id),
            equipment_name=COALESCE(?, equipment_name), equipment_family=COALESCE(?, equipment_family),
            installation_date=COALESCE(?, installation_date), warranty_start=COALESCE(?, warranty_start),
            warranty_end=COALESCE(?, warranty_end), calibration_required=COALESCE(?, calibration_required),
            calibration_due_date=COALESCE(?, calibration_due_date), risk_level=COALESCE(?, risk_level),
            life_support=COALESCE(?, life_support), lifecycle_status=COALESCE(?, lifecycle_status),
            last_service_date=COALESCE(?, last_service_date),
            end_user=COALESCE(?, end_user), installation_data=COALESCE(?, installation_data),
            warranty_expiration=COALESCE(?, warranty_expiration), delivery_doc=COALESCE(?, delivery_doc),
            supplies=COALESCE(?, supplies), system_name=COALESCE(?, system_name),
            subsystem_name=COALESCE(?, subsystem_name), updated_at=?
        WHERE id=?
    """, (
        payload.get("serial_number"), payload.get("manufacturer"), payload.get("model"),
        payload.get("department"), payload.get("hospital"), payload.get("location"),
        payload.get("engineer"), payload.get("status"), payload.get("notes"),
        payload.get("client_id"), payload.get("department_id"),
        payload.get("equipment_name"), payload.get("equipment_family"), payload.get("installation_date"),
        payload.get("warranty_start_date", payload.get("warranty_start")),
        payload.get("warranty_end_date", payload.get("warranty_end")),
        int(bool(payload.get("calibration_required"))) if "calibration_required" in payload else None,
        payload.get("calibration_due_date"), payload.get("risk_classification", payload.get("risk_level")),
        int(bool(payload.get("life_support"))) if "life_support" in payload else None,
        payload.get("lifecycle_status"), payload.get("last_service_date"),
        payload.get("end_user"), payload.get("installation_data"),
        payload.get("warranty_expiration", payload.get("warranty_end_date", payload.get("warranty_end"))),
        payload.get("delivery_doc"), payload.get("supplies"),
        payload.get("system_name"), payload.get("subsystem_name"), now(), pm_asset_id,
    ))
    conn.execute("INSERT INTO pm_history (asset_id, action, notes, engineer, created_at) VALUES (?, ?, ?, ?, ?)",
                 (pm_asset_id, "ASSET_UPDATED", "Equipment updated from core API", payload.get("engineer", ""), now()))
    sync_core_reference_tables(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM equipment WHERE id=?", (equipment_id,)).fetchone())
    conn.close()
    return row

@app.get("/api/contracts")
def list_contracts(client_id: int | None = None):
    conn = db()
    where = "WHERE client_id=?" if client_id else ""
    params = [client_id] if client_id else []
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM contracts {where} ORDER BY updated_at DESC, id DESC", params).fetchall()]
    if not rows:
        rows = [dict(r) for r in conn.execute("""
            SELECT MIN(id) AS id, client_id, NULL AS department_id, contract_no AS doc_no,
                   contract_no AS document_reference, '' AS parent_case_reference, NULL AS parent_case_id,
                   MIN(contract_start_date) AS created_at, MAX(contract_end_date) AS updated_at,
                   'active' AS status, COUNT(*) AS equipment_count, hospital AS notes
            FROM pm_assets
            WHERE COALESCE(contract_no, '') != ''
            GROUP BY client_id, hospital, contract_no
            ORDER BY updated_at DESC
        """).fetchall()]
    conn.close()
    return rows

@app.post("/api/contracts")
def save_contract(payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    client_id = payload.get("client_id")
    if client_id:
        crm_client_row(conn, int(client_id))
    cur = conn.execute("""
        INSERT INTO contracts
        (doc_no, document_reference, parent_case_reference, parent_case_id, client_id, department_id, request_id, equipment_id, status, amount, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.get("contract_no") or payload.get("doc_no", ""),
        payload.get("document_reference", ""),
        payload.get("parent_case_reference", ""),
        payload.get("parent_case_id"),
        client_id,
        payload.get("department_id"),
        payload.get("request_id"),
        payload.get("equipment_id"),
        payload.get("status", "active"),
        float(payload.get("amount") or 0),
        payload.get("notes", ""),
        now(),
        now(),
    ))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM contracts WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row

@app.get("/api/service-calls")
def list_service_calls(client_id: int | None = None, department_id: int | None = None, status: str = ""):
    conn = db()
    where, params = [], []
    if client_id:
        where.append("client_id=?")
        params.append(client_id)
    if department_id:
        where.append("department_id=?")
        params.append(department_id)
    if status:
        where.append("status=?")
        params.append(status)
    sql = "SELECT * FROM service_calls"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(opened_at, created_at) DESC"
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows

@app.post("/api/service-calls")
def create_service_call(payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    client_id = payload.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")
    crm_client_row(conn, int(client_id))
    parent_ref = payload.get("parent_case_reference", "")
    parent_case_id = payload.get("parent_case_id")
    if not parent_ref and payload.get("case_id"):
        case_row = conn.execute("SELECT id, parent_case_reference FROM cases WHERE id=?", (payload.get("case_id"),)).fetchone()
        parent_ref = case_row["parent_case_reference"] if case_row else ""
        parent_case_id = case_row["id"] if case_row else None
    call_no = payload.get("call_no") or f"SC-{date.today().strftime('%y%m%d')}-{int(datetime.now().timestamp())}"
    cur = conn.execute("""
        INSERT INTO service_calls
        (client_id, equipment_id, request_id, call_no, status, engineer, issue, resolution, opened_at, closed_at, created_at, updated_at,
         parent_case_reference, parent_case_id, department_id, priority, response_time_hours, progress_state, invoice_required)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        client_id, payload.get("equipment_id"), payload.get("request_id"), call_no, payload.get("status", "open"),
        payload.get("engineer", ""), payload.get("issue", ""), payload.get("resolution", ""),
        payload.get("opened_at", now()), payload.get("closed_at", ""), now(), now(),
        parent_ref, parent_case_id, payload.get("department_id"), payload.get("priority", "normal"),
        float(payload.get("response_time_hours") or 0), payload.get("progress_state", "call_received"),
        int(bool(payload.get("invoice_required", False))),
    ))
    case_timeline(conn, parent_ref, parent_case_id, "service_call", "Service call created", payload.get("status", "open"), request.session.get("username", "system"), call_no, "service_calls", cur.lastrowid)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM service_calls WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row

@app.put("/api/service-calls/{call_id}")
def update_service_call(call_id: int, payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    existing = conn.execute("SELECT * FROM service_calls WHERE id=?", (call_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Service call not found")
    conn.execute("""
        UPDATE service_calls
        SET status=COALESCE(?, status), engineer=COALESCE(?, engineer), issue=COALESCE(?, issue),
            resolution=COALESCE(?, resolution), department_id=COALESCE(?, department_id),
            priority=COALESCE(?, priority), progress_state=COALESCE(?, progress_state),
            response_time_hours=COALESCE(?, response_time_hours), updated_at=?
        WHERE id=?
    """, (
        payload.get("status"), payload.get("engineer"), payload.get("issue"), payload.get("resolution"),
        payload.get("department_id"), payload.get("priority"), payload.get("progress_state"),
        payload.get("response_time_hours"), now(), call_id
    ))
    case_timeline(conn, existing["parent_case_reference"], existing["parent_case_id"], "engineer_update", "Service call updated", payload.get("status", existing["status"]), request.session.get("username", "system"), payload.get("notes", ""), "service_calls", call_id)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM service_calls WHERE id=?", (call_id,)).fetchone())
    conn.close()
    return row

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
def crm_client_dashboard(client_id: int, department_id: int | None = None):
    conn = db()
    data = crm_client_dashboard_data(conn, client_id, department_id)
    conn.close()
    return data

@app.get("/api/crm/client/{client_id}/timeline")
def crm_client_timeline(client_id: int, activity_type: str = "", status: str = "",
                        responsible_person: str = "", department: str = "", sort: str = "desc"):
    conn = db()
    data = crm_client_dashboard_data(conn, client_id)
    rows = list(data.get("timeline", []))
    for note in data.get("notes", []):
        rows.append({
            "id": f"communication-{note.get('id')}",
            "created_at": note.get("created_at"),
            "parent_case_reference": "",
            "event_type": "communication",
            "activity_type": "client_operations",
            "title": note.get("type") or "Communication",
            "status": "",
            "user": note.get("user") or "",
            "responsible_person": note.get("user") or "",
            "department": "",
            "notes": note.get("note") or "",
        })
    rows.extend([dict(r) for r in conn.execute("SELECT * FROM client_activities WHERE client_id=?", (client_id,)).fetchall()])
    def keep(row):
        row_type = str(row.get("activity_type") or row.get("event_type") or "").lower()
        if activity_type and activity_type != "all" and activity_type.lower() not in row_type:
            return False
        if status and status.lower() not in str(row.get("status", "")).lower():
            return False
        if responsible_person and responsible_person.lower() not in str(row.get("responsible_person") or row.get("user") or "").lower():
            return False
        if department and department.lower() not in str(row.get("department", "")).lower():
            return False
        return True
    unique = []
    seen = set()
    for row in rows:
        key = (row.get("created_at") or row.get("activity_date"), row.get("title"), row.get("source_table"), row.get("source_id"), row.get("notes"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    unique = [row for row in unique if keep(row)]
    unique.sort(key=lambda row: row.get("activity_date") or row.get("created_at") or "", reverse=sort != "asc")
    conn.close()
    return unique

@app.get("/api/crm/client/{client_id}/departments")
def crm_client_departments(client_id: int):
    conn = db()
    crm_client_row(conn, client_id)
    rows = [dict(r) for r in conn.execute("SELECT * FROM client_departments WHERE client_id=? ORDER BY department_name", (client_id,)).fetchall()]
    conn.close()
    return rows

@app.post("/api/crm/client/{client_id}/departments")
def create_crm_client_department(client_id: int, payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="CRM edit permission required")
    conn = db()
    crm_client_row(conn, client_id)
    department_id = ensure_department(
        conn,
        client_id,
        payload.get("department_name", ""),
        floor_location=payload.get("floor_location", ""),
        main_contact_name=payload.get("main_contact_name", ""),
        phone=payload.get("phone", ""),
        email=payload.get("email", ""),
        notes=payload.get("notes", ""),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM client_departments WHERE id=?", (department_id,)).fetchone())
    conn.close()
    return row

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

@app.get("/api/cases/workflows")
def case_workflow_definitions():
    return {
        "case_types": sorted(CASE_TYPES),
        "request_sources": sorted(REQUEST_SOURCES),
        "item_types": sorted(LINE_ITEM_TYPES),
        "procurement_statuses": sorted(PROCUREMENT_STATUSES),
        "documents": sorted(GENERATABLE_DOCUMENT_TYPES),
        "workflows": SOP_WORKFLOWS,
        "case_type_workflows": CASE_TYPE_WORKFLOW,
    }

@app.get("/api/traceability/{reference}")
def get_traceability(reference: str):
    conn = db()
    data = traceability_data(conn, reference)
    conn.commit()
    conn.close()
    return data

@app.get("/api/search")
def global_search(q: str):
    text = str(q or "").strip()
    if not text:
        return {"query": text, "results": []}
    like = f"%{text}%"
    conn = db()
    results = []
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, case_no AS label, 'case' AS type, client_id, id AS case_id
        FROM cases
        WHERE parent_case_reference LIKE ? OR external_reference LIKE ? OR case_no LIKE ? OR notes LIKE ?
        LIMIT 30
    """, (like, like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, quotation_no AS label, 'quotation' AS type, client_id, NULL AS case_id
        FROM quotations
        WHERE quotation_no LIKE ? OR document_reference LIKE ? OR parent_case_reference LIKE ? OR external_reference LIKE ?
        LIMIT 20
    """, (like, like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, doc_no AS label, doc_type AS type, client_id, parent_case_id AS case_id
        FROM sales_case_documents
        WHERE doc_no LIKE ? OR document_reference LIKE ? OR parent_case_reference LIKE ? OR external_reference LIKE ?
        LIMIT 30
    """, (like, like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, client_order_no AS label, 'client_order' AS type, client_id, parent_case_id AS case_id
        FROM client_orders
        WHERE client_order_no LIKE ? OR document_reference LIKE ? OR parent_case_reference LIKE ? OR client_name LIKE ?
        LIMIT 20
    """, (like, like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, po_no AS label, 'purchase_order' AS type, client_id, parent_case_id AS case_id
        FROM purchase_orders
        WHERE po_no LIKE ? OR document_reference LIKE ? OR parent_case_reference LIKE ? OR supplier LIKE ? OR external_reference LIKE ?
        LIMIT 20
    """, (like, like, like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, call_no AS label, 'service_call' AS type, client_id, parent_case_id AS case_id
        FROM service_calls
        WHERE call_no LIKE ? OR parent_case_reference LIKE ? OR issue LIKE ?
        LIMIT 20
    """, (like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT parent_case_reference AS reference, doc_no AS label, 'invoice' AS type, client_id, parent_case_id AS case_id
        FROM invoices
        WHERE doc_no LIKE ? OR document_reference LIKE ? OR parent_case_reference LIKE ?
        LIMIT 20
    """, (like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT a.parent_case_reference AS reference, a.asset_tag || ' / ' || a.serial_number AS label,
               'equipment' AS type, a.client_id, a.parent_case_id AS case_id
        FROM pm_assets a
        WHERE a.asset_tag LIKE ? OR a.serial_number LIKE ? OR a.model LIKE ? OR a.hospital LIKE ? OR a.manufacturer LIKE ?
        LIMIT 30
    """, (like, like, like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT '' AS reference, name AS label, 'client' AS type, id AS client_id, NULL AS case_id
        FROM clients
        WHERE name LIKE ? OR city LIKE ? OR main_contact LIKE ?
        LIMIT 20
    """, (like, like, like)).fetchall():
        results.append(dict(row))
    for row in conn.execute("""
        SELECT '' AS reference, department_name AS label, 'department' AS type, client_id, NULL AS case_id
        FROM departments
        WHERE department_name LIKE ? OR floor_location LIKE ? OR main_contact_name LIKE ?
        LIMIT 20
    """, (like, like, like)).fetchall():
        results.append(dict(row))
    seen = set()
    unique = []
    for item in results:
        key = (item.get("type"), item.get("label"), item.get("reference"), item.get("client_id"))
        if key in seen:
            continue
        seen.add(key)
        item["url"] = f"/crm/client/{item.get('client_id')}" if item.get("client_id") else "/dashboard"
        if item.get("reference"):
            item["traceability_url"] = f"/api/traceability/{urllib.parse.quote(str(item.get('reference')))}"
        unique.append(item)
    conn.close()
    return {"query": text, "results": unique[:80]}

@app.get("/api/imports")
def list_import_batches(limit: int = 50):
    conn = db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM import_batches ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
    conn.close()
    return rows

@app.get("/api/imports/{batch_id}/rows")
def list_import_batch_rows(batch_id: int):
    conn = db()
    rows = []
    for row in conn.execute("SELECT * FROM import_batch_rows WHERE batch_id=? ORDER BY row_no", (batch_id,)).fetchall():
        item = dict(row)
        item["raw_data"] = json.loads(item.get("raw_data") or "{}")
        item["mapped_data"] = json.loads(item.get("mapped_data") or "{}")
        rows.append(item)
    conn.close()
    return rows

@app.post("/api/imports/pending-offers/preview")
async def preview_pending_offers_import(request: Request, file: UploadFile = File(...), field_map_json: str = Form("")):
    contents = await file.read()
    try:
        imported_df = read_import_dataframe(contents, file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read pending offers import file: {exc}")
    field_map = None
    if field_map_json:
        try:
            raw_map = json.loads(field_map_json)
            field_map = {k: v for k, v in raw_map.items() if v}
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid field_map_json: {exc}")
    rows = parse_pending_offer_dataframe(imported_df, field_map)
    conn = db()
    cur = conn.execute("""
        INSERT INTO import_batches (import_type, filename, status, total_rows, valid_rows, error_rows, created_by, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "pending_offers", file.filename or "upload", "preview", len(rows),
        sum(1 for row in rows if row["validation_status"] == "valid"),
        sum(1 for row in rows if row["validation_status"] == "error"),
        request.session.get("username", "system"), now(), "Pending calls/offers preview",
    ))
    batch_id = cur.lastrowid
    for row in rows:
        client = conn.execute("SELECT id FROM clients WHERE lower(trim(name))=lower(trim(?))", (row.get("hospital", ""),)).fetchone()
        existing_case = find_case_by_reference(conn, row.get("offer_reference", ""))
        row["existing_client_id"] = client["id"] if client else None
        row["existing_case_id"] = existing_case["id"] if existing_case else None
        row["planned_action"] = "update" if existing_case else "create"
        conn.execute("""
            INSERT INTO import_batch_rows
            (batch_id, row_no, raw_data, mapped_data, validation_status, error_message, action, client_id, case_id,
             parent_case_reference, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            batch_id, row["row_no"], json.dumps(row["raw_data"]), json.dumps(row),
            row["validation_status"], "; ".join(row.get("errors") or []), row["planned_action"],
            row["existing_client_id"], row["existing_case_id"],
            existing_case["parent_case_reference"] if existing_case else "", now(), now(),
        ))
    conn.commit()
    conn.close()
    return {
        "batch_id": batch_id,
        "columns": [str(col) for col in imported_df.columns],
        "field_map": {**default_pending_offer_field_map(imported_df), **(field_map or {})},
        "rows": rows,
        "summary": {
            "total_rows": len(rows),
            "valid_rows": sum(1 for row in rows if row["validation_status"] == "valid"),
            "error_rows": sum(1 for row in rows if row["validation_status"] == "error"),
            "create_rows": sum(1 for row in rows if row.get("planned_action") == "create"),
            "update_rows": sum(1 for row in rows if row.get("planned_action") == "update"),
        },
    }

@app.post("/api/imports/pending-offers/commit")
def commit_pending_offers_import(payload: dict, request: Request):
    batch_id = payload.get("batch_id")
    create_missing = bool(payload.get("create_missing_hospitals", True))
    conn = db()
    rows = payload.get("rows")
    if batch_id and not rows:
        rows = []
        for row in conn.execute("SELECT * FROM import_batch_rows WHERE batch_id=? ORDER BY row_no", (batch_id,)).fetchall():
            mapped = json.loads(row["mapped_data"] or "{}")
            rows.append(mapped)
    if not isinstance(rows, list) or not rows:
        conn.close()
        raise HTTPException(status_code=400, detail="No import rows provided")
    results = commit_pending_offer_rows(conn, rows, int(batch_id) if batch_id else None, request.session.get("username", "system"), create_missing)
    imported = sum(1 for item in results if item.get("status") == "imported")
    errors = sum(1 for item in results if item.get("status") == "error")
    if batch_id:
        conn.execute("""
            UPDATE import_batches
            SET status=?, valid_rows=?, error_rows=?, committed_at=?, notes=?
            WHERE id=?
        """, ("committed_with_errors" if errors else "committed", imported, errors, now(), f"Imported {imported}; errors {errors}", batch_id))
    conn.commit()
    conn.close()
    return {"batch_id": batch_id, "imported": imported, "errors": errors, "results": results}

@app.post("/api/imports/{batch_id}/rollback")
def rollback_import_batch(batch_id: int, request: Request):
    conn = db()
    batch = conn.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        raise HTTPException(status_code=404, detail="Import batch not found")
    rows = [dict(r) for r in conn.execute("SELECT * FROM import_batch_rows WHERE batch_id=?", (batch_id,)).fetchall()]
    touched = 0
    for row in rows:
        if row.get("action") != "created":
            continue
        case_id = row.get("case_id")
        request_id = row.get("request_id")
        parent_ref = row.get("parent_case_reference")
        if case_id:
            conn.execute("UPDATE cases SET status='cancelled', blocked_reason='none', updated_at=? WHERE id=?", (now(), case_id))
            case_timeline(conn, parent_ref, case_id, "import_rollback", "Import row rolled back", "cancelled", request.session.get("username", "system"), f"Batch {batch_id}", "import_batches", batch_id)
            touched += 1
        if request_id:
            conn.execute("UPDATE customer_requests SET status='cancelled', updated_at=? WHERE id=?", (now(), request_id))
        conn.execute("UPDATE quotations SET status='cancelled', updated_at=? WHERE parent_case_reference=?", (now(), parent_ref))
        conn.execute("UPDATE sales_case_documents SET status='cancelled', updated_at=? WHERE parent_case_reference=?", (now(), parent_ref))
    conn.execute("UPDATE import_batches SET status='rolled_back', rolled_back_at=?, notes=? WHERE id=?", (now(), f"Soft-rolled back {touched} created cases", batch_id))
    conn.commit()
    conn.close()
    return {"batch_id": batch_id, "rolled_back_cases": touched, "message": "Created rows were soft-cancelled, not destructively deleted."}

def bulk_target_table(target: str):
    table = BULK_TARGETS.get(str(target or "").strip())
    if not table:
        raise HTTPException(status_code=400, detail=f"Unsupported bulk target: {target}")
    return table

def bulk_field_column(table_cols: set[str], field: str):
    aliases = {
        "responsible_person": ["responsible_person", "engineer", "assigned_to"],
        "engineer": ["engineer", "assigned_to", "responsible_person"],
        "assigned_to": ["assigned_to", "engineer", "responsible_person"],
        "equipment_id": ["equipment_id", "asset_id"],
        "contract_id": ["contract_id", "contract_no"],
        "due_date": ["due_date", "expected_date", "next_pm_date"],
        "blocked_by": ["blocked_reason"],
        "client_id": ["client_id"],
        "department_id": ["department_id"],
        "status": ["status"],
        "priority": ["priority"],
        "blocked_reason": ["blocked_reason"],
        "blocked_notes": ["blocked_notes"],
        "client_informed": ["client_informed"],
        "date_informed": ["date_informed"],
        "informed_by": ["informed_by"],
        "communication_method": ["communication_method"],
        "informed_notes": ["informed_notes"],
        "notes": ["notes"],
    }
    for candidate in aliases.get(field, [field]):
        if candidate in table_cols:
            return candidate
    return None

@app.post("/api/bulk-edit")
def bulk_edit(payload: dict, request: Request):
    role = current_role(request)
    if not can_edit_crm(role):
        raise HTTPException(status_code=403, detail="Edit permission required")
    target = payload.get("target")
    ids = payload.get("ids") or []
    updates = payload.get("updates") or {}
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty list")
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(status_code=400, detail="updates must be provided")
    table = bulk_target_table(target)
    conn = db()
    table_cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    set_parts = []
    values = []
    skipped_fields = []
    for field, value in updates.items():
        if field == "delete":
            continue
        column = bulk_field_column(table_cols, field)
        if not column:
            skipped_fields.append(field)
            continue
        if column == "blocked_reason":
            value = normalize_blocked_reason(value)
        if column == "client_informed":
            value = 1 if bool(value) else 0
            if value and "date_informed" in table_cols and "date_informed" not in updates:
                set_parts.append("date_informed=?")
                values.append(now())
        set_parts.append(f"{column}=?")
        values.append(value)
    if "updated_at" in table_cols:
        set_parts.append("updated_at=?")
        values.append(now())
    if not set_parts:
        conn.close()
        raise HTTPException(status_code=400, detail="No supported fields for this target")
    placeholders = ",".join("?" for _ in ids)
    conn.execute(f"UPDATE {table} SET {', '.join(set_parts)} WHERE id IN ({placeholders})", [*values, *ids])
    updated = conn.total_changes
    if table == "pm_assets" and "department_id" in updates:
        dept = conn.execute("SELECT department_name FROM departments WHERE id=?", (updates["department_id"],)).fetchone()
        if dept:
            conn.execute(f"UPDATE pm_assets SET department=? WHERE id IN ({placeholders})", [dept["department_name"], *ids])
    if table in {"cases", "customer_requests"}:
        for row in conn.execute(f"SELECT id, parent_case_reference, parent_case_id, status, blocked_reason FROM {table} WHERE id IN ({placeholders})", ids).fetchall():
            case_timeline(conn, row["parent_case_reference"], row["parent_case_id"] or row["id"], "bulk_edit", "Bulk edit applied", row["status"], request.session.get("username", "system"), json.dumps(updates), table, row["id"])
    conn.commit()
    conn.close()
    return {"target": target, "table": table, "requested": len(ids), "updated": updated, "skipped_fields": skipped_fields}

@app.post("/api/bulk-export")
def bulk_export(payload: dict):
    target = payload.get("target")
    ids = payload.get("ids") or []
    fmt = payload.get("format", "excel")
    if not ids:
        raise HTTPException(status_code=400, detail="ids must be provided")
    table = bulk_target_table(target)
    conn = db()
    placeholders = ",".join("?" for _ in ids)
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE id IN ({placeholders})", ids).fetchall()]
    conn.close()
    return export_rows_response(f"{target}_selected_export", rows, fmt, f"Selected {target} rows")

@app.get("/api/exports/{report_name}")
def export_operational_report(report_name: str, format: str = "excel", client_id: int | None = None, batch_id: int | None = None):
    conn = db()
    report_key = report_name.replace("-", "_")
    if report_key in {"hospital_dashboard_summary", "hospitals"}:
        rows = hospital_dashboard_rows(conn)
        title = "hospital_dashboard_summary"
    elif report_key == "department_progress":
        if client_id:
            rows = department_progress_rows(conn, client_id)
        else:
            rows = []
            for client in conn.execute("SELECT id FROM clients ORDER BY name").fetchall():
                rows.extend(department_progress_rows(conn, client["id"]))
        title = "department_progress"
    elif report_key in {"pending_calls", "service_calls"}:
        rows = [dict(r) for r in conn.execute("""
            SELECT s.*, c.name AS client_name, d.department_name
            FROM service_calls s
            LEFT JOIN clients c ON c.id=s.client_id
            LEFT JOIN departments d ON d.id=s.department_id
            WHERE (? IS NULL OR s.client_id=?)
              AND lower(COALESCE(s.status, 'open')) NOT IN ('closed', 'resolved', 'cancelled')
            ORDER BY COALESCE(s.opened_at, s.created_at) DESC
        """, (client_id, client_id)).fetchall()]
        title = "pending_calls"
    elif report_key == "import_validation":
        if not batch_id:
            rows = [dict(r) for r in conn.execute("SELECT * FROM import_batches ORDER BY created_at DESC LIMIT 100").fetchall()]
        else:
            rows = [dict(r) for r in conn.execute("SELECT * FROM import_batch_rows WHERE batch_id=? ORDER BY row_no", (batch_id,)).fetchall()]
        title = "import_validation"
    elif report_key == "equipment_database":
        sync_core_reference_tables(conn)
        rows = [dict(r) for r in conn.execute("""
            SELECT e.id, e.pm_asset_id, e.client_id, e.department_id,
                   COALESCE(a.equipment_name, e.asset_tag, e.model) AS equipment_name,
                   COALESCE(a.equipment_family, em.equipment_family, '') AS equipment_family,
                   e.asset_tag, e.serial_number, e.manufacturer, e.model,
                   COALESCE(a.status, e.status) AS status,
                   COALESCE(a.lifecycle_status, '') AS lifecycle_status,
                   a.location, a.installation_date, a.contract_no,
                   a.contract_start_date, a.contract_end_date,
                   a.frequency_days AS pm_frequency_days, a.last_pm_date, a.next_pm_date,
                   a.last_service_date, a.calibration_required, a.calibration_due_date,
                   a.risk_level AS risk_classification, a.life_support,
                   c.name AS client_name, d.department_name,
                   COALESCE(w.warranty_start, a.warranty_start) AS warranty_start,
                   COALESCE(w.warranty_end, a.warranty_end) AS warranty_end,
                   COALESCE(w.status, a.warranty_status) AS warranty_status
            FROM equipment e
            LEFT JOIN pm_assets a ON a.id=e.pm_asset_id
            LEFT JOIN equipment_models em ON em.id=e.equipment_model_id
            LEFT JOIN clients c ON c.id=e.client_id
            LEFT JOIN departments d ON d.id=e.department_id
            LEFT JOIN warranties w ON w.equipment_id=e.id
            WHERE (? IS NULL OR e.client_id=?)
            ORDER BY c.name, d.department_name, e.asset_tag
        """, (client_id, client_id)).fetchall()]
        title = "equipment_database"
    elif report_key == "procurement":
        sync_core_reference_tables(conn)
        rows = procurement_dashboard_data(conn).get("requested_shortages", [])
        title = "procurement_alerts"
    elif report_key == "sales_requests":
        sync_core_reference_tables(conn)
        rows = sales_dashboard_data(conn).get("requests", [])
        title = "sales_requests"
    elif report_key == "pm_schedule":
        rows = [dict(r) for r in conn.execute("""
            SELECT t.*, a.asset_tag, a.hospital, a.department, a.model, a.serial_number
            FROM pm_tasks t LEFT JOIN pm_assets a ON a.id=t.asset_id
            WHERE (? IS NULL OR a.client_id=?)
            ORDER BY COALESCE(t.due_date, ''), t.status
        """, (client_id, client_id)).fetchall()]
        title = "pm_schedule"
    elif report_key == "blocked_items":
        rows = blocked_item_rows(conn, client_id, None, 1000)
        title = "blocked_items"
    elif report_key == "pending_procurement":
        rows = [dict(r) for r in conn.execute("""
            SELECT i.*, r.case_no, r.client_hospital, r.parent_case_reference, r.department_id
            FROM customer_request_items i
            JOIN customer_requests r ON r.id=i.request_id
            WHERE (? IS NULL OR r.client_id=?)
              AND (COALESCE(i.shortage_qty,0) > 0
                   OR COALESCE(i.procurement_status,'not_ordered') IN ('not_ordered','po_draft','po_sent','supplier_confirmed','partially_received'))
            ORDER BY i.updated_at DESC
        """, (client_id, client_id)).fetchall()]
        title = "pending_procurement"
    else:
        conn.close()
        raise HTTPException(status_code=404, detail="Unknown export report")
    conn.close()
    return export_rows_response(title, rows, format, report_name.replace("_", " ").title())

@app.post("/api/cases")
def create_case(case: CaseCreate):
    conn = db()
    case_type = validate_case_type(case.case_type)
    workflow_state = initial_workflow_state(case_type)
    parent_case_reference = generate_parent_case_reference(conn)
    case_no = f"CASE-{datetime.now().strftime('%y%m%d%H%M%S%f')}"
    cur = conn.execute("""
        INSERT INTO cases (case_no, case_type, client_id, contact_id, equipment_id, request_id,
                          quotation_id, client_order_id, purchase_order_id, delivery_note_id,
                          invoice_id, engineer_id, contract_id, priority, notes, created_at, updated_at,
                          parent_case_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_no, case_type, case.client_id, case.contact_id, case.equipment_id, case.request_id,
          case.quotation_id, case.client_order_id, case.purchase_order_id, case.delivery_note_id,
          case.invoice_id, case.engineer_id, case.contract_id, case.priority, case.notes, now(), now(),
          parent_case_reference))
    case_id = cur.lastrowid
    conn.execute("UPDATE cases SET workflow_state=?, parent_case_id=? WHERE id=?", (workflow_state, case_id, case_id))
    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, workflow_state, now(), "system", "Case created"))
    case_timeline(conn, parent_case_reference, case_id, "case_created", "Case created", "open", "system", case.notes, "cases", case_id)
    conn.commit()
    conn.close()
    return {"id": case_id, "case_no": case_no, "parent_case_reference": parent_case_reference, "message": "Case created successfully"}

@app.get("/api/cases")
def list_cases(case_type: str = "", client_id: int | None = None):
    conn = db()
    where = "WHERE 1=1"
    params = []
    if case_type:
        where += " AND cases.case_type = ?"
        params.append(case_type)
    if client_id:
        where += " AND cases.client_id = ?"
        params.append(client_id)
    rows = conn.execute(f"""
        SELECT cases.id, cases.case_no, cases.case_type, cases.client_id, clients.name AS client_name,
               cases.department_id, departments.department_name,
               cases.parent_case_reference, cases.external_reference,
               cases.workflow_state, cases.status, cases.priority,
               cases.blocked_reason, cases.responsible_person, cases.due_date,
               cases.created_at, cases.updated_at
        FROM cases
        LEFT JOIN clients ON clients.id=cases.client_id
        LEFT JOIN departments ON departments.id=cases.department_id
        {where} ORDER BY cases.created_at DESC
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
    case_data["workflow_key"] = workflow_key_for_case_type(case_data["case_type"])
    case_data["allowed_states"] = workflow_states_for_case_type(case_data["case_type"])
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
    case_row = conn.execute("SELECT workflow_state, case_type FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")
    allowed = workflow_states_for_case_type(case_row["case_type"])
    if state_change.state not in allowed:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Unsupported workflow state for {case_row['case_type']}: {state_change.state}")
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

@app.get("/api/cases/{case_id}/summary")
def get_case_summary(case_id: int):
    conn = db()
    case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")

    case_data = dict(case_row)
    request_id = case_data.get("request_id")

    if request_id:
        request_data = request_with_lines(conn, request_id)
        case_data["customer_request"] = request_data
        case_data["total_items"] = len(request_data.get("lines", []))
        case_data["total_shortage"] = sum(l.get("shortage_qty", 0) for l in request_data.get("lines", []))
        case_data["total_available"] = sum(l.get("available_qty", 0) for l in request_data.get("lines", []))

    conn.close()
    return case_data

@app.post("/api/cases/{case_id}/auto-procure-shortages")
def auto_create_po_for_shortages(case_id: int):
    conn = db()
    case_row = conn.execute("SELECT request_id, client_id, department_id, parent_case_reference FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row or not case_row["request_id"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Case has no customer request")

    request_id = case_row["request_id"]
    shortage_lines = conn.execute("""
        SELECT id, requested_item, shortage_qty, pn FROM customer_request_items
        WHERE request_id = ? AND shortage_qty > 0 AND procurement_status = 'not_ordered'
    """, (request_id,)).fetchall()

    if not shortage_lines:
        conn.close()
        return {"message": "No shortages to procure"}

    po_no = f"PO-{int(datetime.now().timestamp())}"
    po_cur = conn.execute("""
        INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at, request_id, client_id, case_id,
                                     parent_case_reference, parent_case_id, document_reference, department_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (po_no, "To be assigned", "draft", add_days_iso(date.today().isoformat(), 7), f"Auto-generated for case {case_id}", now(), now(), request_id, case_row["client_id"], case_id,
          case_row["parent_case_reference"], case_id, document_reference_for(case_row["parent_case_reference"], "purchase_order"), case_row["department_id"]))
    po_id = po_cur.lastrowid

    for line in shortage_lines:
        conn.execute("""
            INSERT INTO purchase_order_items (po_no, pn, description, qty, created_at, updated_at, request_id, request_item_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (po_no, line["pn"] or "", line["requested_item"], line["shortage_qty"], now(), now(), request_id, line["id"]))
        conn.execute("""
            UPDATE customer_request_items SET procurement_status = 'po_draft', linked_purchase_order = ? WHERE id = ?
        """, (po_no, line["id"]))
    conn.execute("UPDATE cases SET purchase_order_id=?, updated_at=? WHERE id=?", (po_id, now(), case_id))
    advance_case_for_request(conn, request_id, "parts_request_if_needed", f"PO {po_no} drafted for shortage items")
    refresh_case_links(conn, request_id)

    conn.commit()
    conn.close()
    return {"po_no": po_no, "po_id": po_id, "lines_count": len(shortage_lines), "message": "Purchase order created"}

@app.post("/api/cases/{case_id}/complete-workflow")
def complete_case_workflow(case_id: int, final_status: str = "completed"):
    conn = db()
    case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")

    conn.execute("""
        UPDATE cases SET status = ?, workflow_state = ?, updated_at = ?
        WHERE id = ?
    """, (final_status, "completed", now(), case_id))

    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, "completed", now(), "system", f"Case marked as {final_status}"))
    case_timeline(conn, case_row["parent_case_reference"], case_id, "workflow_state", "Case completed", final_status, "system", f"Case marked as {final_status}", "cases", case_id)

    conn.commit()
    conn.close()
    return {"message": f"Case workflow completed with status: {final_status}"}

@app.post("/api/unified-case-entry")
def create_unified_case(case_entry: UnifiedCaseEntryIn, request: Request):
    if not case_entry.client_hospital.strip():
        raise HTTPException(status_code=400, detail="Client/hospital is required")
    if not case_entry.line_items:
        raise HTTPException(status_code=400, detail="At least one line item is required")
    case_type = validate_case_type(case_entry.case_type)
    request_source = normalize_request_source(case_entry.request_source)
    workflow_state = initial_workflow_state(case_type)

    conn = db()
    client_id = ensure_client(conn, case_entry.client_hospital.strip(), main_contact=case_entry.contact_person)
    department_id = ensure_department(conn, client_id, case_entry.department, main_contact_name=case_entry.contact_person)
    contact_id = ensure_contact(conn, client_id, case_entry.contact_person, case_entry.department)
    parent_case_reference = generate_parent_case_reference(conn)

    case_no = f"CASE-{datetime.now().strftime('%y%m%d%H%M%S%f')}"
    cur = conn.execute("""
        INSERT INTO customer_requests (case_no, client_id, client_hospital, contact_person, request_source, status, notes, created_at, updated_at, department, department_id, contact_id, parent_case_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_no, client_id, case_entry.client_hospital.strip(), case_entry.contact_person, request_source, "open", case_entry.notes, now(), now(), case_entry.department, department_id, contact_id, parent_case_reference))
    request_id = cur.lastrowid

    case_cur = conn.execute("""
        INSERT INTO cases (case_no, case_type, client_id, contact_id, request_id, priority, status, workflow_state, created_at, updated_at, notes, department, department_id, request_source, parent_case_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_no, case_type, client_id, contact_id, request_id, case_entry.priority, "open", workflow_state, now(), now(), case_entry.notes, case_entry.department, department_id, request_source, parent_case_reference))
    case_id = case_cur.lastrowid
    conn.execute("UPDATE cases SET parent_case_id=? WHERE id=?", (case_id, case_id))
    conn.execute("UPDATE customer_requests SET parent_case_id=? WHERE id=?", (case_id, request_id))

    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, workflow_state, now(), request.session.get("username", "system"), "Unified case entry created"))

    total_shortage = 0
    for line in case_entry.line_items:
        if not line.requested_item.strip():
            continue
        item_type = validate_item_type(line.item_type)
        if int(line.quantity or 0) <= 0:
            raise HTTPException(status_code=400, detail="Line quantities must be positive")

        inv = find_inventory_for_request_item(conn, line.requested_item) if item_type in STOCK_ITEM_TYPES else None
        cur_line = conn.execute("""
            INSERT INTO customer_request_items
            (request_id, requested_item, item_type, quantity, unit_price, notes, related_equipment_serial,
             inventory_item_id, pn, procurement_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request_id, line.requested_item.strip(), item_type, int(line.quantity), float(line.unit_price or 0),
            line.notes, line.related_equipment_serial, inv["id"] if inv else None, inv["pn"] if inv else "",
            "not_ordered", now(), now()
        ))
        line_data = sync_case_line_stock(conn, cur_line.lastrowid)
        if line_data:
            total_shortage += line_data.get("shortage_qty", 0)

    if case_entry.auto_reserve_available:
        reserve_customer_request_stock_in_conn(conn, request_id)
    total_shortage = sum(
        int((sync_case_line_stock(conn, line["id"]) or {}).get("shortage_qty", 0))
        for line in conn.execute("SELECT id FROM customer_request_items WHERE request_id=?", (request_id,)).fetchall()
    )

    if case_entry.auto_create_po and total_shortage > 0:
        po_no = f"PO-{datetime.now().strftime('%y%m%d%H%M%S%f')}"
        po_cur = conn.execute("""
            INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at, request_id, case_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (po_no, "To be assigned", "draft", add_days_iso(date.today().isoformat(), 7), f"Auto-generated for {case_no}", now(), now(), request_id, case_id))
        conn.execute("""
            UPDATE purchase_orders
            SET parent_case_reference=?, parent_case_id=?, document_reference=?, client_id=?, department_id=?
            WHERE id=?
        """, (parent_case_reference, case_id, document_reference_for(parent_case_reference, "purchase_order"), client_id, department_id, po_cur.lastrowid))

        for line in conn.execute("SELECT * FROM customer_request_items WHERE request_id = ? AND shortage_qty > 0", (request_id,)).fetchall():
            conn.execute("""
                INSERT INTO purchase_order_items (po_no, pn, description, qty, created_at, updated_at, request_id, request_item_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (po_no, line["pn"] or "", line["requested_item"], line["shortage_qty"], now(), now(), request_id, line["id"]))
            conn.execute("UPDATE customer_request_items SET procurement_status = 'po_draft', linked_purchase_order = ? WHERE id = ?",
                        (po_no, line["id"]))
        conn.execute("UPDATE cases SET purchase_order_id=?, updated_at=? WHERE id=?", (po_cur.lastrowid, now(), case_id))

    conn.execute("""
        INSERT INTO crm_communications (client_id, type, user, note, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, "customer_request", request.session.get("username", "system"), f"Created unified case {case_no}", now()))

    case_timeline(conn, parent_case_reference, case_id, "case_created", "Unified case created", "open", request.session.get("username", "system"), case_entry.notes, "customer_requests", request_id)
    refresh_case_links(conn, request_id)
    conn.commit()
    data = request_with_lines(conn, request_id)
    conn.close()
    export_excel(EXCEL_PATH)

    return {
        "case_id": case_id,
        "case_no": case_no,
        "parent_case_reference": parent_case_reference,
        "request_id": request_id,
        "client_id": client_id,
        "total_items": len(case_entry.line_items),
        "total_shortage": total_shortage,
        "auto_po_created": case_entry.auto_create_po and total_shortage > 0,
        "customer_request": data,
        "message": "Unified case created successfully"
    }

@app.get("/api/commercial/products")
def list_commercial_products(q: str = "", product_type: str = "", active: int | None = None):
    conn = db()
    try:
        clauses = []
        params = []
        if q:
            clauses.append("(ref LIKE ? OR description LIKE ? OR brand LIKE ? OR model LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like, like])
        if product_type:
            clauses.append("product_type=?")
            params.append(product_type)
        if active is not None:
            clauses.append("active=?")
            params.append(active)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [dict(r) for r in conn.execute(f"SELECT * FROM products {where} ORDER BY active DESC, ref, description", params).fetchall()]
    finally:
        conn.close()

@app.post("/api/commercial/products")
def create_commercial_product(payload: dict):
    return create_product(payload)

@app.post("/api/commercial/quotations")
def create_commercial_quotation_api(payload: dict):
    return create_commercial_quotation(
        customer_id=int(payload.get("customer_id") or payload.get("client_id") or 0),
        items=payload.get("items") or [],
        quotation_no=payload.get("quotation_no", ""),
        status=payload.get("status", "draft"),
        quotation_date=payload.get("quotation_date", ""),
        valid_until=payload.get("valid_until", ""),
        notes=payload.get("notes", ""),
    )

@app.post("/api/commercial/quotations/{quotation_id}/approve")
def approve_commercial_quotation_api(quotation_id: int):
    return approve_quotation(quotation_id)

@app.get("/api/commercial/stock-items")
def list_commercial_stock_items(status: str = "", customer_order_id: int | None = None, co_no: str = ""):
    conn = db()
    try:
        clauses = []
        params = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if customer_order_id is not None:
            clauses.append("customer_order_id=?")
            params.append(customer_order_id)
        if co_no:
            clauses.append("co_no=?")
            params.append(co_no)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return [dict(r) for r in conn.execute(f"SELECT * FROM stock_items {where} ORDER BY created_at DESC, id DESC", params).fetchall()]
    finally:
        conn.close()

@app.post("/api/commercial/purchase-orders")
def create_commercial_purchase_order_api(payload: dict):
    return create_purchase_order_from_stock_items(
        supplier_id=int(payload.get("supplier_id") or 0),
        stock_item_ids=[int(item_id) for item_id in payload.get("stock_item_ids", [])],
        notes=payload.get("notes", ""),
    )

@app.post("/api/commercial/shipments")
def create_commercial_shipment_api(payload: dict):
    return create_shipment_from_purchase_order_items(
        purchase_order_item_ids=[int(item_id) for item_id in payload.get("purchase_order_item_ids", [])],
        supplier_id=payload.get("supplier_id"),
        shipment_no=payload.get("shipment_no", ""),
        notes=payload.get("notes", ""),
    )

@app.post("/api/commercial/shipments/{shipment_id}/receive")
def receive_commercial_shipment_api(shipment_id: int):
    return receive_shipment(shipment_id)

@app.post("/api/commercial/delivery-orders")
def create_commercial_delivery_order_api(payload: dict):
    return create_delivery_order(
        customer_id=int(payload.get("customer_id") or 0),
        customer_order_id=int(payload.get("customer_order_id") or 0),
        stock_item_ids=[int(item_id) for item_id in payload.get("stock_item_ids", [])],
        notes=payload.get("notes", ""),
    )

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
    request_source = normalize_request_source(payload.request_source)
    case_type = infer_case_type_from_lines(payload.lines)
    workflow_state = initial_workflow_state(case_type)
    conn = db()
    client_id = ensure_client(conn, payload.client_hospital.strip(), main_contact=payload.contact_person)
    department_id = ensure_department(conn, client_id, payload.department, main_contact_name=payload.contact_person)
    contact_id = ensure_contact(conn, client_id, payload.contact_person, payload.department)
    parent_case_reference = generate_parent_case_reference(conn)
    cur = conn.execute("""
        INSERT INTO customer_requests (case_no, client_id, client_hospital, contact_person, request_source, status, notes, created_at, updated_at, department, department_id, contact_id, parent_case_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("PENDING", client_id, payload.client_hospital.strip(), payload.contact_person, request_source, "open", payload.notes, now(), now(), payload.department, department_id, contact_id, parent_case_reference))
    request_id = cur.lastrowid
    case_no = make_doc_no("CASE", request_id)
    conn.execute("UPDATE customer_requests SET case_no=? WHERE id=?", (case_no, request_id))

    case_cur = conn.execute("""
        INSERT INTO cases (case_no, case_type, client_id, contact_id, request_id, status, workflow_state, created_at, updated_at, notes, department, department_id, request_source, parent_case_reference)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (case_no, case_type, client_id, contact_id, request_id, "open", workflow_state, now(), now(), payload.notes, payload.department, department_id, request_source, parent_case_reference))
    case_id = case_cur.lastrowid
    conn.execute("UPDATE cases SET parent_case_id=? WHERE id=?", (case_id, case_id))
    conn.execute("UPDATE customer_requests SET parent_case_id=? WHERE id=?", (case_id, request_id))
    conn.execute("""
        INSERT INTO case_workflow_states (case_id, state, timestamp, user, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (case_id, workflow_state, now(), "system", f"Customer request {case_no} created"))

    for line in payload.lines:
        if not line.requested_item.strip():
            continue
        item_type = validate_item_type(line.item_type)
        if int(line.quantity or 0) <= 0:
            raise HTTPException(status_code=400, detail="Line quantities must be positive")
        inv = find_inventory_for_request_item(conn, line.requested_item) if item_type in STOCK_ITEM_TYPES else None
        cur_line = conn.execute("""
            INSERT INTO customer_request_items
            (request_id, requested_item, item_type, quantity, unit_price, notes, related_equipment_serial,
             inventory_item_id, pn, procurement_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request_id, line.requested_item.strip(), item_type, int(line.quantity), float(line.unit_price or 0),
            line.notes, line.related_equipment_serial, inv["id"] if inv else None, inv["pn"] if inv else "",
            "not_ordered", now(), now()
        ))
        sync_case_line_stock(conn, cur_line.lastrowid)
    conn.execute("""
        INSERT INTO crm_communications (client_id, type, user, note, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (client_id, "customer_request", request.session.get("username", current_role(request)), f"Created {case_no}", now()))
    case_timeline(conn, parent_case_reference, case_id, "case_created", "Customer request created", "open", request.session.get("username", current_role(request)), payload.notes, "customer_requests", request_id)
    refresh_case_links(conn, request_id)
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
    allowed = {"quotation", "pro_forma", "service_report", "pm_report", "installation_report", "acceptance_test_report"}
    if doc_type not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported document generation action")
    conn = db()
    doc = create_sales_document(conn, request_id, doc_type, "draft", "Generated from Customer Request")
    if doc_type == "quotation":
        req = conn.execute("SELECT * FROM customer_requests WHERE id=?", (request_id,)).fetchone()
        quote = conn.execute("SELECT * FROM quotations WHERE quotation_no=? ORDER BY id DESC LIMIT 1", (doc["doc_no"],)).fetchone()
        if not quote:
            conn.execute("""
                INSERT INTO quotations (client_id, equipment_id, service_call_id, quotation_no, quote_date, status, amount, notes, created_at, updated_at, request_id, contact_person,
                                        parent_case_reference, parent_case_id, document_reference, department_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (req["client_id"], None, None, doc["doc_no"], date.today().isoformat(), "draft", doc["amount"], f"Linked to {req['case_no']}", now(), now(), request_id, req["contact_person"], doc["parent_case_reference"], doc["parent_case_id"], doc["document_reference"], doc["department_id"]))
        advance_case_for_request(conn, request_id, "offer_sent", f"Quotation {doc['doc_no']} generated")
    elif doc_type == "pro_forma":
        advance_case_for_request(conn, request_id, "offer_sent", f"Pro forma {doc['doc_no']} generated")
    elif doc_type in {"service_report", "pm_report", "installation_report", "acceptance_test_report"}:
        advance_case_for_request(conn, request_id, "service_report", f"{doc_type.replace('_', ' ').title()} {doc['doc_no']} generated")
    refresh_case_links(conn, request_id)
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
    quote_row = conn.execute("SELECT id FROM quotations WHERE quotation_no=? ORDER BY id DESC LIMIT 1", (quotation["doc_no"],)).fetchone()
    if not quote_row:
        quote_cur = conn.execute("""
            INSERT INTO quotations (client_id, equipment_id, service_call_id, quotation_no, quote_date, status, amount, notes, created_at, updated_at, request_id, contact_person,
                                    parent_case_reference, parent_case_id, document_reference, department_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (req["client_id"], None, None, quotation["doc_no"], date.today().isoformat(), "approved", quotation["amount"], f"Linked to {req['case_no']}", now(), now(), request_id, req["contact_person"], quotation["parent_case_reference"], quotation["parent_case_id"], quotation["document_reference"], quotation["department_id"]))
        quotation_id = quote_cur.lastrowid
    else:
        quotation_id = quote_row["id"]
    doc = create_sales_document(conn, request_id, "client_order", "approved", "Converted from approved quotation", quotation["id"])
    conn.execute("""
        INSERT INTO client_orders (client_order_no, client_name, status, expected_date, notes, created_at, updated_at, request_id, quotation_id, client_id,
                                   parent_case_reference, parent_case_id, document_reference, department_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(client_order_no) DO UPDATE SET status=excluded.status, notes=excluded.notes, updated_at=excluded.updated_at, request_id=excluded.request_id, quotation_id=excluded.quotation_id, client_id=excluded.client_id,
            parent_case_reference=excluded.parent_case_reference, parent_case_id=excluded.parent_case_id, document_reference=excluded.document_reference, department_id=excluded.department_id
    """, (doc["doc_no"], req["client_hospital"], "APPROVED", "", f"Linked to {req['case_no']} and quotation {quotation['doc_no']}", now(), now(), request_id, quotation_id, req["client_id"], doc["parent_case_reference"], doc["parent_case_id"], doc["document_reference"], doc["department_id"]))
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
                client_order_row["id"], doc["doc_no"], request_id, quotation_id, line["id"], line["requested_item"],
                line["item_type"], int(line["quantity"] or 0), float(line["unit_price"] or 0),
                int(line["quantity"] or 0) * float(line["unit_price"] or 0), line["notes"], now(), now()
            ))
    conn.execute("UPDATE sales_case_documents SET client_order_id=?, quotation_id=?, updated_at=? WHERE id=?", (client_order_row["id"], quotation_id, now(), doc["id"]))
    service_lines = conn.execute("SELECT * FROM customer_request_items WHERE request_id=? AND item_type IN ('labor','service','maintenance_contract')", (request_id,)).fetchall()
    for line in service_lines:
        call_no = make_doc_no("ST", request_id) + f"-{line['id']}"
        conn.execute("""
            INSERT INTO service_calls (client_id, equipment_id, request_id, call_no, status, engineer, issue, resolution, opened_at, closed_at, created_at, updated_at,
                                       parent_case_reference, parent_case_id, department_id, priority, progress_state, invoice_required)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (req["client_id"], None, request_id, call_no, "open", "", f"{line['item_type']}: {line['requested_item']}", "", now(), "", now(), now(),
              doc["parent_case_reference"], doc["parent_case_id"], doc["department_id"], "normal", "call_registered", 1))
    conn.execute("UPDATE customer_requests SET status=?, updated_at=? WHERE id=?", ("client_order_approved", now(), request_id))
    conn.commit()
    reserve_customer_request_stock_in_conn(conn, request_id, client_order_row["id"])
    advance_case_for_request(conn, request_id, "deal_closed", f"Client order {doc['doc_no']} approved")
    advance_case_for_request(conn, request_id, "delivery_coordination", "Stock reservation and delivery coordination started")
    refresh_case_links(conn, request_id)
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
    advance_case_for_request(conn, request_id, "delivery_coordination", "Available stock reserved")
    refresh_case_links(conn, request_id)
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
    case_row = conn.execute("SELECT id, parent_case_reference, department_id FROM cases WHERE request_id=? ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    parent_ref = case_row["parent_case_reference"] if case_row else req["parent_case_reference"]
    parent_case_id = case_row["id"] if case_row else req["parent_case_id"]
    department_id = case_row["department_id"] if case_row else req["department_id"]
    po_no = make_doc_no("PO", request_id)
    conn.execute("""
        INSERT INTO purchase_orders (po_no, supplier, status, expected_date, notes, created_at, updated_at, request_id, client_id, case_id,
                                     parent_case_reference, parent_case_id, document_reference, department_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(po_no) DO UPDATE SET updated_at=excluded.updated_at, request_id=excluded.request_id, client_id=excluded.client_id, case_id=excluded.case_id,
            parent_case_reference=excluded.parent_case_reference, parent_case_id=excluded.parent_case_id, document_reference=excluded.document_reference, department_id=excluded.department_id
    """, (po_no, "", "DRAFT", "", f"Missing items for {req['case_no']}", now(), now(), request_id, req["client_id"], parent_case_id, parent_ref, parent_case_id, document_reference_for(parent_ref, "purchase_order"), department_id))
    po_row = conn.execute("SELECT id FROM purchase_orders WHERE po_no=?", (po_no,)).fetchone()
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
    if po_row:
        conn.execute("UPDATE cases SET purchase_order_id=?, updated_at=? WHERE request_id=?", (po_row["id"], now(), request_id))
    advance_case_for_request(conn, request_id, "parts_request_if_needed", f"PO {po_no} drafted for shortage items")
    refresh_case_links(conn, request_id)
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
    advance_case_for_request(conn, request_id, "shipment_ready", "Linked PO items received or updated")
    refresh_case_links(conn, request_id)
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
    advance_case_for_request(conn, request_id, "delivery_order", f"Delivery note {doc['doc_no']} drafted")
    refresh_case_links(conn, request_id)
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
            (movement_type, item_id, pn, qty, old_qty, new_qty, request_id, request_item_id, delivery_note_id, document_no, client_name, notes, created_at,
             parent_case_reference, parent_case_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("OUT", inv["id"], inv["pn"], qty, old_qty, new_qty, request_id, line["id"], doc["id"], doc["doc_no"], req["client_hospital"], "Delivery note stock removal", now(),
              doc["parent_case_reference"], doc["parent_case_id"]))
        if doc.get("client_order_id"):
            conn.execute("""
                UPDATE client_order_items
                SET delivered_qty=delivered_qty+?, reserved_qty=max(0,reserved_qty-?), updated_at=?
                WHERE client_order_id=? AND request_item_id=?
            """, (qty, qty, now(), doc["client_order_id"], line["id"]))
        audit(conn, inv["id"], "DELIVERY_STOCK_OUT", old_qty, new_qty, f"{req['case_no']} {doc['doc_no']}")
        case_timeline(conn, doc["parent_case_reference"], doc["parent_case_id"], "stock_action", "Delivery stock removed", "completed", "system", f"{qty} x {inv['pn']} via {doc['doc_no']}", "stock_movements", line["id"])
        sync_case_line_stock(conn, line["id"])
    conn.execute("UPDATE sales_case_documents SET status=?, updated_at=? WHERE id=?", ("completed", now(), doc["id"]))
    advance_case_for_request(conn, request_id, "physical_delivery", f"Stock removed for {doc['doc_no']}")
    refresh_case_links(conn, request_id)
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
    advance_case_for_request(conn, request_id, "accountant_notified_for_invoice", f"Invoice {doc['doc_no']} issued")
    advance_case_for_request(conn, request_id, "accountant_notification", f"Invoice {doc['doc_no']} issued")
    refresh_case_links(conn, request_id)
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
        (equipment_id, client_id, calibration_date, next_due_date, calibrated_by, certificate_attachment, calibration_result, result, standards_used, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("calibration_date", ""), data.get("next_due_date", ""), data.get("calibrated_by", ""), data.get("certificate_attachment", ""), data.get("calibration_result", data.get("result", "")), data.get("result", data.get("calibration_result", "")), data.get("standards_used", ""), data.get("notes", ""), now(), now()))
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
        (equipment_id, client_id, event_type, started_at, ended_at, downtime_hours, outage_reason, response_time_hours, repair_time_hours, failure_category, recurring_issue, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("event_type", "outage"), data.get("started_at", ""), data.get("ended_at", ""), downtime, data.get("outage_reason", data.get("failure_category", "")), float(data.get("response_time_hours") or 0), float(data.get("repair_time_hours") or 0), data.get("failure_category", ""), int(bool(data.get("recurring_issue", False))), data.get("notes", ""), now(), now()))
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
        (equipment_id, client_id, notice_type, notice_no, manufacturer, affected_model, affected_serial_numbers, completion_status, corrective_actions, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("notice_type", "recall"), data.get("notice_no", ""), data.get("manufacturer", asset["manufacturer"] or ""), data.get("affected_model", asset["model"] or ""), data.get("affected_serial_numbers", ""), data.get("completion_status", "open"), data.get("corrective_actions", ""), data.get("notes", ""), now(), now()))
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
        (equipment_id, inventory_item_id, part_no, compatibility_type, description, supplier, substitute_part_no, equivalent_part_no, approved, notes,
         equipment_model, compatible_consumables, compatible_accessories, compatible_part_numbers, alternatives_substitutes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, data.get("inventory_item_id"), data.get("part_no", ""), data.get("compatibility_type", "accessory"), data.get("description", ""), data.get("supplier", ""), data.get("substitute_part_no", ""), data.get("equivalent_part_no", ""), int(bool(data.get("approved", True))), data.get("notes", ""), data.get("equipment_model", ""), data.get("compatible_consumables", ""), data.get("compatible_accessories", ""), data.get("compatible_part_numbers", ""), data.get("alternatives_substitutes", data.get("substitute_part_no", "")), now(), now()))
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
        (equipment_type, manufacturer, model, checklist_items, measurements, engineer_signature_required,
         pass_fail_items, measurement_values, comments, engineer_signature, customer_signature, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (payload.get("equipment_type", ""), payload.get("manufacturer", ""), payload.get("model", ""), payload.get("checklist_items", ""), payload.get("measurements", ""), int(bool(payload.get("engineer_signature_required", True))), payload.get("pass_fail_items", ""), payload.get("measurement_values", ""), payload.get("comments", ""), payload.get("engineer_signature", ""), payload.get("customer_signature", ""), now(), now()))
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
        (equipment_id, client_id, bid_id, site_readiness, installation_checklist, environmental_conditions, networking_power_validation, power_network_validation, engineer_signature, customer_signature, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("bid_id"), data.get("site_readiness", ""), data.get("installation_checklist", ""), data.get("environmental_conditions", ""), data.get("networking_power_validation", data.get("power_network_validation", "")), data.get("power_network_validation", data.get("networking_power_validation", "")), data.get("engineer_signature", ""), data.get("customer_signature", ""), data.get("status", "draft"), now(), now()))
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
        (equipment_id, client_id, bid_id, functionality, functional_tests, alarms, calibration_verification, electrical_safety, pass_fail_criteria, pass_fail, customer_approval, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (record.equipment_id, asset["client_id"], data.get("bid_id"), data.get("functionality", data.get("functional_tests", "")), data.get("functional_tests", data.get("functionality", "")), data.get("alarms", ""), data.get("calibration_verification", ""), data.get("electrical_safety", ""), data.get("pass_fail_criteria", ""), data.get("pass_fail", data.get("pass_fail_criteria", "")), data.get("customer_approval", ""), data.get("status", "draft"), now(), now()))
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
             next_pm_date, last_pm_date, status, notes, linked_inventory_pn, barcode,
             end_user, installation_data, warranty_expiration, delivery_doc, supplies, system_name, subsystem_name,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (asset.asset_tag.strip(), asset.serial_number, asset.manufacturer, asset.model, asset.department,
              asset.hospital, asset.location, asset.engineer, asset.contact_email, asset.contract_no,
              asset.contract_start_date, asset.contract_end_date, asset.frequency_days, asset.next_pm_date,
              asset.last_pm_date, asset.status, asset.notes, asset.linked_inventory_pn, asset.barcode,
              asset.end_user, asset.installation_data, asset.warranty_expiration, asset.delivery_doc,
              asset.supplies, asset.system_name, asset.subsystem_name, now(), now()))
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
            barcode=?, end_user=?, installation_data=?, warranty_expiration=?, delivery_doc=?, supplies=?,
            system_name=?, subsystem_name=?, updated_at=?
        WHERE id=?
    """, (asset.asset_tag.strip(), asset.serial_number, asset.manufacturer, asset.model, asset.department,
          asset.hospital, asset.location, asset.engineer, asset.contact_email, asset.contract_no,
          asset.contract_start_date, asset.contract_end_date, asset.frequency_days, asset.next_pm_date,
          asset.last_pm_date, asset.status, asset.notes, asset.linked_inventory_pn, asset.barcode,
          asset.end_user, asset.installation_data, asset.warranty_expiration, asset.delivery_doc, asset.supplies,
          asset.system_name, asset.subsystem_name, now(), asset_id))
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
        (asset_id, task_name, description, checklist, status, assigned_to, due_date, completed_date, notes, created_at, updated_at,
         department_id, equipment_id, checklist_status, report_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (task.asset_id, task.task_name, task.description, task.checklist, task.status, task.assigned_to,
          task.due_date, task.completed_date, task.notes, now(), now(),
          asset["department_id"] if "department_id" in asset.keys() else None, task.asset_id,
          "prepared" if task.checklist else "pending", "pending"))
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
    asset = conn.execute("SELECT * FROM pm_assets WHERE id=?", (task.asset_id,)).fetchone()
    if not asset:
        conn.close()
        raise HTTPException(status_code=404, detail="PM asset not found")
    conn.execute("""
        UPDATE pm_tasks
        SET asset_id=?, task_name=?, description=?, checklist=?, status=?, assigned_to=?, due_date=?,
            completed_date=?, notes=?, department_id=?, equipment_id=?, checklist_status=COALESCE(checklist_status, ?),
            report_status=COALESCE(report_status, ?), updated_at=?
        WHERE id=?
    """, (task.asset_id, task.task_name, task.description, task.checklist, task.status, task.assigned_to,
          task.due_date, task.completed_date, task.notes,
          asset["department_id"] if asset and "department_id" in asset.keys() else None, task.asset_id,
          "prepared" if task.checklist else "pending", "signed" if task.status.lower() == "completed" else "pending",
          now(), task_id))
    if task.status.lower() == "completed":
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
def pm_reports(report: str = "completion", format: str = "excel"):
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
    if format.lower() in {"print", "html", "printable", "pdf"}:
        rows = df.fillna("").to_dict(orient="records")
        return export_rows_response(filename.replace(".xlsx", ""), rows, format, f"PM {report.replace('-', ' ')}")
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
def clean_inventory(q: str = "", location: str = "", category: str = "", limit: int = 1000):
    conn = db()
    where, args = [], []

    if q:
        where.append("(pn LIKE ? OR description LIKE ? OR barcode LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

    if location:
        where.append("location LIKE ?")
        args.append(f"%{location}%")
    normalized_category = normalize_inventory_category(category) if category else ""
    if normalized_category:
        where.append("COALESCE(item_category, 'spare_parts') = ?")
        args.append(normalized_category)

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
def item_options(q: str = "", category: str = "", limit: int = 300):
    conn = db()
    where, args = [], []
    sql = """
        SELECT id, pn, description, barcode, location, physical_qty, system_qty
        FROM inventory
    """
    if q:
        where.append("(pn LIKE ? OR description LIKE ? OR barcode LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    normalized_category = normalize_inventory_category(category) if category else ""
    if normalized_category:
        where.append("COALESCE(item_category, 'spare_parts') = ?")
        args.append(normalized_category)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY pn LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows


@app.get("/api/items")
def list_items(q: str = "", status: str = "", location: str = "", category: str = "", limit: int = 1000):
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
    normalized_category = normalize_inventory_category(category) if category else ""
    if normalized_category:
        where.append("COALESCE(item_category, 'spare_parts') = ?")
        args.append(normalized_category)
    sql = "SELECT * FROM inventory"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY location, pn LIMIT ?"
    args.append(limit)
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    conn.close()
    return rows

@app.get("/api/inventory/{category}")
def list_inventory_category(category: str, q: str = "", status: str = "", location: str = "", limit: int = 1000):
    if category not in {"spare-parts", "spare_parts", "accessories"}:
        raise HTTPException(status_code=404, detail="Inventory category not found")
    normalized = "spare_parts" if category in {"spare-parts", "spare_parts"} else "accessories"
    return list_items(q=q, status=status, location=location, category=normalized, limit=limit)

@app.post("/api/items")
def create_item(item: InventoryItem):
    conn = db()
    diff = item.physical_qty - item.system_qty
    status = item.status or compute_status(item.system_qty, item.physical_qty)
    family = item.device_family or detect_family(item.description)
    item_category = normalize_inventory_category(item.item_category, family, item.description)
    lookup_url = lookup_url_for(item.pn, item.description)
    cur = conn.execute("""
        INSERT INTO inventory
        (pn, description, location, system_qty, physical_qty, difference, device_family, status, notes, source, updated_at, barcode, photo_url, lookup_url, item_category)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (item.pn.strip(), item.description, item.location, item.system_qty, item.physical_qty,
          diff, family, status, item.notes, "WEB_APP", now(), item.barcode, item.photo_url, lookup_url, item_category))
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
    item_category = normalize_inventory_category(item.item_category, family, item.description)
    lookup_url = lookup_url_for(item.pn, item.description)
    conn.execute("""
        UPDATE inventory
        SET pn=?, description=?, location=?, system_qty=?, physical_qty=?, difference=?,
            device_family=?, status=?, notes=?, updated_at=?, barcode=?, photo_url=?, lookup_url=?, item_category=?
        WHERE id=?
    """, (item.pn.strip(), item.description, item.location, item.system_qty, item.physical_qty,
          diff, family, status, item.notes, now(), item.barcode, item.photo_url, lookup_url, item_category, item_id))
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
                 notes, source, updated_at, barcode, photo_url, lookup_url, item_category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                line["pn"], line["description"], line["location"], system_qty, new_qty, diff,
                family, status, line["notes"], "PO_RECEIVED", now(),
                line["barcode"], "", lookup_url, normalize_inventory_category("", family, line["description"])
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

        if line["request_item_id"]:
            conn.execute("""
                UPDATE customer_request_items
                SET procurement_status=?, updated_at=?
                WHERE id=?
            """, ("received", now(), line["request_item_id"]))

        audit(conn, item_id, "PO_RECEIVED_AUTO_STOCK_IN", old_qty, new_qty, f"PO={po_no}; PN={line['pn']}; qty={qty}")
        received_count += 1

    return received_count


@app.post("/api/purchase-orders")
def create_po(po: PurchaseOrder):
    conn = db()
    previous = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (po.po_no,)).fetchone()

    conn.execute("""
        INSERT INTO purchase_orders
        (po_no, supplier, status, po_date, contact_person, payment_terms, shipping_status, shipping_reference,
         reception_status, expected_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(po_no) DO UPDATE SET
            supplier=excluded.supplier,
            status=excluded.status,
            po_date=excluded.po_date,
            contact_person=excluded.contact_person,
            payment_terms=excluded.payment_terms,
            shipping_status=excluded.shipping_status,
            shipping_reference=excluded.shipping_reference,
            reception_status=excluded.reception_status,
            expected_date=excluded.expected_date,
            notes=excluded.notes,
            updated_at=excluded.updated_at
    """, (
        po.po_no, po.supplier, po.status, po.po_date, po.contact_person, po.payment_terms,
        po.shipping_status, po.shipping_reference, po.reception_status, po.expected_date, po.notes, now(), now()
    ))

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
        (po_no, pn, description, qty, received_qty, location, barcode, device_family, notes, received,
         created_at, updated_at, request_id, request_item_id, client_order_no)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        line.po_no, line.pn.strip(), line.description, line.qty, 0,
        line.location, line.barcode, family, line.notes, 0, now(), now(),
        line.request_id, line.request_item_id, line.client_order_no
    ))

    if line.request_item_id:
        conn.execute("""
            UPDATE customer_request_items
            SET linked_purchase_order=?, procurement_status=?, updated_at=?
            WHERE id=?
        """, (line.po_no, "po_draft", now(), line.request_item_id))

    audit(conn, None, "ADD_PO_ITEM", "", line.dict(), f"PO={line.po_no}")
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "PO item added", "id": new_id}


@app.get("/api/procurement/client-order-items/unassigned")
def unassigned_client_order_items():
    conn = db()
    rows = [dict(r) for r in conn.execute("""
        SELECT
            'COI-' || coi.id AS tracking_id,
            coi.id AS client_order_item_id,
            coi.client_order_no,
            coi.client_order_no AS co_no,
            '' AS po_no,
            '' AS supplier,
            coi.request_id,
            coi.request_item_id,
            coi.requested_item,
            COALESCE(NULLIF(cri.pn, ''), coi.requested_item) AS ref,
            coi.requested_item AS description,
            coi.item_type,
            coi.quantity,
            coi.quantity AS qty,
            coi.reserved_qty,
            coi.delivered_qty,
            coi.invoiced_qty,
            coi.notes,
            co.client_name,
            co.client_name AS customer,
            co.status AS client_order_status,
            co.expected_date,
            cr.contact_person,
            cr.parent_case_reference,
            cri.pn,
            cri.shortage_qty,
            cri.procurement_status,
            cri.linked_purchase_order
        FROM client_order_items coi
        LEFT JOIN client_orders co ON co.id=coi.client_order_id
        LEFT JOIN customer_requests cr ON cr.id=coi.request_id
        LEFT JOIN customer_request_items cri ON cri.id=coi.request_item_id
        WHERE COALESCE(cri.linked_purchase_order, '') = ''
          AND COALESCE(coi.quantity, 0) > COALESCE(coi.delivered_qty, 0)
          AND COALESCE(co.status, '') NOT IN ('CANCELLED', 'cancelled')
        ORDER BY co.updated_at DESC, coi.id DESC
    """).fetchall()]
    conn.close()
    return rows


@app.get("/api/procurement/tracked-items")
def procurement_tracked_items(limit: int = 1000):
    conn = db()
    unassigned = [dict(r) for r in conn.execute("""
        SELECT
            'COI-' || coi.id AS tracking_id,
            'client_order' AS source,
            coi.id AS source_id,
            coi.client_order_no AS co_no,
            '' AS po_no,
            '' AS supplier,
            co.client_name AS customer,
            COALESCE(NULLIF(cri.pn, ''), coi.requested_item) AS ref,
            coi.requested_item AS description,
            coi.quantity AS qty,
            0 AS received_qty,
            COALESCE(cri.procurement_status, 'not_ordered') AS status,
            '' AS shipping_status,
            '' AS reception_status,
            coi.request_id,
            coi.request_item_id,
            cr.parent_case_reference,
            coi.updated_at
        FROM client_order_items coi
        LEFT JOIN client_orders co ON co.id=coi.client_order_id
        LEFT JOIN customer_requests cr ON cr.id=coi.request_id
        LEFT JOIN customer_request_items cri ON cri.id=coi.request_item_id
        WHERE COALESCE(cri.linked_purchase_order, '') = ''
          AND COALESCE(coi.quantity, 0) > COALESCE(coi.delivered_qty, 0)
          AND COALESCE(co.status, '') NOT IN ('CANCELLED', 'cancelled')
        ORDER BY coi.updated_at DESC
        LIMIT ?
    """, (limit,)).fetchall()]
    assigned = [dict(r) for r in conn.execute("""
        SELECT
            'POI-' || poi.id AS tracking_id,
            'purchase_order' AS source,
            poi.id AS source_id,
            poi.client_order_no AS co_no,
            poi.po_no,
            po.supplier,
            co.client_name AS customer,
            poi.pn AS ref,
            poi.description,
            poi.qty,
            poi.received_qty,
            CASE WHEN poi.received=1 THEN 'received' ELSE COALESCE(po.status, 'OPEN') END AS status,
            po.shipping_status,
            po.reception_status,
            poi.request_id,
            poi.request_item_id,
            cr.parent_case_reference,
            poi.updated_at
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.po_no=poi.po_no
        LEFT JOIN client_orders co ON co.client_order_no=poi.client_order_no
        LEFT JOIN customer_requests cr ON cr.id=poi.request_id
        ORDER BY poi.updated_at DESC
        LIMIT ?
    """, (limit,)).fetchall()]
    conn.close()
    rows = unassigned + assigned
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return rows[:limit]


@app.post("/api/procurement/purchase-orders/{po_no}/assign-client-order-items")
def assign_client_order_items_to_po(po_no: str, payload: dict):
    item_ids = [int(x) for x in payload.get("client_order_item_ids", []) if str(x).strip()]
    if not item_ids:
        raise HTTPException(status_code=400, detail="Select at least one client order item")

    conn = db()
    po = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (po_no,)).fetchone()
    if not po:
        conn.execute("""
            INSERT INTO purchase_orders (po_no, supplier, status, po_date, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (po_no, "", "OPEN", date.today().isoformat(), "Created from client order assignment", now(), now()))

    placeholders = ",".join("?" for _ in item_ids)
    rows = conn.execute(f"""
        SELECT
            coi.*,
            co.client_name,
            cri.pn,
            cri.shortage_qty,
            cri.linked_purchase_order
        FROM client_order_items coi
        LEFT JOIN client_orders co ON co.id=coi.client_order_id
        LEFT JOIN customer_request_items cri ON cri.id=coi.request_item_id
        WHERE coi.id IN ({placeholders})
    """, item_ids).fetchall()

    assigned = 0
    skipped = []
    for row in rows:
        if row["linked_purchase_order"]:
            skipped.append({"id": row["id"], "reason": "already assigned", "po_no": row["linked_purchase_order"]})
            continue
        qty = int(row["shortage_qty"] or 0) or max(0, int(row["quantity"] or 0) - int(row["delivered_qty"] or 0))
        if qty <= 0:
            skipped.append({"id": row["id"], "reason": "no pending quantity"})
            continue
        pn = row["pn"] or row["requested_item"]
        conn.execute("""
            INSERT INTO purchase_order_items
            (po_no, pn, description, qty, received_qty, location, barcode, device_family, notes, received,
             created_at, updated_at, request_id, request_item_id, client_order_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            po_no, pn, row["requested_item"], qty, 0, "", "", "", f"Linked from client order {row['client_order_no']}",
            0, now(), now(), row["request_id"], row["request_item_id"], row["client_order_no"]
        ))
        if row["request_item_id"]:
            conn.execute("""
                UPDATE customer_request_items
                SET linked_purchase_order=?, procurement_status=?, updated_at=?
                WHERE id=?
            """, (po_no, "po_draft", now(), row["request_item_id"]))
        assigned += 1
        audit(conn, None, "ASSIGN_CO_ITEM_TO_PO", "", f"CO={row['client_order_no']}; PO={po_no}; qty={qty}", f"client_order_item_id={row['id']}")

    conn.commit()
    conn.close()
    export_excel(EXCEL_PATH)
    return {"message": "client order items assigned to purchase order", "assigned": assigned, "skipped": skipped}


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
        """
        SELECT
            poi.*,
            po.supplier,
            po.status AS po_status,
            po.po_date,
            po.contact_person,
            po.payment_terms,
            po.shipping_status,
            po.shipping_reference,
            po.reception_status,
            co.client_name
        FROM purchase_order_items poi
        LEFT JOIN purchase_orders po ON po.po_no=poi.po_no
        LEFT JOIN client_orders co ON co.client_order_no=poi.client_order_no
        ORDER BY poi.updated_at DESC
        LIMIT ?
        """,
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
    hospitals = hospital_dashboard_rows(conn)
    conn.commit()
    conn.close()
    df = pd.DataFrame(rows)
    if df.empty:
        return {
            "hospitals": hospitals,
            "total_hospitals": len(hospitals),
            "transactions": tx_count,
            "purchase_orders": po_count,
            "client_orders": client_order_count,
            "audit_events": audit_count,
            "excel_path": str(EXCEL_PATH),
        }
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
        "hospitals": hospitals,
        "total_hospitals": len(hospitals),
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
