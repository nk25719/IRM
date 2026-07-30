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
            item_type="spare_part",
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
        audit_ai_event(conn, "quotation_approved", quotation_id=quotation_id, approved_status="approved")
        conn.commit()
        return serialize_quotation(conn, quotation_id)


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
