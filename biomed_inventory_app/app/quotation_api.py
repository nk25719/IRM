from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .config.database import get_sqlite_database_path
from .quotation_ai_service import (
    AI_QUOTATION_ENABLED,
    AI_QUOTATION_MAX_INPUT_LENGTH,
    AI_QUOTATION_MODEL,
    AI_QUOTATION_PROVIDER,
    QuotationAIService,
    QuotationContext,
    QuotationExtractionResult,
    RuleBasedQuotationExtractionProvider,
)
from .quotation_export import build_excel, build_pdf, calculate_item_total, calculate_totals
from .quotation_import_service import parse_upload


router = APIRouter(prefix="/quotations", tags=["Quotations"])

STOCK_QUOTATION_ITEM_TYPES = {"spare_part", "part", "equipment", "accessory"}
CLIENT_ORDER_ITEM_STATUSES = {
    "pending_stock_check",
    "available",
    "reserved",
    "purchase_required",
    "ordered",
    "shipped",
    "partially_received",
    "received",
    "ready_for_delivery",
    "delivered",
    "installed",
    "completed",
    "cancelled",
}


def model_data(value: Any) -> dict[str, Any]:
    return value.model_dump() if hasattr(value, "model_dump") else dict(value)


def db_path() -> Path:
    return get_sqlite_database_path()


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


class QuotationItemIn(BaseModel):
    equipment_group_id: int | None = None
    inventory_item_id: int | None = None
    item_code: str | None = None
    manufacturer_part_number: str | None = None
    description: str
    quantity: float = Field(1, gt=0)
    unit_price: float = 0
    discount_percent: float = 0
    item_type: str = "spare_part"
    sort_order: int = 0
    warranty: str | None = None
    delivery_time: str | None = None


class QuotationEquipmentGroupIn(BaseModel):
    equipment_id: int | None = None
    equipment_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    service_report_number: str | None = None
    department_name: str | None = None
    location: str | None = None
    sort_order: int = 0
    items: list[QuotationItemIn] = Field(default_factory=list)


class QuotationEquipmentGroupPatch(BaseModel):
    equipment_id: int | None = None
    equipment_name: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    service_report_number: str | None = None
    department_name: str | None = None
    location: str | None = None
    sort_order: int | None = None


class QuotationIn(BaseModel):
    quotation_number: str | None = None
    client_id: int
    department_id: int | None = None
    contact_id: int | None = None
    case_id: int | None = None
    status: str = "draft"
    quotation_date: str | None = None
    valid_until: str | None = None
    currency: str = "USD"
    discount_amount: float = 0
    vat_rate: float = 0
    payment_terms: str | None = None
    delivery_terms: str | None = None
    warranty_terms: str | None = None
    sales_person: str | None = None
    phone_number: str | None = None
    email: str | None = None
    notes: str | None = None
    items: list[QuotationItemIn] = Field(default_factory=list)
    equipment_groups: list[QuotationEquipmentGroupIn] = Field(default_factory=list)


class QuotationPatch(BaseModel):
    quotation_number: str | None = None
    client_id: int | None = None
    department_id: int | None = None
    contact_id: int | None = None
    case_id: int | None = None
    status: str | None = None
    quotation_date: str | None = None
    valid_until: str | None = None
    currency: str | None = None
    discount_amount: float | None = None
    vat_rate: float | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    warranty_terms: str | None = None
    sales_person: str | None = None
    phone_number: str | None = None
    email: str | None = None
    notes: str | None = None


class QuotationAIExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)
    context: QuotationContext = Field(default_factory=QuotationContext)


class QuotationAIDraftRequest(BaseModel):
    extraction: QuotationExtractionResult
    context: QuotationContext = Field(default_factory=QuotationContext)
    quotation_number: str | None = None
    status: str = "draft"


class PurchaseFromClientOrderItemsRequest(BaseModel):
    customer_order_item_ids: list[int] = Field(default_factory=list)
    supplier_id: int | None = None
    notes: str = ""


class ShipmentFromPurchaseOrderItemsRequest(BaseModel):
    purchase_order_item_quantities: dict[int, int] = Field(default_factory=dict)
    supplier_id: int | None = None
    shipment_no: str = ""
    notes: str = ""


class ReceptionLineRequest(BaseModel):
    shipment_item_id: int
    received_qty: int | None = None
    accepted_qty: int | None = None
    rejected_qty: int = 0
    serial_number: str | None = None
    batch_lot_number: str | None = None
    expiry_date: str | None = None
    warehouse_location: str | None = None


class ReceiveShipmentRequest(BaseModel):
    lines: list[ReceptionLineRequest] = Field(default_factory=list)
    notes: str = ""


class ServiceReportItemRequest(BaseModel):
    customer_order_item_id: int
    stock_item_id: int
    qty: int = 1
    action: str = "delivered"


class ServiceReportRequest(BaseModel):
    items: list[ServiceReportItemRequest] = Field(default_factory=list)
    notes: str = ""


