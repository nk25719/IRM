from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .quotation_ai_service import QuotationAIService
from .quotation_export import build_excel, build_pdf, calculate_item_total, calculate_totals
from .quotation_import_service import parse_upload


router = APIRouter(prefix="/quotations", tags=["Quotations"])


def db_path() -> Path:
    return Path(os.getenv("DB_PATH", Path(__file__).resolve().parent / "data" / "inventory.db"))


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
    inventory_item_id: int | None = None
    item_code: str | None = None
    manufacturer_part_number: str | None = None
    description: str
    quantity: float = Field(1, gt=0)
    unit_price: float = 0
    discount_percent: float = 0
    warranty: str | None = None
    delivery_time: str | None = None


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
    notes: str | None = None
    items: list[QuotationItemIn] = []


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
    notes: str | None = None


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
            notes TEXT,
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
            inventory_item_id INTEGER,
            item_code TEXT,
            manufacturer_part_number TEXT,
            description TEXT,
            ai_normalized_description TEXT,
            quantity REAL DEFAULT 1,
            unit_price REAL DEFAULT 0,
            discount_percent REAL DEFAULT 0,
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
        },
        "quotation_items": {
            "inventory_item_id": "INTEGER",
            "item_code": "TEXT",
            "manufacturer_part_number": "TEXT",
            "ai_normalized_description": "TEXT",
            "quantity": "REAL DEFAULT 1",
            "discount_percent": "REAL DEFAULT 0",
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
            currency TEXT DEFAULT 'USD',
            payment_terms TEXT,
            delivery_terms TEXT,
            warranty_terms TEXT,
            notes TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )


def next_quotation_number(conn: sqlite3.Connection) -> str:
    year = date.today().year
    row = conn.execute("SELECT COUNT(*) AS c FROM quotations WHERE COALESCE(quotation_number, quotation_no, '') LIKE ?", (f"QT-{year}-%",)).fetchone()
    return f"QT-{year}-{int(row['c'] or 0) + 1:05d}"


def get_items(conn: sqlite3.Connection, quotation_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM quotation_items WHERE quotation_id=? ORDER BY id", (quotation_id,)).fetchall()
    return [row_dict(row) for row in rows]


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
        "UPDATE quotations SET subtotal=?, vat_amount=?, total_amount=?, amount=?, updated_at=? WHERE id=?",
        (totals["subtotal"], totals["vat_amount"], totals["total_amount"], totals["total_amount"], now_iso(), quotation_id),
    )


def serialize_quotation(conn: sqlite3.Connection, quotation_id: int) -> dict[str, Any]:
    quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    items = get_items(conn, quotation_id)
    client = get_client(conn, quotation.get("client_id"))
    return {**quotation, "client": client, "items": items}


def insert_item(conn: sqlite3.Connection, quotation_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    line_total = calculate_item_total(payload)
    cur = conn.execute(
        """
        INSERT INTO quotation_items
        (quotation_id, inventory_item_id, item_code, manufacturer_part_number, description, quantity, qty, unit_price,
         discount_percent, line_total, total_price, warranty, delivery_time, ai_validation_status, ref)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quotation_id,
            payload.get("inventory_item_id"),
            payload.get("item_code"),
            payload.get("manufacturer_part_number"),
            payload.get("description"),
            payload.get("quantity") or 1,
            int(payload.get("quantity") or 1),
            payload.get("unit_price") or 0,
            payload.get("discount_percent") or 0,
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
        quotation_date = payload.quotation_date or date.today().isoformat()
        valid_until = payload.valid_until or (date.today() + timedelta(days=30)).isoformat()
        number = payload.quotation_number or next_quotation_number(conn)
        ts = now_iso()
        cur = conn.execute(
            """
            INSERT INTO quotations
            (quotation_number, quotation_no, client_id, department_id, contact_id, case_id, status, quotation_date, quote_date,
             valid_until, currency, discount_amount, vat_rate, payment_terms, delivery_terms, warranty_terms, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                payload.notes,
                ts,
                ts,
            ),
        )
        quotation_id = cur.lastrowid
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


@router.get("/{quotation_id}")
def get_quotation(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        return serialize_quotation(conn, quotation_id)


@router.patch("/{quotation_id}")
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


@router.delete("/{quotation_id}", status_code=204)
def delete_quotation(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        conn.execute("DELETE FROM quotation_items WHERE quotation_id=?", (quotation_id,))
        conn.execute("DELETE FROM quotation_attachments WHERE quotation_id=?", (quotation_id,))
        conn.execute("DELETE FROM quotations WHERE id=?", (quotation_id,))
        conn.commit()
    return None


@router.post("/{quotation_id}/items", status_code=201)
def create_item(quotation_id: int, payload: QuotationItemIn):
    with connect() as conn:
        ensure_tables(conn)
        if not conn.execute("SELECT id FROM quotations WHERE id=?", (quotation_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Quotation not found")
        item = insert_item(conn, quotation_id, payload.model_dump())
        conn.commit()
        return item


@router.patch("/{quotation_id}/items/{item_id}")
def patch_item(quotation_id: int, item_id: int, payload: dict[str, Any]):
    allowed = {"inventory_item_id", "item_code", "manufacturer_part_number", "description", "quantity", "unit_price", "discount_percent", "warranty", "delivery_time", "ai_normalized_description", "ai_match_confidence", "ai_validation_status", "ai_validation_notes"}
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


@router.delete("/{quotation_id}/items/{item_id}", status_code=204)
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


def inventory_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM inventory_items ORDER BY id DESC LIMIT 1000").fetchall()
    return [row_dict(row) for row in rows]


@router.post("/{quotation_id}/validate-ai")
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
        return {"safe_mode": "suggestions_only", "items": results}


@router.get("/{quotation_id}/export/excel")
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


@router.get("/{quotation_id}/export/pdf")
def export_pdf(quotation_id: int):
    with connect() as conn:
        ensure_tables(conn)
        quotation = row_dict(conn.execute("SELECT * FROM quotations WHERE id=?", (quotation_id,)).fetchone())
        if not quotation:
            raise HTTPException(status_code=404, detail="Quotation not found")
        items = get_items(conn, quotation_id)
        content = build_pdf(quotation, items, get_client(conn, quotation.get("client_id")))
        filename = f"{quotation.get('quotation_number') or quotation.get('quotation_no') or 'quotation'}.pdf"
        return Response(content, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})