class CancelClientOrderItemRequest(BaseModel):
    reason: str = ""


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_number TEXT,
            quotation_no TEXT,
            client_id INTEGER,
            department_id INTEGER,
            contact_id INTEGER,
            case_id INTEGER,
            status TEXT DEFAULT 'draft',
            quotation_date TEXT,
            quote_date TEXT,
            valid_until TEXT,
            currency TEXT DEFAULT 'USD',
            subtotal REAL DEFAULT 0,
            discount_amount REAL DEFAULT 0,
            vat_rate REAL DEFAULT 0,
            vat_amount REAL DEFAULT 0,
            total_amount REAL DEFAULT 0,
            amount REAL DEFAULT 0,
            payment_terms TEXT,
            delivery_terms TEXT,
            warranty_terms TEXT,
            sales_person TEXT,
            phone_number TEXT,
            email TEXT,
            notes TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_equipment_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER,
            equipment_id INTEGER,
            equipment_name TEXT,
            manufacturer TEXT,
            model TEXT,
            serial_number TEXT,
            service_report_number TEXT,
            department_name TEXT,
            location TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER,
            equipment_group_id INTEGER,
            inventory_item_id INTEGER,
            item_code TEXT,
            manufacturer_part_number TEXT,
            description TEXT,
            ai_normalized_description TEXT,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            discount_percent REAL DEFAULT 0,
            item_type TEXT DEFAULT 'spare_part',
            sort_order INTEGER DEFAULT 0,
            line_total REAL DEFAULT 0,
            warranty TEXT,
            delivery_time TEXT,
            ai_match_confidence REAL,
            ai_validation_status TEXT DEFAULT 'missing_info',
            ai_validation_notes TEXT,
            product_id INTEGER,
            ref TEXT,
            qty INTEGER,
            total_price REAL DEFAULT 0,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS customer_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            co_no TEXT UNIQUE,
            quotation_id INTEGER,
            customer_id INTEGER,
            status TEXT DEFAULT 'open',
            order_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
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
            status TEXT
        )
        """
    )
    conn.execute(
        """
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
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_number TEXT UNIQUE,
            call_no TEXT,
            client_id INTEGER,
            customer_id INTEGER,
            equipment_id INTEGER,
            status TEXT DEFAULT 'open',
            issue TEXT,
            received_at TEXT,
            opened_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_call_id INTEGER,
            quotation_id INTEGER UNIQUE,
            offer_number TEXT,
            status TEXT DEFAULT 'draft',
            approved_at TEXT,
            approved_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_offer_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_offer_id INTEGER,
            quotation_item_id INTEGER UNIQUE,
            item_type TEXT,
            description TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_no TEXT UNIQUE,
            supplier_id INTEGER,
            supplier TEXT,
            status TEXT DEFAULT 'draft',
            po_date TEXT,
            expected_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_order_id INTEGER,
            po_no TEXT,
            client_order_item_id INTEGER,
            customer_order_item_id INTEGER,
            quotation_item_id INTEGER,
            stock_item_id INTEGER,
            product_id INTEGER,
            ref TEXT,
            pn TEXT,
            description TEXT,
            qty INTEGER DEFAULT 0,
            ordered_qty INTEGER DEFAULT 0,
            shipped_qty INTEGER DEFAULT 0,
            received_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ordered',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_no TEXT UNIQUE,
            supplier_id INTEGER,
            status TEXT DEFAULT 'draft',
            shipment_date TEXT,
            expected_arrival TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS shipment_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shipment_id INTEGER,
            purchase_order_item_id INTEGER,
            stock_item_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER DEFAULT 0,
            shipped_qty INTEGER DEFAULT 0,
            received_qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'shipped'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reception_no TEXT UNIQUE,
            shipment_id INTEGER,
            received_date TEXT,
            status TEXT DEFAULT 'draft',
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reception_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reception_id INTEGER,
            shipment_item_id INTEGER,
            stock_item_id INTEGER,
            ref TEXT,
            description TEXT,
            qty INTEGER DEFAULT 0,
            received_qty INTEGER DEFAULT 0,
            accepted_qty INTEGER DEFAULT 0,
            rejected_qty INTEGER DEFAULT 0,
            serial_number TEXT,
            batch_lot_number TEXT,
            expiry_date TEXT,
            warehouse_location TEXT,
            status TEXT DEFAULT 'received',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_reservations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_order_id INTEGER,
            client_order_item_id INTEGER,
            customer_order_item_id INTEGER,
            stock_item_id INTEGER,
            qty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'reserved',
            source_document TEXT,
            source_line_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_item_id INTEGER,
            movement_type TEXT,
            qty INTEGER,
            source_document TEXT,
            source_line_id INTEGER,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_call_id INTEGER,
            customer_order_id INTEGER,
            report_no TEXT UNIQUE,
            status TEXT DEFAULT 'draft',
            report_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS service_report_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_report_id INTEGER,
            client_order_item_id INTEGER,
            customer_order_item_id INTEGER,
            stock_item_id INTEGER,
            description TEXT,
            qty INTEGER DEFAULT 0,
            action TEXT DEFAULT 'delivered',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for table, columns in {
        "quotations": {
            "quotation_number": "TEXT",
            "quotation_no": "TEXT",
            "quote_date": "TEXT",
            "department_id": "INTEGER",
            "contact_id": "INTEGER",
            "case_id": "INTEGER",
            "currency": "TEXT DEFAULT 'USD'",
            "subtotal": "REAL DEFAULT 0",
            "discount_amount": "REAL DEFAULT 0",
            "vat_rate": "REAL DEFAULT 0",
            "vat_amount": "REAL DEFAULT 0",
            "total_amount": "REAL DEFAULT 0",
            "amount": "REAL DEFAULT 0",
            "payment_terms": "TEXT",
            "delivery_terms": "TEXT",
            "warranty_terms": "TEXT",
            "sales_person": "TEXT",
            "phone_number": "TEXT",
            "email": "TEXT",
            "ai_source": "TEXT",
            "ai_missing_information": "TEXT",
            "ai_warnings": "TEXT",
            "template_name": "TEXT",
            "template_version": "TEXT",
            "form_code": "TEXT",
            "edition": "TEXT",
            "footer_form_code": "TEXT",
            "template_snapshot": "TEXT",
            "client_name_snapshot": "TEXT",
            "client_site_id": "INTEGER",
            "sales_person_id": "INTEGER",
            "sales_person_name_snapshot": "TEXT",
            "company_phone_snapshot": "TEXT",
            "company_email_snapshot": "TEXT",
            "discount_total": "REAL DEFAULT 0",
            "grand_total": "REAL DEFAULT 0",
            "validity_days": "INTEGER",
            "disclaimer_text": "TEXT",
            "template_id": "INTEGER",
            "approved_by": "TEXT",
            "approved_at": "TEXT",
            "generated_pdf_path": "TEXT",
            "service_call_id": "INTEGER",
            "service_offer_id": "INTEGER",
        },
        "quotation_items": {
            "equipment_group_id": "INTEGER",
            "equipment_id": "INTEGER",
            "equipment_description_snapshot": "TEXT",
            "manufacturer_snapshot": "TEXT",
            "model_snapshot": "TEXT",
            "serial_number_snapshot": "TEXT",
            "service_report_number": "TEXT",
            "part_number": "TEXT",
            "service_code": "TEXT",
            "unit": "TEXT",
            "taxable": "INTEGER DEFAULT 1",
            "display_order": "INTEGER DEFAULT 0",
            "inventory_item_id": "INTEGER",
            "item_code": "TEXT",
            "manufacturer_part_number": "TEXT",
            "ai_normalized_description": "TEXT",
            "quantity": "REAL DEFAULT 1",
            "discount_percent": "REAL DEFAULT 0",
            "item_type": "TEXT DEFAULT 'spare_part'",
            "sort_order": "INTEGER DEFAULT 0",
            "line_total": "REAL DEFAULT 0",
            "warranty": "TEXT",
            "delivery_time": "TEXT",
            "ai_match_confidence": "REAL",
            "ai_validation_status": "TEXT DEFAULT 'missing_info'",
            "ai_validation_notes": "TEXT",
        },
        "customer_orders": {
            "co_no": "TEXT",
            "quotation_id": "INTEGER",
            "service_offer_id": "INTEGER",
            "service_call_id": "INTEGER",
            "customer_id": "INTEGER",
            "status": "TEXT DEFAULT 'open'",
            "order_date": "TEXT",
            "notes": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
        "customer_order_items": {
            "customer_order_id": "INTEGER",
            "quotation_item_id": "INTEGER",
            "service_offer_item_id": "INTEGER",
            "product_id": "INTEGER",
            "ref": "TEXT",
            "description": "TEXT",
            "ordered_qty": "INTEGER",
            "available_qty": "INTEGER DEFAULT 0",
            "reserved_qty": "INTEGER DEFAULT 0",
            "required_qty": "INTEGER DEFAULT 0",
            "procured_qty": "INTEGER DEFAULT 0",
            "received_qty": "INTEGER DEFAULT 0",
            "delivered_qty": "INTEGER DEFAULT 0",
            "installed_qty": "INTEGER DEFAULT 0",
            "pending_qty": "INTEGER",
            "status": "TEXT",
            "purchasing_status": "TEXT",
            "shipment_status": "TEXT",
            "reception_status": "TEXT",
            "delivery_status": "TEXT",
        },
        "stock_items": {
            "product_id": "INTEGER",
            "ref": "TEXT",
            "description": "TEXT",
            "qty": "INTEGER",
            "customer_order_id": "INTEGER",
            "customer_order_item_id": "INTEGER",
            "co_no": "TEXT",
            "purchase_order_id": "INTEGER",
            "po_no": "TEXT",
            "supplier_id": "INTEGER",
            "shipment_id": "INTEGER",
            "reception_id": "INTEGER",
            "delivery_order_id": "INTEGER",
            "customer_id": "INTEGER",
            "source": "TEXT DEFAULT 'customer_order'",
            "status": "TEXT DEFAULT 'pending_procurement'",
            "location": "TEXT",
            "serial_number": "TEXT",
            "barcode": "TEXT",
            "batch_lot_number": "TEXT",
            "expiry_date": "TEXT",
            "reserved_qty": "INTEGER DEFAULT 0",
            "issued_qty": "INTEGER DEFAULT 0",
            "notes": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
        "service_calls": {
            "service_number": "TEXT",
            "call_no": "TEXT",
            "client_id": "INTEGER",
            "customer_id": "INTEGER",
            "equipment_id": "INTEGER",
            "status": "TEXT DEFAULT 'open'",
            "issue": "TEXT",
            "received_at": "TEXT",
            "opened_at": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
        "service_offers": {
            "service_call_id": "INTEGER",
            "quotation_id": "INTEGER",
            "offer_number": "TEXT",
            "status": "TEXT DEFAULT 'draft'",
            "approved_at": "TEXT",
            "approved_by": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
        "service_offer_items": {
            "service_offer_id": "INTEGER",
            "quotation_item_id": "INTEGER",
            "item_type": "TEXT",
            "description": "TEXT",
            "quantity": "INTEGER DEFAULT 1",
            "unit_price": "REAL DEFAULT 0",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
        "purchase_orders": {"po_no": "TEXT", "supplier_id": "INTEGER", "supplier": "TEXT", "status": "TEXT DEFAULT 'draft'", "po_date": "TEXT", "expected_date": "TEXT", "notes": "TEXT", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP", "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "purchase_order_items": {"purchase_order_id": "INTEGER", "po_no": "TEXT", "client_order_item_id": "INTEGER", "customer_order_item_id": "INTEGER", "quotation_item_id": "INTEGER", "stock_item_id": "INTEGER", "product_id": "INTEGER", "ref": "TEXT", "pn": "TEXT", "description": "TEXT", "qty": "INTEGER DEFAULT 0", "ordered_qty": "INTEGER DEFAULT 0", "shipped_qty": "INTEGER DEFAULT 0", "received_qty": "INTEGER DEFAULT 0", "status": "TEXT DEFAULT 'ordered'", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP", "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "shipments": {"shipment_no": "TEXT", "supplier_id": "INTEGER", "status": "TEXT DEFAULT 'draft'", "shipment_date": "TEXT", "expected_arrival": "TEXT", "notes": "TEXT", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP", "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "shipment_items": {"shipment_id": "INTEGER", "purchase_order_item_id": "INTEGER", "stock_item_id": "INTEGER", "ref": "TEXT", "description": "TEXT", "qty": "INTEGER DEFAULT 0", "shipped_qty": "INTEGER DEFAULT 0", "received_qty": "INTEGER DEFAULT 0", "status": "TEXT DEFAULT 'shipped'"},
        "receptions": {"reception_no": "TEXT", "shipment_id": "INTEGER", "received_date": "TEXT", "status": "TEXT DEFAULT 'draft'", "notes": "TEXT", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "reception_items": {"reception_id": "INTEGER", "shipment_item_id": "INTEGER", "stock_item_id": "INTEGER", "ref": "TEXT", "description": "TEXT", "qty": "INTEGER DEFAULT 0", "received_qty": "INTEGER DEFAULT 0", "accepted_qty": "INTEGER DEFAULT 0", "rejected_qty": "INTEGER DEFAULT 0", "serial_number": "TEXT", "batch_lot_number": "TEXT", "expiry_date": "TEXT", "warehouse_location": "TEXT", "status": "TEXT DEFAULT 'received'", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "stock_reservations": {"customer_order_id": "INTEGER", "client_order_item_id": "INTEGER", "customer_order_item_id": "INTEGER", "stock_item_id": "INTEGER", "qty": "INTEGER DEFAULT 0", "status": "TEXT DEFAULT 'reserved'", "source_document": "TEXT", "source_line_id": "INTEGER", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP", "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "stock_movements": {"stock_item_id": "INTEGER", "movement_type": "TEXT", "qty": "INTEGER", "source_document": "TEXT", "source_line_id": "INTEGER", "notes": "TEXT", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "service_reports": {"service_call_id": "INTEGER", "customer_order_id": "INTEGER", "report_no": "TEXT", "status": "TEXT DEFAULT 'draft'", "report_date": "TEXT", "notes": "TEXT", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
        "service_report_items": {"service_report_id": "INTEGER", "client_order_item_id": "INTEGER", "customer_order_item_id": "INTEGER", "stock_item_id": "INTEGER", "description": "TEXT", "qty": "INTEGER DEFAULT 0", "action": "TEXT DEFAULT 'delivered'", "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP"},
    }.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, column_type in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER,
            filename TEXT,
            content_type TEXT,
            storage_path TEXT,
            extracted_text TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            template_code TEXT,
            edition TEXT,
            logo_asset TEXT,
            company_name TEXT,
            company_legal_information TEXT,
            company_address TEXT,
            company_telephone TEXT,
            company_email TEXT,
            company_website TEXT,
            currency TEXT DEFAULT 'USD',
            default_vat_rate REAL DEFAULT 11,
            default_validity_days INTEGER DEFAULT 7,
            payment_terms TEXT,
            delivery_terms TEXT,
            warranty_terms TEXT,
            default_disclaimer TEXT,
            footer_form_code TEXT,
            notes TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_ai_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER,
            event_type TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            source_entity TEXT,
            prompt_template_version TEXT,
            input_length INTEGER DEFAULT 0,
            extracted_summary TEXT,
            user_approved_status TEXT,
            created_at TEXT
        )
        """
    )
    existing_template_columns = {row["name"] for row in conn.execute("PRAGMA table_info(quotation_templates)")}
    for name, column_type in {
        "template_code": "TEXT",
        "edition": "TEXT",
        "logo_asset": "TEXT",
        "company_name": "TEXT",
        "company_legal_information": "TEXT",
        "company_address": "TEXT",
        "company_telephone": "TEXT",
        "company_email": "TEXT",
        "company_website": "TEXT",
        "default_vat_rate": "REAL DEFAULT 11",
        "default_validity_days": "INTEGER DEFAULT 7",
        "default_disclaimer": "TEXT",
        "footer_form_code": "TEXT",
    }.items():
        if name not in existing_template_columns:
            conn.execute(f"ALTER TABLE quotation_templates ADD COLUMN {name} {column_type}")
    if not conn.execute("SELECT id FROM quotation_templates WHERE name=?", ("CMM Financial Offer",)).fetchone():
        ts = now_iso()
        conn.execute(
            """
            INSERT INTO quotation_templates
            (name, template_code, edition, company_name, company_email, company_website, currency, default_vat_rate,
             default_validity_days, payment_terms, delivery_terms, warranty_terms, default_disclaimer, footer_form_code,
             notes, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CMM Financial Offer",
                "CMM-SA-F-04-03",
                "Edition01",
                "CMM",
                "support@cmm-hc.com",
                "www.cmm-hc.com",
                "USD",
                11,
                7,
                "Cash in Advance",
                "Delivery within four weeks from order confirmation date.",
                "",
                "Should the issue persist following this service, further troubleshooting or additional parts may be required, and a separate quotation will be issued.",
                "CMM-SA-F-04-03-Edition01",
                "Controlled CMM Financial Offer template.",
                1,
                ts,
                ts,
            ),
        )


def default_template(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM quotation_templates WHERE is_default=1 ORDER BY id LIMIT 1").fetchone()
    if not row:
        row = conn.execute("SELECT * FROM quotation_templates ORDER BY id LIMIT 1").fetchone()
    return row_dict(row) or {
        "name": "CMM Financial Offer",
        "template_code": "CMM-SA-F-04-03",
        "edition": "Edition01",
        "currency": "USD",
        "default_vat_rate": 11,
        "default_validity_days": 7,
        "payment_terms": "Cash in Advance",
        "delivery_terms": "Delivery within four weeks from order confirmation date.",
        "default_disclaimer": "Should the issue persist following this service, further troubleshooting or additional parts may be required, and a separate quotation will be issued.",
        "footer_form_code": "CMM-SA-F-04-03-Edition01",
    }


def audit_ai_event(conn: sqlite3.Connection, event_type: str, quotation_id: int | None = None, extracted: dict[str, Any] | None = None, source_entity: str | None = None, input_length: int = 0, approved_status: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO quotation_ai_audit_logs
        (quotation_id, event_type, provider, model, source_entity, prompt_template_version, input_length,
         extracted_summary, user_approved_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quotation_id,
            event_type,
            AI_QUOTATION_PROVIDER,
            AI_QUOTATION_MODEL,
            source_entity,
            "quotation-extraction-v1",
            input_length,
            json.dumps(extracted or {}, default=str)[:4000],
            approved_status,
            now_iso(),
        ),
    )


def client_name(conn: sqlite3.Connection, client_id: int | None) -> str | None:
    client = get_client(conn, client_id)
    return client.get("name") if client else None


def next_quotation_number(conn: sqlite3.Connection) -> str:
    year = date.today().year
    row = conn.execute("SELECT COUNT(*) AS c FROM quotations WHERE COALESCE(quotation_number, quotation_no, '') LIKE ?", (f"QT-{year}-%",)).fetchone()
    return f"QT-{year}-{int(row['c'] or 0) + 1:05d}"


def next_customer_order_number(conn: sqlite3.Connection) -> str:
    year = date.today().year
    row = conn.execute("SELECT COUNT(*) AS c FROM customer_orders WHERE COALESCE(co_no, '') LIKE ?", (f"CO-{year}-%",)).fetchone()
    return f"CO-{year}-{int(row['c'] or 0) + 1:05d}"


def next_document_number(conn: sqlite3.Connection, table: str, column: str, prefix: str) -> str:
    year = date.today().year
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE COALESCE({column}, '') LIKE ?", (f"{prefix}-{year}-%",)).fetchone()
    return f"{prefix}-{year}-{int(row['c'] or 0) + 1:05d}"


def get_items(conn: sqlite3.Connection, quotation_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY COALESCE(equipment_group_id, 0), COALESCE(sort_order, 0), id", (quotation_id,)).fetchall()
    return [row_dict(row) for row in rows]


def get_equipment_groups(conn: sqlite3.Connection, quotation_id: int) -> list[dict[str, Any]]:
    groups = [row_dict(row) for row in conn.execute(
        "SELECT * FROM quotation_equipment_groups WHERE quotation_id=? ORDER BY COALESCE(sort_order, 0), id",
        (quotation_id,),
    ).fetchall()]
    items = get_items(conn, quotation_id)
    for group in groups:
        group["items"] = [item for item in items if item.get("equipment_group_id") == group["id"]]
    return groups


def get_client(conn: sqlite3.Connection, client_id: int | None) -> dict[str, Any] | None:
    if not client_id:
        return None
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    return row_dict(row)


def recalculate(conn: sqlite3.Connection, quotation_id: int) -> None:
    quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
    if not quotation:
        return
    items = get_items(conn, quotation_id)
    totals = calculate_totals(items, quotation.get("discount_amount"), quotation.get("vat_rate"))
    conn.execute(
        "UPDATE quotations SET subtotal=?, discount_total=?, vat_amount=?, total_amount=?, grand_total=?, amount=?, updated_at=? WHERE id=?",
        (totals["subtotal"], totals["discount_amount"], totals["vat_amount"], totals["total_amount"], totals["total_amount"], totals["total_amount"], now_iso(), quotation_id),
    )


def serialize_quotation(conn: sqlite3.Connection, quotation_id: int) -> dict[str, Any]:
    quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    items = get_items(conn, quotation_id)
    equipment_groups = get_equipment_groups(conn, quotation_id)
    client = get_client(conn, quotation.get("client_id"))
    return {**quotation, "client": client, "items": items, "equipment_groups": equipment_groups}


def update_customer_order_status(conn: sqlite3.Connection, customer_order_id: int) -> None:
    rows = [row_dict(row) for row in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=?", (customer_order_id,)).fetchall()]
    if not rows:
        return
    ordered = sum(int(row.get("ordered_qty") or 0) for row in rows)
    received = sum(int(row.get("received_qty") or 0) + int(row.get("reserved_qty") or 0) for row in rows)
    delivered = sum(int(row.get("delivered_qty") or 0) for row in rows)
    pending = sum(int(row.get("pending_qty") or 0) for row in rows)
    if delivered >= ordered:
        status = "delivered"
    elif delivered > 0:
        status = "partially_delivered"
    elif received >= ordered:
        status = "procured"
    elif received > 0 and pending > 0:
        status = "partially_procured"
    else:
        status = "open"
    conn.execute("UPDATE customer_orders SET status=? WHERE id=?", (status, customer_order_id))


def available_stock_rows(conn: sqlite3.Connection, item: dict[str, Any], exclude_ids: set[int]) -> list[dict[str, Any]]:
    ref = item.get("item_code") or item.get("manufacturer_part_number") or item.get("ref") or ""
    clauses = ["status='in_stock'", "COALESCE(customer_order_id, 0)=0", "qty > 0"]
    params: list[Any] = []
    if item.get("product_id"):
        clauses.append("product_id=?")
        params.append(item.get("product_id"))
    elif ref:
        clauses.append("ref=?")
        params.append(ref)
    else:
        clauses.append("description=?")
        params.append(item.get("description") or "")
    rows = [row_dict(row) for row in conn.execute(f"SELECT * FROM stock_items WHERE {' AND '.join(clauses)} ORDER BY id", params).fetchall()]
    return [row for row in rows if row and row["id"] not in exclude_ids]


def record_stock_movement(conn: sqlite3.Connection, stock_item_id: int | None, movement_type: str, qty: int,
                          source_document: str, source_line_id: int | None, notes: str = "") -> None:
    conn.execute(
        """
        INSERT INTO stock_movements
        (stock_item_id, movement_type, qty, source_document, source_line_id, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (stock_item_id, movement_type, qty, source_document, source_line_id, notes, now_iso()),
    )


def create_stock_reservation(conn: sqlite3.Connection, customer_order_id: int, customer_order_item_id: int,
                             stock_item_id: int, qty: int, source_document: str, source_line_id: int) -> None:
    if qty <= 0:
        return
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO stock_reservations
        (customer_order_id, client_order_item_id, customer_order_item_id, stock_item_id, qty,
         status, source_document, source_line_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'reserved', ?, ?, ?, ?)
        """,
        (customer_order_id, customer_order_item_id, customer_order_item_id, stock_item_id, qty, source_document, source_line_id, ts, ts),
    )
    record_stock_movement(conn, stock_item_id, "reserve", qty, source_document, source_line_id, "Reserved for client order line")


def reserve_stock_row(conn: sqlite3.Connection, stock_item: dict[str, Any], reserve_qty: int, customer_order_id: int,
                      customer_order_item_id: int, co_no: str, customer_id: int, ts: str) -> dict[str, Any]:
    stock_qty = int(stock_item.get("qty") or 0)
    if reserve_qty < stock_qty:
        conn.execute("UPDATE stock_items SET qty=?, updated_at=? WHERE id=?", (stock_qty - reserve_qty, ts, stock_item["id"]))
        cur = conn.execute(
            """
            INSERT INTO stock_items
            (product_id, ref, description, qty, customer_order_id, customer_order_item_id, co_no, customer_id,
             source, status, location, serial_number, barcode, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stock_item.get("product_id"),
                stock_item.get("ref") or "",
                stock_item.get("description") or "",
                reserve_qty,
                customer_order_id,
                customer_order_item_id,
                co_no,
                customer_id,
                "existing_stock",
                "reserved",
                stock_item.get("location"),
                stock_item.get("serial_number"),
                stock_item.get("barcode"),
                f"Reserved from stock item {stock_item['id']} for {co_no}",
                ts,
                ts,
            ),
        )
        reserved_id = cur.lastrowid
    else:
        reserved_id = stock_item["id"]
        conn.execute(
            """
            UPDATE stock_items
            SET customer_order_id=?, customer_order_item_id=?, co_no=?, customer_id=?,
                source='existing_stock', status='reserved', reserved_qty=?, notes=?, updated_at=?
            WHERE id=?
            """,
            (customer_order_id, customer_order_item_id, co_no, customer_id, reserve_qty, f"Reserved from available stock for {co_no}", ts, reserved_id),
        )
    create_stock_reservation(conn, customer_order_id, customer_order_item_id, reserved_id, reserve_qty, "customer_order", customer_order_item_id)
    return row_dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (reserved_id,)).fetchone()) or {}


def ensure_service_offer_for_quotation(conn: sqlite3.Connection, quotation_id: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    existing = conn.execute("SELECT * FROM service_offers WHERE quotation_id=?", (quotation_id,)).fetchone()
    if existing:
        return row_dict(existing)
    quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    ts = now_iso()
    service_call_id = payload.get("service_call_id") or quotation.get("service_call_id")
    if not service_call_id:
        service_number = next_document_number(conn, "service_calls", "service_number", "SRV")
        cur = conn.execute(
            """
            INSERT INTO service_calls
            (service_number, call_no, client_id, customer_id, status, issue, received_at, opened_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?)
            """,
            (service_number, service_number, quotation.get("client_id"), quotation.get("client_id"), quotation.get("notes") or "Customer call", ts, ts, ts, ts),
        )
        service_call_id = cur.lastrowid
    offer_number = quotation.get("quotation_number") or quotation.get("quotation_no") or next_document_number(conn, "service_offers", "offer_number", "SO")
    cur = conn.execute(
        """
        INSERT INTO service_offers
        (service_call_id, quotation_id, offer_number, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (service_call_id, quotation_id, offer_number, quotation.get("status") or "draft", ts, ts),
    )
    service_offer_id = cur.lastrowid
    conn.execute("UPDATE quotations SET service_call_id=?, service_offer_id=? WHERE id=?", (service_call_id, service_offer_id, quotation_id))
    for item in get_items(conn, quotation_id):
        conn.execute(
            """
            INSERT INTO service_offer_items
            (service_offer_id, quotation_item_id, item_type, description, quantity, unit_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_offer_id,
                item.get("id"),
                item.get("item_type"),
                item.get("description"),
                max(1, int(float(item.get("quantity") or item.get("qty") or 1))),
                item.get("unit_price") or 0,
                ts,
            ),
        )
    return row_dict(conn.execute("SELECT * FROM service_offers WHERE id=?", (service_offer_id,)).fetchone()) or {}


def ensure_customer_order_for_quotation(conn: sqlite3.Connection, quotation_id: int) -> dict[str, Any]:
    existing = conn.execute("SELECT * FROM customer_orders WHERE quotation_id=?", (quotation_id,)).fetchone()
    if existing:
        return {
            "customer_order": row_dict(existing),
            "items": [row_dict(row) for row in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=? ORDER BY id", (existing["id"],)).fetchall()],
            "stock_items": [row_dict(row) for row in conn.execute("SELECT * FROM stock_items WHERE customer_order_id=? ORDER BY id", (existing["id"],)).fetchall()],
            "reservations": [row_dict(row) for row in conn.execute("SELECT * FROM stock_reservations WHERE customer_order_id=? ORDER BY id", (existing["id"],)).fetchall()],
        }
    quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    service_offer = ensure_service_offer_for_quotation(conn, quotation_id)
    stock_items = []
    co_no = next_customer_order_number(conn)
    customer_id = quotation.get("customer_id") or quotation.get("client_id")
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO customer_orders
        (co_no, quotation_id, service_offer_id, service_call_id, customer_id, status, order_date, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (co_no, quotation_id, service_offer.get("id"), service_offer.get("service_call_id"), customer_id, "open", date.today().isoformat(), quotation.get("notes") or "", ts),
    )
    customer_order_id = cur.lastrowid
    reserved_stock_ids: set[int] = set()
    for item in get_items(conn, quotation_id):
        item_type = str(item.get("item_type") or "").strip().lower()
        if item_type not in STOCK_QUOTATION_ITEM_TYPES:
            continue
        ordered_qty = max(1, int(float(item.get("quantity") or item.get("qty") or 1)))
        ref = item.get("item_code") or item.get("manufacturer_part_number") or item.get("ref") or ""
        co_item_cur = conn.execute(
            """
            INSERT INTO customer_order_items
            (customer_order_id, quotation_item_id, service_offer_item_id, product_id, ref, description, ordered_qty,
             available_qty, reserved_qty, required_qty, procured_qty, received_qty, delivered_qty,
             pending_qty, status, purchasing_status, shipment_status, reception_status, delivery_status)
            VALUES (?, ?, (SELECT id FROM service_offer_items WHERE quotation_item_id=?), ?, ?, ?, ?,
                    0, 0, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_order_id,
                item.get("id"),
                item.get("id"),
                item.get("product_id"),
                ref,
                item.get("description") or "",
                ordered_qty,
                ordered_qty,
                ordered_qty,
                "pending_stock_check",
                "not_required",
                "not_started",
                "not_started",
                "not_ready",
            ),
        )
        customer_order_item_id = co_item_cur.lastrowid
        remaining_qty = ordered_qty
        reserved_qty = 0
        for stock_row in available_stock_rows(conn, item, reserved_stock_ids):
            if remaining_qty <= 0:
                break
            reserve_qty = min(remaining_qty, int(stock_row.get("qty") or 0))
            reserved = reserve_stock_row(conn, stock_row, reserve_qty, customer_order_id, customer_order_item_id, co_no, int(customer_id or 0), ts)
            if reserved:
                stock_items.append(reserved)
                reserved_stock_ids.add(reserved["id"])
            reserved_qty += reserve_qty
            remaining_qty -= reserve_qty
        if remaining_qty > 0:
            demand_cur = conn.execute(
                """
                INSERT INTO stock_items
                (product_id, ref, description, qty, customer_order_id, customer_order_item_id, co_no,
                 customer_id, source, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item.get("product_id"), ref, item.get("description") or "", remaining_qty, customer_order_id, customer_order_item_id, co_no, customer_id, "customer_order", "purchase_required", ts, ts),
            )
            stock_items.append(row_dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (demand_cur.lastrowid,)).fetchone()) or {})
        line_status = "reserved" if remaining_qty == 0 else ("purchase_required" if reserved_qty == 0 else "purchase_required")
        purchasing_status = "not_required" if remaining_qty == 0 else "purchase_required"
        conn.execute(
            """
            UPDATE customer_order_items
            SET available_qty=?, reserved_qty=?, required_qty=?, pending_qty=?, status=?, purchasing_status=?, delivery_status=?
            WHERE id=?
            """,
            (reserved_qty, reserved_qty, remaining_qty, remaining_qty, line_status, purchasing_status, "ready" if remaining_qty == 0 else "not_ready", customer_order_item_id),
        )
    update_customer_order_status(conn, customer_order_id)
    return {
        "customer_order": row_dict(conn.execute("SELECT * FROM customer_orders WHERE id=?", (customer_order_id,)).fetchone()),
        "items": [row_dict(row) for row in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
        "stock_items": [row for row in stock_items if row],
        "reservations": [row_dict(row) for row in conn.execute("SELECT * FROM stock_reservations WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
        "service_offer": service_offer,
    }


def create_purchase_order_from_client_order_items(conn: sqlite3.Connection, customer_order_item_ids: list[int],
                                                 supplier_id: int | None = None, notes: str = "") -> dict[str, Any]:
    if not customer_order_item_ids:
        raise HTTPException(status_code=400, detail="No client-order lines selected")
    po_no = next_document_number(conn, "purchase_orders", "po_no", "PO")
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO purchase_orders
        (po_no, supplier_id, supplier, status, po_date, expected_date, notes, created_at, updated_at)
        VALUES (?, ?, ?, 'ordered', ?, '', ?, ?, ?)
        """,
        (po_no, supplier_id, str(supplier_id or ""), date.today().isoformat(), notes, ts, ts),
    )
    purchase_order_id = cur.lastrowid
    touched_orders: set[int] = set()
    for line_id in customer_order_item_ids:
        line = row_dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (line_id,)).fetchone())
        if not line:
            raise HTTPException(status_code=404, detail=f"Client-order line {line_id} not found")
        if line.get("status") == "cancelled":
            raise HTTPException(status_code=400, detail=f"Client-order line {line_id} is cancelled")
        required_qty = max(0, int(line.get("required_qty") or line.get("pending_qty") or 0))
        if required_qty <= 0:
            continue
        demand = row_dict(
            conn.execute(
                "SELECT * FROM stock_items WHERE customer_order_item_id=? AND status='purchase_required' ORDER BY id LIMIT 1",
                (line_id,),
            ).fetchone()
        )
        cur_item = conn.execute(
            """
            INSERT INTO purchase_order_items
            (purchase_order_id, po_no, client_order_item_id, customer_order_item_id, quotation_item_id,
             stock_item_id, product_id, ref, pn, description, qty, ordered_qty, shipped_qty, received_qty,
             status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'ordered', ?, ?)
            """,
            (
                purchase_order_id,
                po_no,
                line_id,
                line_id,
                line.get("quotation_item_id"),
                demand.get("id") if demand else None,
                line.get("product_id"),
                line.get("ref"),
                line.get("ref"),
                line.get("description"),
                required_qty,
                required_qty,
                ts,
                ts,
            ),
        )
        if demand:
            conn.execute("UPDATE stock_items SET purchase_order_id=?, po_no=?, supplier_id=?, status='ordered', updated_at=? WHERE id=?", (purchase_order_id, po_no, supplier_id, ts, demand["id"]))
        conn.execute(
            """
            UPDATE customer_order_items
            SET status='ordered', purchasing_status='ordered'
            WHERE id=?
            """,
            (line_id,),
        )
        record_stock_movement(conn, demand.get("id") if demand else None, "order", required_qty, "purchase_order", cur_item.lastrowid, "Purchase order created from client-order line")
        touched_orders.add(int(line.get("customer_order_id") or 0))
    for order_id in touched_orders:
        update_customer_order_status(conn, order_id)
    return {
        "purchase_order": row_dict(conn.execute("SELECT * FROM purchase_orders WHERE id=?", (purchase_order_id,)).fetchone()),
        "items": [row_dict(row) for row in conn.execute("SELECT * FROM purchase_order_items WHERE purchase_order_id=? ORDER BY id", (purchase_order_id,)).fetchall()],
    }


def create_shipment_for_purchase_order_items(conn: sqlite3.Connection, purchase_order_item_quantities: dict[int, int],
                                             supplier_id: int | None = None, shipment_no: str = "", notes: str = "") -> dict[str, Any]:
    if not purchase_order_item_quantities:
        raise HTTPException(status_code=400, detail="No purchase-order lines selected")
    shipment_no = shipment_no or next_document_number(conn, "shipments", "shipment_no", "SH")
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO shipments
        (shipment_no, supplier_id, status, shipment_date, expected_arrival, notes, created_at, updated_at)
        VALUES (?, ?, 'shipped', ?, '', ?, ?, ?)
        """,
        (shipment_no, supplier_id, date.today().isoformat(), notes, ts, ts),
    )
    shipment_id = cur.lastrowid
    touched_lines: set[int] = set()
    for poi_id, requested_qty in purchase_order_item_quantities.items():
        item = row_dict(conn.execute("SELECT * FROM purchase_order_items WHERE id=?", (poi_id,)).fetchone())
        if not item:
            raise HTTPException(status_code=404, detail=f"Purchase-order line {poi_id} not found")
        remaining_to_ship = max(0, int(item.get("ordered_qty") or item.get("qty") or 0) - int(item.get("shipped_qty") or 0))
        ship_qty = min(max(0, int(requested_qty or 0)), remaining_to_ship)
        if ship_qty <= 0:
            continue
        conn.execute(
            """
            INSERT INTO shipment_items
            (shipment_id, purchase_order_item_id, stock_item_id, ref, description, qty, shipped_qty, received_qty, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'shipped')
            """,
            (shipment_id, poi_id, item.get("stock_item_id"), item.get("ref") or item.get("pn"), item.get("description"), ship_qty, ship_qty),
        )
        conn.execute("UPDATE purchase_order_items SET shipped_qty=COALESCE(shipped_qty,0)+?, status=?, updated_at=? WHERE id=?", (ship_qty, "shipped" if ship_qty >= remaining_to_ship else "partially_shipped", ts, poi_id))
        if item.get("stock_item_id"):
            conn.execute("UPDATE stock_items SET shipment_id=?, status='shipped', updated_at=? WHERE id=?", (shipment_id, ts, item.get("stock_item_id")))
        conn.execute("UPDATE customer_order_items SET status='shipped', shipment_status='shipped' WHERE id=?", (item.get("customer_order_item_id"),))
        record_stock_movement(conn, item.get("stock_item_id"), "ship", ship_qty, "shipment", shipment_id, "Shipment assigned to purchase-order line")
        touched_lines.add(int(item.get("customer_order_item_id") or 0))
    return {
        "shipment": row_dict(conn.execute("SELECT * FROM shipments WHERE id=?", (shipment_id,)).fetchone()),
        "items": [row_dict(row) for row in conn.execute("SELECT * FROM shipment_items WHERE shipment_id=? ORDER BY id", (shipment_id,)).fetchall()],
    }


def order_co_no(conn: sqlite3.Connection, customer_order_id: int) -> str:
    row = conn.execute("SELECT co_no FROM customer_orders WHERE id=?", (customer_order_id,)).fetchone()
    return row["co_no"] if row else ""


def order_customer_id(conn: sqlite3.Connection, customer_order_id: int) -> int | None:
    row = conn.execute("SELECT customer_id FROM customer_orders WHERE id=?", (customer_order_id,)).fetchone()
    return row["customer_id"] if row else None


def receive_shipment_items(conn: sqlite3.Connection, shipment_id: int, receipt_lines: list[dict[str, Any]], notes: str = "") -> dict[str, Any]:
    if not receipt_lines:
        raise HTTPException(status_code=400, detail="No reception lines supplied")
    reception_no = next_document_number(conn, "receptions", "reception_no", "RC")
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO receptions
        (reception_no, shipment_id, received_date, status, notes, created_at)
        VALUES (?, ?, ?, 'received', ?, ?)
        """,
        (reception_no, shipment_id, date.today().isoformat(), notes, ts),
    )
    reception_id = cur.lastrowid
    touched_order_ids: set[int] = set()
    for payload in receipt_lines:
        shipment_item_id = int(payload.get("shipment_item_id") or 0)
        item = row_dict(conn.execute("SELECT * FROM shipment_items WHERE id=? AND shipment_id=?", (shipment_item_id, shipment_id)).fetchone())
        if not item:
            raise HTTPException(status_code=404, detail=f"Shipment line {shipment_item_id} not found")
        already_received = int(item.get("received_qty") or 0)
        shipped_qty = int(item.get("shipped_qty") or item.get("qty") or 0)
        received_qty = max(0, int(payload.get("received_qty") if payload.get("received_qty") is not None else shipped_qty - already_received))
        accepted_qty = max(0, int(payload.get("accepted_qty") if payload.get("accepted_qty") is not None else received_qty))
        rejected_qty = max(0, int(payload.get("rejected_qty") or max(0, received_qty - accepted_qty)))
        if already_received + received_qty > shipped_qty:
            raise HTTPException(status_code=400, detail=f"Shipment line {shipment_item_id} would be received twice")
        if accepted_qty + rejected_qty > received_qty:
            raise HTTPException(status_code=400, detail=f"Reception quantities exceed received quantity for line {shipment_item_id}")
        po_item = row_dict(conn.execute("SELECT * FROM purchase_order_items WHERE id=?", (item.get("purchase_order_item_id"),)).fetchone())
        stock_item_id = item.get("stock_item_id")
        conn.execute(
            """
            INSERT INTO reception_items
            (reception_id, shipment_item_id, stock_item_id, ref, description, qty, received_qty,
             accepted_qty, rejected_qty, serial_number, batch_lot_number, expiry_date, warehouse_location, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', ?)
            """,
            (
                reception_id,
                shipment_item_id,
                stock_item_id,
                item.get("ref"),
                item.get("description"),
                shipped_qty,
                received_qty,
                accepted_qty,
                rejected_qty,
                payload.get("serial_number"),
                payload.get("batch_lot_number"),
                payload.get("expiry_date"),
                payload.get("warehouse_location"),
                ts,
            ),
        )
        conn.execute("UPDATE shipment_items SET received_qty=COALESCE(received_qty,0)+?, status=? WHERE id=?", (received_qty, "received" if already_received + received_qty >= shipped_qty else "partially_received", shipment_item_id))
        if po_item:
            conn.execute("UPDATE purchase_order_items SET received_qty=COALESCE(received_qty,0)+?, status=? WHERE id=?", (accepted_qty, "received" if int(po_item.get("received_qty") or 0) + accepted_qty >= int(po_item.get("ordered_qty") or po_item.get("qty") or 0) else "partially_received", po_item["id"]))
            co_item_id = po_item.get("customer_order_item_id") or po_item.get("client_order_item_id")
            co_item = row_dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (co_item_id,)).fetchone())
            if co_item and accepted_qty:
                conn.execute(
                    """
                    UPDATE customer_order_items
                    SET received_qty=COALESCE(received_qty,0)+?, reserved_qty=COALESCE(reserved_qty,0)+?,
                        required_qty=MAX(0, COALESCE(required_qty,0)-?), pending_qty=MAX(0, COALESCE(pending_qty,0)-?),
                        status=CASE WHEN MAX(0, COALESCE(required_qty,0)-?)=0 THEN 'ready_for_delivery' ELSE 'partially_received' END,
                        reception_status=CASE WHEN MAX(0, COALESCE(required_qty,0)-?)=0 THEN 'received' ELSE 'partially_received' END,
                        delivery_status=CASE WHEN MAX(0, COALESCE(required_qty,0)-?)=0 THEN 'ready' ELSE delivery_status END
                    WHERE id=?
                    """,
                    (accepted_qty, accepted_qty, accepted_qty, accepted_qty, accepted_qty, accepted_qty, accepted_qty, co_item_id),
                )
                touched_order_ids.add(int(co_item.get("customer_order_id") or 0))
                received_stock_cur = conn.execute(
                    """
                    INSERT INTO stock_items
                    (product_id, ref, description, qty, customer_order_id, customer_order_item_id, co_no,
                     purchase_order_id, po_no, supplier_id, shipment_id, reception_id, customer_id,
                     source, status, location, serial_number, batch_lot_number, expiry_date, reserved_qty,
                     notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reception', 'reserved', ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        po_item.get("product_id"),
                        item.get("ref"),
                        item.get("description"),
                        accepted_qty,
                        co_item.get("customer_order_id"),
                        co_item_id,
                        order_co_no(conn, int(co_item.get("customer_order_id") or 0)),
                        po_item.get("purchase_order_id"),
                        po_item.get("po_no"),
                        None,
                        shipment_id,
                        reception_id,
                        order_customer_id(conn, int(co_item.get("customer_order_id") or 0)),
                        payload.get("warehouse_location"),
                        payload.get("serial_number"),
                        payload.get("batch_lot_number"),
                        payload.get("expiry_date"),
                        accepted_qty,
                        "Accepted reception stock reserved for original client order",
                        ts,
                        ts,
                    ),
                )
                received_stock_id = received_stock_cur.lastrowid
                if stock_item_id:
                    conn.execute("UPDATE stock_items SET status=?, reception_id=?, updated_at=? WHERE id=?", ("received" if accepted_qty else "shipped", reception_id, ts, stock_item_id))
                create_stock_reservation(conn, int(co_item.get("customer_order_id") or 0), int(co_item_id), int(received_stock_id), accepted_qty, "reception", reception_id)
                record_stock_movement(conn, int(received_stock_id), "receive", accepted_qty, "reception", reception_id, "Accepted reception added to stock and reserved")
    conn.execute("UPDATE shipments SET status=? WHERE id=?", ("arrived", shipment_id))
    for order_id in touched_order_ids:
        update_customer_order_status(conn, order_id)
    return {
        "reception": row_dict(conn.execute("SELECT * FROM receptions WHERE id=?", (reception_id,)).fetchone()),
        "items": [row_dict(row) for row in conn.execute("SELECT * FROM reception_items WHERE reception_id=? ORDER BY id", (reception_id,)).fetchall()],
    }


def create_service_report_for_client_order(conn: sqlite3.Connection, customer_order_id: int, item_actions: list[dict[str, Any]], notes: str = "") -> dict[str, Any]:
    order = row_dict(conn.execute("SELECT * FROM customer_orders WHERE id=?", (customer_order_id,)).fetchone())
    if not order:
        raise HTTPException(status_code=404, detail="Client order not found")
    report_no = next_document_number(conn, "service_reports", "report_no", "SRPT")
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO service_reports
        (service_call_id, customer_order_id, report_no, status, report_date, notes, created_at)
        VALUES (?, ?, ?, 'completed', ?, ?, ?)
        """,
        (order.get("service_call_id"), customer_order_id, report_no, date.today().isoformat(), notes, ts),
    )
    report_id = cur.lastrowid
    touched_lines: set[int] = set()
    for action in item_actions:
        co_item_id = int(action.get("customer_order_item_id") or action.get("client_order_item_id") or 0)
        stock_item_id = int(action.get("stock_item_id") or 0)
        qty = max(1, int(action.get("qty") or 1))
        kind = action.get("action") or "delivered"
        if kind not in {"delivered", "installed"}:
            raise HTTPException(status_code=400, detail="Service report action must be delivered or installed")
        stock = row_dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (stock_item_id,)).fetchone())
        if not stock or int(stock.get("qty") or 0) < qty:
            raise HTTPException(status_code=400, detail="Reserved stock is not available for issue")
        line = row_dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (co_item_id,)).fetchone())
        conn.execute(
            """
            INSERT INTO service_report_items
            (service_report_id, client_order_item_id, customer_order_item_id, stock_item_id, description, qty, action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (report_id, co_item_id, co_item_id, stock_item_id, stock.get("description") or (line or {}).get("description"), qty, kind, ts),
        )
        new_qty = int(stock.get("qty") or 0) - qty
        conn.execute("UPDATE stock_items SET qty=?, issued_qty=COALESCE(issued_qty,0)+?, status=?, updated_at=? WHERE id=?", (new_qty, qty, "issued" if new_qty == 0 else "reserved", ts, stock_item_id))
        conn.execute("UPDATE stock_reservations SET status=? WHERE stock_item_id=? AND customer_order_item_id=?", ("issued" if new_qty == 0 else "partially_issued", stock_item_id, co_item_id))
        status = "installed" if kind == "installed" else "delivered"
        qty_col = "installed_qty" if kind == "installed" else "delivered_qty"
        conn.execute(f"UPDATE customer_order_items SET {qty_col}=COALESCE({qty_col},0)+?, status=?, delivery_status=? WHERE id=?", (qty, status, status, co_item_id))
        record_stock_movement(conn, stock_item_id, "issue", qty, "service_report", report_id, f"Stock {kind} through service report")
        touched_lines.add(co_item_id)
    update_customer_order_status(conn, customer_order_id)
    return {
        "service_report": row_dict(conn.execute("SELECT * FROM service_reports WHERE id=?", (report_id,)).fetchone()),
        "items": [row_dict(row) for row in conn.execute("SELECT * FROM service_report_items WHERE service_report_id=? ORDER BY id", (report_id,)).fetchall()],
    }


def cancel_client_order_item(conn: sqlite3.Connection, customer_order_item_id: int, reason: str = "") -> dict[str, Any]:
    line = row_dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (customer_order_item_id,)).fetchone())
    if not line:
        raise HTTPException(status_code=404, detail="Client-order line not found")
    ts = now_iso()
    reservations = [row_dict(row) for row in conn.execute("SELECT * FROM stock_reservations WHERE customer_order_item_id=? AND status='reserved'", (customer_order_item_id,)).fetchall()]
    for reservation in reservations:
        stock = row_dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (reservation.get("stock_item_id"),)).fetchone())
        if stock and stock.get("source") == "existing_stock":
            conn.execute("UPDATE stock_items SET customer_order_id=NULL, customer_order_item_id=NULL, co_no=NULL, customer_id=NULL, status='in_stock', reserved_qty=0, notes=?, updated_at=? WHERE id=?", (reason, ts, stock["id"]))
        conn.execute("UPDATE stock_reservations SET status='cancelled', updated_at=? WHERE id=?", (ts, reservation["id"]))
    conn.execute("UPDATE customer_order_items SET status='cancelled', purchasing_status='cancelled', shipment_status='cancelled', reception_status='cancelled', delivery_status='cancelled' WHERE id=?", (customer_order_item_id,))
    update_customer_order_status(conn, int(line.get("customer_order_id") or 0))
    return row_dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (customer_order_item_id,)).fetchone()) or {}


def client_context(conn: sqlite3.Connection, context: QuotationContext) -> QuotationContext:
    data = context.model_dump()
    if context.client_id and not context.client_name:
        client = get_client(conn, context.client_id)
        if client:
            data["client_name"] = client.get("name")
    if context.contact_id and not context.contact_name:
        contact = conn.execute("SELECT * FROM contacts WHERE id=?", (context.contact_id,)).fetchone()
        if contact:
            data["contact_name"] = contact["display_name"] or contact["name"] or contact["email"]
    return QuotationContext(**data)


def extraction_to_quotation_payload(conn: sqlite3.Connection, request: QuotationAIDraftRequest) -> QuotationIn:
    extraction = request.extraction
    context = client_context(conn, request.context)
    client_id = context.client_id or extraction.client.id
    if not client_id:
        raise HTTPException(status_code=400, detail="Client must be selected before creating a draft quotation")
    currency = extraction.commercial_terms.currency or context.preferred_currency or "USD"
    notes = []
    ts = extraction.technical_summary
    for label, value in [
        ("Reported issue", ts.reported_issue),
        ("Inspection findings", ts.inspection_findings),
        ("Diagnosis", ts.diagnosis),
        ("Recommended action", ts.recommended_action),
    ]:
        if value:
            notes.append(f"{label}: {value}")
    notes.extend(f"Missing Information: {item}" for item in extraction.missing_information)
    notes.extend(f"Warning: {item}" for item in extraction.warnings)
    items = [
        QuotationItemIn(
            item_code=item.part_number,
            manufacturer_part_number=item.part_number,
            description=item.description or item.part_number or "Review extracted spare part",
            quantity=item.quantity or 1,
            unit_price=item.unit_price or 0,
            discount_percent=item.discount_percent,
            item_type="service_fee" if item.item_type in {"service", "service_fee", "pm", "contract"} else "spare_part",
            warranty=item.warranty or extraction.commercial_terms.warranty,
            ai_validation_status="missing_info" if item.unit_price is None or not item.description else "warning",
            sort_order=index,
        )
        for index, item in enumerate(extraction.items, start=1)
    ]
    items.extend(
        QuotationItemIn(
            item_code=None,
            description=labour.description or "Labour - review extracted scope",
            quantity=labour.hours or 1,
            unit_price=labour.hourly_rate or 0,
            item_type="labor",
            warranty=extraction.commercial_terms.warranty,
            ai_validation_status="missing_info" if labour.hours is None or labour.hourly_rate is None else "warning",
            sort_order=len(items) + 1,
        )
        for labour in extraction.labour
    )
    group = QuotationEquipmentGroupIn(
        equipment_id=context.equipment_id or extraction.equipment.equipment_id,
        equipment_name=context.equipment_name or extraction.equipment.model,
        manufacturer=extraction.equipment.manufacturer,
        model=extraction.equipment.model,
        serial_number=extraction.equipment.serial_number,
        service_report_number=context.service_report_number or extraction.references.service_report_number,
        items=items,
    )
    return QuotationIn(
        quotation_number=request.quotation_number,
        client_id=client_id,
        contact_id=context.contact_id or extraction.client.contact_id,
        case_id=context.service_case_id or extraction.references.service_case_id,
        status="ai_draft",
        currency=currency,
        vat_rate=0 if extraction.commercial_terms.tax_included is False else 11,
        valid_until=(date.today() + timedelta(days=extraction.commercial_terms.quotation_validity_days or 7)).isoformat(),
        payment_terms=extraction.commercial_terms.payment_terms,
        delivery_terms=extraction.commercial_terms.delivery_time,
        warranty_terms=extraction.commercial_terms.warranty,
        notes="\n".join(notes),
        equipment_groups=[group] if items else [],
        items=[] if items else [QuotationItemIn(description="Review AI extraction and add quotation lines", quantity=1, unit_price=0, item_type="custom")],
    )


def insert_equipment_group(conn: sqlite3.Connection, quotation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    ts = now_iso()
    cur = conn.execute(
        """
        INSERT INTO quotation_equipment_groups
        (quotation_id, equipment_id, equipment_name, manufacturer, model, serial_number, service_report_number,
         department_name, location, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quotation_id,
            payload.get("equipment_id"),
            payload.get("equipment_name"),
            payload.get("manufacturer"),
            payload.get("model"),
            payload.get("serial_number"),
            payload.get("service_report_number"),
            payload.get("department_name"),
            payload.get("location"),
            payload.get("sort_order") or 0,
            ts,
            ts,
        ),
    )
    return row_dict(conn.execute("SELECT * FROM quotation_equipment_groups WHERE id=?", (cur.lastrowid,)).fetchone())


def insert_item(conn: sqlite3.Connection, quotation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    line_total = calculate_item_total(payload)
    group = None
    if payload.get("equipment_group_id"):
        group = conn.execute("SELECT * FROM quotation_equipment_groups WHERE id=?", (payload.get("equipment_group_id"),)).fetchone()
        group = row_dict(group)
    cur = conn.execute(
        """
        INSERT INTO quotation_items
        (quotation_id, equipment_group_id, equipment_id, equipment_description_snapshot, manufacturer_snapshot, model_snapshot,
         serial_number_snapshot, service_report_number, inventory_item_id, item_code, manufacturer_part_number, part_number,
         service_code, description, quantity, qty, unit, unit_price, discount_percent, taxable, item_type, sort_order,
         display_order, line_total, total_price, warranty, delivery_time, ai_validation_status, ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quotation_id,
            payload.get("equipment_group_id"),
            payload.get("equipment_id") or (group or {}).get("equipment_id"),
            payload.get("equipment_description_snapshot") or (group or {}).get("equipment_name"),
            payload.get("manufacturer_snapshot") or (group or {}).get("manufacturer"),
            payload.get("model_snapshot") or (group or {}).get("model"),
            payload.get("serial_number_snapshot") or (group or {}).get("serial_number"),
            payload.get("service_report_number") or (group or {}).get("service_report_number"),
            payload.get("inventory_item_id"),
            payload.get("item_code"),
            payload.get("manufacturer_part_number"),
            payload.get("part_number") or payload.get("manufacturer_part_number") or payload.get("item_code"),
            payload.get("service_code"),
            payload.get("description"),
            payload.get("quantity") or 1,
            int(payload.get("quantity") or 1),
            payload.get("unit") or "piece",
            payload.get("unit_price") or 0,
            payload.get("discount_percent") or 0,
            0 if payload.get("taxable") is False else 1,
            payload.get("item_type") or "spare_part",
            payload.get("sort_order") or 0,
            payload.get("display_order") or payload.get("sort_order") or 0,
            line_total,
            line_total,
            payload.get("warranty"),
            payload.get("delivery_time"),
            payload.get("ai_validation_status") or "missing_info",
            payload.get("item_code"),
        ),
    )
    recalculate(conn, quotation_id)
    return row_dict(conn.execute("SELECT * FROM quotation_items WHERE id=?", (cur.lastrowid,)).fetchone())


@router.post("", status_code=201)
@router.post("/", status_code=201)
def create_quotation(payload: QuotationIn):
    with connect() as conn:
        ensure_tables(conn)
        template = default_template(conn)
        quotation_date = payload.quotation_date or date.today().isoformat()
        valid_until = payload.valid_until or (date.today() + timedelta(days=30)).isoformat()
        number = payload.quotation_number or next_quotation_number(conn)
        ts = now_iso()
        cur = conn.execute(
            """
            INSERT INTO quotations
            (quotation_number, quotation_no, client_id, department_id, contact_id, case_id, status, quotation_date, quote_date,
             valid_until, currency, discount_amount, vat_rate, payment_terms, delivery_terms, warranty_terms,
             sales_person, phone_number, email, notes, client_name_snapshot, sales_person_name_snapshot,
             company_phone_snapshot, company_email_snapshot, discount_total, grand_total, validity_days,
             disclaimer_text, template_id, template_version, form_code, edition, template_name, footer_form_code,
             template_snapshot, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                number,
                number,
                payload.client_id,
                payload.department_id,
                payload.contact_id,
                payload.case_id,
                payload.status,
                quotation_date,
                quotation_date,
                valid_until,
                payload.currency,
                payload.discount_amount,
                payload.vat_rate,
                payload.payment_terms,
                payload.delivery_terms,
                payload.warranty_terms,
                payload.sales_person,
                payload.phone_number,
                payload.email,
                payload.notes,
                client_name(conn, payload.client_id),
                payload.sales_person,
                payload.phone_number,
                payload.email or template.get("company_email"),
                payload.discount_amount,
                0,
                max(0, (date.fromisoformat(valid_until) - date.fromisoformat(quotation_date)).days) if valid_until and quotation_date else template.get("default_validity_days"),
                template.get("default_disclaimer"),
                template.get("id"),
                template.get("edition"),
                template.get("template_code"),
                template.get("edition"),
                template.get("name"),
                template.get("footer_form_code"),
                json.dumps(template, default=str),
                ts,
                ts,
            ),
        )
        quotation_id = cur.lastrowid
        for group in payload.equipment_groups:
            group_data = group.model_dump()
            items = group_data.pop("items", [])
            inserted_group = insert_equipment_group(conn, quotation_id, group_data)
            for item in items:
                item_data = model_data(item)
                item_data["equipment_group_id"] = inserted_group["id"]
                insert_item(conn, quotation_id, item_data)
        for item in payload.items:
            insert_item(conn, quotation_id, item.model_dump())
        recalculate(conn, quotation_id)
        conn.commit()
        return serialize_quotation(conn, quotation_id)


@router.get("")
@router.get("/")
def list_quotations(limit: int = 100, offset: int = 0, status: str = ""):
    with connect() as conn:
        ensure_tables(conn)
        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE status=?"
            params.append(status)
        rows = conn.execute(
            f"SELECT * FROM quotations {where} ORDER BY COALESCE(updated_at, created_at) DESC, id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [row_dict(row) for row in rows]


@router.post("/demo/cmm-service-offer", status_code=201)
def create_cmm_service_demo():
    with connect() as conn:
        ensure_tables(conn)
        client = conn.execute("SELECT * FROM clients WHERE lower(name)=lower(?)", ("Clinique du Levant",)).fetchone()
        if not client:
            ts = now_iso()
            try:
                cur = conn.execute("INSERT INTO clients (name, phone, contact_email, created_at, updated_at) VALUES (?, ?, ?, ?, ?)", ("Clinique du Levant", "03137314", "Support@cmm-hc.com", ts, ts))
            except sqlite3.OperationalError:
                cur = conn.execute("INSERT INTO clients (name) VALUES (?)", ("Clinique du Levant",))
            client_id = cur.lastrowid
        else:
            client_id = client["id"]
        payload = QuotationIn(
            client_id=client_id,
            quotation_number="CDL-SRV1 - 4762/3/ A-0006910",
            quotation_date="2026-06-12",
            valid_until="2026-06-19",
            currency="USD",
            vat_rate=11,
            payment_terms="Cash in Advance",
            sales_person="Nagham Kheir",
            phone_number="03137314",
            email="Support@cmm-hc.com",
            equipment_groups=[
                QuotationEquipmentGroupIn(
                    equipment_name="SLE 2000",
                    serial_number="D0424",
                    service_report_number="6-14762",
                    sort_order=1,
                    items=[
                        QuotationItemIn(item_code="SL-N2191", description="OXYGEN CELL SENSOR SLE2000", quantity=1, unit_price=220, item_type="spare_part", sort_order=1),
                        QuotationItemIn(item_code="CMM-LabA", description="Inspection/Repair Labor Fee", quantity=1, unit_price=70, item_type="labor", sort_order=2),
                    ],
                ),
                QuotationEquipmentGroupIn(
                    equipment_name="SLE 2000",
                    serial_number="D0410",
                    service_report_number="6-14763",
                    sort_order=2,
                    items=[
                        QuotationItemIn(item_code="SL-N2191", description="OXYGEN CELL SENSOR SLE2000", quantity=1, unit_price=220, item_type="spare_part", sort_order=1),
                        QuotationItemIn(item_code="CMM-LabA", description="Inspection/Repair Labor Fee", quantity=1, unit_price=70, item_type="labor", sort_order=2),
                    ],
                ),
            ],
        )
        quotation_date = payload.quotation_date or date.today().isoformat()
        ts = now_iso()
        cur = conn.execute(
            """
            INSERT INTO quotations
            (quotation_number, quotation_no, client_id, status, quotation_date, quote_date, valid_until, currency,
             discount_amount, vat_rate, payment_terms, sales_person, phone_number, email, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (payload.quotation_number, payload.quotation_number, payload.client_id, "draft", quotation_date, quotation_date,
             payload.valid_until, payload.currency, payload.discount_amount, payload.vat_rate, payload.payment_terms,
             payload.sales_person, payload.phone_number, payload.email, ts, ts),
        )
        quotation_id = cur.lastrowid
        for group in payload.equipment_groups:
            group_data = group.model_dump()
            items = group_data.pop("items", [])
            inserted_group = insert_equipment_group(conn, quotation_id, group_data)
            for item in items:
                item_data = model_data(item)
                item_data["equipment_group_id"] = inserted_group["id"]
                insert_item(conn, quotation_id, item_data)
        recalculate(conn, quotation_id)
        conn.commit()
        return serialize_quotation(conn, quotation_id)


@router.get("/{quotation_id:int}")
def get_quotation(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        return serialize_quotation(conn, quotation_id)


@router.patch("/{quotation_id:int}")
def patch_quotation(quotation_id: int, payload: QuotationPatch):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_quotation(quotation_id)
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        if "quotation_number" in data:
            data["quotation_no"] = data["quotation_number"]
        data["updated_at"] = now_iso()
        sets = ", ".join(f"{key}=?" for key in data)
        conn.execute(f"UPDATE quotations SET {sets} WHERE id=?", (*data.values(), quotation_id))
        recalculate(conn, quotation_id)
        conn.commit()
        return serialize_quotation(conn, quotation_id)


@router.delete("/{quotation_id:int}", status_code=204)
def delete_quotation(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        conn.execute("DELETE FROM quotation_items WHERE quotation_id=?", (quotation_id,))
        conn.execute("DELETE FROM quotation_equipment_groups WHERE quotation_id=?", (quotation_id,))
        conn.execute("DELETE FROM quotation_attachments WHERE quotation_id=?", (quotation_id,))
        conn.execute("DELETE FROM quotations WHERE id=?", (quotation_id,))
        conn.commit()
    return None


@router.post("/{quotation_id:int}/items", status_code=201)
def create_item(quotation_id: int, payload: QuotationItemIn):
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        item = insert_item(conn, quotation_id, payload.model_dump())
        conn.commit()
        return item


@router.post("/{quotation_id:int}/equipment-groups", status_code=201)
def create_equipment_group(quotation_id: int, payload: QuotationEquipmentGroupIn):
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        group_data = payload.model_dump()
        items = group_data.pop("items", [])
        group = insert_equipment_group(conn, quotation_id, group_data)
        for item in items:
            item_data = model_data(item)
            item_data["equipment_group_id"] = group["id"]
            insert_item(conn, quotation_id, item_data)
        recalculate(conn, quotation_id)
        conn.commit()
        return {**group, "items": [item for item in get_items(conn, quotation_id) if item.get("equipment_group_id") == group["id"]]}


@router.patch("/{quotation_id:int}/equipment-groups/{group_id}")
def patch_equipment_group(quotation_id: int, group_id: int, payload: QuotationEquipmentGroupPatch):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return get_quotation(quotation_id)
    data["updated_at"] = now_iso()
    with connect() as conn:
        ensure_tables(conn)
        row = conn.execute("SELECT * FROM quotation_equipment_groups WHERE id=? AND quotation_id=?", (group_id, quotation_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Equipment group not found")
        sets = ", ".join(f"{key}=?" for key in data)
        conn.execute(f"UPDATE quotation_equipment_groups SET {sets} WHERE id=? AND quotation_id=?", (*data.values(), group_id, quotation_id))
        conn.commit()
        return row_dict(conn.execute("SELECT * FROM quotation_equipment_groups WHERE id=?", (group_id,)).fetchone())


@router.delete("/{quotation_id:int}/equipment-groups/{group_id}", status_code=204)
def delete_equipment_group(quotation_id: int, group_id: int):
    with connect() as conn:
        ensure_tables(conn)
        conn.execute("UPDATE quotation_items SET equipment_group_id=NULL WHERE quotation_id=? AND equipment_group_id=?", (quotation_id, group_id))
        conn.execute("DELETE FROM quotation_equipment_groups WHERE id=? AND quotation_id=?", (group_id, quotation_id))
        recalculate(conn, quotation_id)
        conn.commit()
    return None


@router.post("/{quotation_id:int}/equipment-groups/{group_id}/items", status_code=201)
def create_group_item(quotation_id: int, group_id: int, payload: QuotationItemIn):
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotation_equipment_groups WHERE id=? AND quotation_id=?", (group_id, quotation_id)).fetchone():
            raise HTTPException(status_code=404, detail="Equipment group not found")
        data = payload.model_dump()
        data["equipment_group_id"] = group_id
        item = insert_item(conn, quotation_id, data)
        conn.commit()
        return item


@router.patch("/{quotation_id:int}/items/{item_id}")
def patch_item(quotation_id: int, item_id: int, payload: dict[str, Any]):
    allowed = {"equipment_group_id", "inventory_item_id", "item_code", "manufacturer_part_number", "description", "quantity", "unit_price", "discount_percent", "item_type", "sort_order", "warranty", "delivery_time", "ai_normalized_description", "ai_match_confidence", "ai_validation_status", "ai_validation_notes"}
    data = {key: value for key, value in payload.items() if key in allowed}
    if "quantity" in data:
        data["qty"] = int(data["quantity"] or 0)
    with connect() as conn:
        ensure_tables(conn)
        row = conn.execute("SELECT * FROM quotation_items WHERE id=? AND quotation_id=?", (item_id, quotation_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Quotation item not found")
        merged = {**row_dict(row), **data}
        data["line_total"] = calculate_item_total(merged)
        data["total_price"] = data["line_total"]
        if "item_code" in data:
            data["ref"] = data["item_code"]
        sets = ", ".join(f"{key}=?" for key in data)
        conn.execute(f"UPDATE quotation_items SET {sets} WHERE id=? AND quotation_id=?", (*data.values(), item_id, quotation_id))
        recalculate(conn, quotation_id)
        conn.commit()
        return row_dict(conn.execute("SELECT * FROM quotation_items WHERE id=?", (item_id,)).fetchone())


@router.delete("/{quotation_id:int}/items/{item_id}", status_code=204)
def delete_item(quotation_id: int, item_id: int):
    with connect() as conn:
        ensure_tables(conn)
        conn.execute("DELETE FROM quotation_items WHERE id=? AND quotation_id=?", (item_id, quotation_id))
        recalculate(conn, quotation_id)
        conn.commit()
    return None


@router.post("/import")
async def import_quotation_file(file: UploadFile = File(...)):
    content = await file.read()
    parsed = parse_upload(file.filename or "upload", content)
    return {"review_required": True, "apply_requires_confirmation": True, **parsed}


@router.post("/ai/extract")
async def ai_extract_quotation(payload: QuotationAIExtractRequest):
    if len(payload.text) > AI_QUOTATION_MAX_INPUT_LENGTH:
        raise HTTPException(status_code=413, detail=f"AI quotation input exceeds {AI_QUOTATION_MAX_INPUT_LENGTH} characters")
    with connect() as conn:
        ensure_tables(conn)
        context = client_context(conn, payload.context)
    provider = RuleBasedQuotationExtractionProvider()
    result = await provider.extract_quotation(payload.text, context)
    with connect() as conn:
        ensure_tables(conn)
        audit_ai_event(conn, "ai_extraction_requested", extracted=result.model_dump(), source_entity=f"service_case:{context.service_case_id}" if context.service_case_id else None, input_length=len(payload.text))
        conn.commit()
    return {
        "enabled": AI_QUOTATION_ENABLED,
        "provider": AI_QUOTATION_PROVIDER,
        "draft_only": True,
        "requires_user_review": True,
        "result": result.model_dump(),
    }


@router.post("/ai/create-draft", status_code=201)
def ai_create_draft(payload: QuotationAIDraftRequest):
    with connect() as conn:
        ensure_tables(conn)
        quotation_payload = extraction_to_quotation_payload(conn, payload)
    quotation = create_quotation(quotation_payload)
    with connect() as conn:
        ensure_tables(conn)
        audit_ai_event(conn, "ai_draft_created", quotation_id=quotation["id"], extracted=payload.extraction.model_dump(), approved_status=quotation.get("status"))
        conn.commit()
    return {"draft_only": True, "requires_user_review": True, "quotation": quotation}


def inventory_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM inventory_items ORDER BY id DESC LIMIT 1000").fetchall()
    return [row_dict(row) for row in rows]


@router.post("/{quotation_id:int}/validate-ai")
def validate_ai(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        items = get_items(conn, quotation_id)
        if not items and not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        results = QuotationAIService().validate_items(items, inventory_rows(conn))
        for result in results:
            conn.execute(
                """
                UPDATE quotation_items
                SET inventory_item_id=COALESCE(?, inventory_item_id), ai_normalized_description=?, ai_match_confidence=?,
                    ai_validation_status=?, ai_validation_notes=?
                WHERE id=?
                """,
                (
                    result.get("inventory_item_id"),
                    result.get("ai_normalized_description"),
                    result.get("ai_match_confidence"),
                    result.get("ai_validation_status"),
                    result.get("ai_validation_notes"),
                    result.get("id"),
                ),
            )
        conn.commit()
        audit_ai_event(conn, "ai_items_validated", quotation_id=quotation_id, extracted={"item_count": len(results)})
        conn.commit()
        return {"safe_mode": "suggestions_only", "items": results}


@router.post("/{quotation_id:int}/ai/reprocess")
def reprocess_ai(quotation_id: int):
    return validate_ai(quotation_id)


@router.post("/{quotation_id:int}/submit-review")
def submit_review(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        conn.execute("UPDATE quotations SET status=?, updated_at=? WHERE id=?", ("under_review", now_iso(), quotation_id))
        audit_ai_event(conn, "quotation_submitted_for_review", quotation_id=quotation_id, approved_status="under_review")
        conn.commit()
        return serialize_quotation(conn, quotation_id)


@router.post("/{quotation_id:int}/approve")
def approve_quotation(quotation_id: int, payload: dict[str, Any] | None = None):
    payload = payload or {}
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        conn.execute(
            "UPDATE quotations SET status=?, approved_by=?, approved_at=?, updated_at=? WHERE id=?",
            ("approved", payload.get("approved_by") or "authorised_user", now_iso(), now_iso(), quotation_id),
        )
        fulfillment = ensure_customer_order_for_quotation(conn, quotation_id)
        conn.execute(
            "UPDATE service_offers SET status='approved', approved_by=?, approved_at=?, updated_at=? WHERE quotation_id=?",
            (payload.get("approved_by") or "authorised_user", now_iso(), now_iso(), quotation_id),
        )
        audit_ai_event(conn, "quotation_approved", quotation_id=quotation_id, approved_status="approved")
        conn.commit()
        return {**serialize_quotation(conn, quotation_id), "fulfillment": fulfillment}


@router.get("/client-orders/{customer_order_id:int}")
def get_client_order_workflow(customer_order_id: int):
    with connect() as conn:
        ensure_tables(conn)
        order = row_dict(conn.execute("SELECT * FROM customer_orders WHERE id=?", (customer_order_id,)).fetchone())
        if not order:
            raise HTTPException(status_code=404, detail="Client order not found")
        return {
            "client_order": order,
            "items": [row_dict(row) for row in conn.execute("SELECT * FROM customer_order_items WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
            "reservations": [row_dict(row) for row in conn.execute("SELECT * FROM stock_reservations WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
            "purchase_orders": [row_dict(row) for row in conn.execute("SELECT DISTINCT po.* FROM purchase_orders po JOIN purchase_order_items poi ON poi.purchase_order_id=po.id JOIN customer_order_items coi ON coi.id=poi.customer_order_item_id WHERE coi.customer_order_id=? ORDER BY po.id", (customer_order_id,)).fetchall()],
            "shipments": [row_dict(row) for row in conn.execute("SELECT DISTINCT s.* FROM shipments s JOIN shipment_items si ON si.shipment_id=s.id JOIN purchase_order_items poi ON poi.id=si.purchase_order_item_id JOIN customer_order_items coi ON coi.id=poi.customer_order_item_id WHERE coi.customer_order_id=? ORDER BY s.id", (customer_order_id,)).fetchall()],
            "service_reports": [row_dict(row) for row in conn.execute("SELECT * FROM service_reports WHERE customer_order_id=? ORDER BY id", (customer_order_id,)).fetchall()],
        }


@router.post("/client-orders/{customer_order_id:int}/purchase-orders", status_code=201)
def create_client_order_purchase_order(customer_order_id: int, payload: PurchaseFromClientOrderItemsRequest):
    with connect() as conn:
        ensure_tables(conn)
        valid_line_ids = {
            row["id"]
            for row in conn.execute("SELECT id FROM customer_order_items WHERE customer_order_id=?", (customer_order_id,)).fetchall()
        }
        selected = [line_id for line_id in payload.customer_order_item_ids if line_id in valid_line_ids]
        if not selected:
            raise HTTPException(status_code=400, detail="No selected lines belong to this client order")
        result = create_purchase_order_from_client_order_items(conn, selected, payload.supplier_id, payload.notes)
        conn.commit()
        return result


@router.post("/shipments", status_code=201)
def create_purchase_shipment(payload: ShipmentFromPurchaseOrderItemsRequest):
    with connect() as conn:
        ensure_tables(conn)
        result = create_shipment_for_purchase_order_items(conn, payload.purchase_order_item_quantities, payload.supplier_id, payload.shipment_no, payload.notes)
        conn.commit()
        return result


@router.post("/shipments/{shipment_id:int}/receive", status_code=201)
def receive_purchase_shipment(shipment_id: int, payload: ReceiveShipmentRequest):
    with connect() as conn:
        ensure_tables(conn)
        result = receive_shipment_items(conn, shipment_id, [line.model_dump() for line in payload.lines], payload.notes)
        conn.commit()
        return result


@router.post("/client-orders/{customer_order_id:int}/service-reports", status_code=201)
def create_client_order_service_report(customer_order_id: int, payload: ServiceReportRequest):
    with connect() as conn:
        ensure_tables(conn)
        result = create_service_report_for_client_order(conn, customer_order_id, [item.model_dump() for item in payload.items], payload.notes)
        conn.commit()
        return result


@router.post("/client-order-items/{customer_order_item_id:int}/cancel")
def cancel_client_order_line(customer_order_item_id: int, payload: CancelClientOrderItemRequest):
    with connect() as conn:
        ensure_tables(conn)
        result = cancel_client_order_item(conn, customer_order_item_id, payload.reason)
        conn.commit()
        return result


@router.post("/{quotation_id:int}/generate-pdf")
def generate_pdf(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        items = get_items(conn, quotation_id)
        content = build_pdf(quotation, items, get_client(conn, quotation.get("client_id")), get_equipment_groups(conn, quotation_id))
        output_dir = db_path().parent / "generated_quotations"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{quotation.get('quotation_number') or quotation.get('quotation_no') or quotation_id}.pdf".replace("/", "-")
        path = output_dir / filename
        path.write_bytes(content)
        conn.execute("UPDATE quotations SET generated_pdf_path=?, updated_at=? WHERE id=?", (str(path), now_iso(), quotation_id))
        audit_ai_event(conn, "quotation_pdf_generated", quotation_id=quotation_id, approved_status=quotation.get("status"))
        conn.commit()
        return {"quotation_id": quotation_id, "generated_pdf_path": str(path), "status": quotation.get("status")}


@router.get("/{quotation_id:int}/export/excel")
def export_excel(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        items = get_items(conn, quotation_id)
        content = build_excel(quotation, items, get_client(conn, quotation.get("client_id")))
        filename = f"{quotation.get('quotation_number') or quotation.get('quotation_no') or 'quotation'}.xlsx"
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/{quotation_id:int}/export/pdf")
def export_pdf(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        items = get_items(conn, quotation_id)
        content = build_pdf(quotation, items, get_client(conn, quotation.get("client_id")), get_equipment_groups(conn, quotation_id))
        filename = f"{quotation.get('quotation_number') or quotation.get('quotation_no') or 'quotation'}.pdf"
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})
