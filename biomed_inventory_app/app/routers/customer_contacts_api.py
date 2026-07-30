from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, inspect, or_, text
from sqlalchemy.orm import Session

from app import erp_models as erp
from app.database import Base, engine, get_db
from app.models.foundation import AuditEvent, Manufacturer, Supplier
from app.services.customer_contacts_import_service import (
    ALLOWED_CONTACT_IMPORT_EXTENSIONS,
    CONTACT_IMPORT_MAX_FILE_SIZE_MB,
    CONTACT_IMPORT_STORAGE,
    CustomerContactsImportService,
    CustomerContactsLargeImportService,
    analyse_customer_contacts_job,
    engagement_level,
    import_customer_contacts_job,
    normalize_email,
    safe_filename,
)

router = APIRouter(tags=["customer-contacts"])

CONTACT_MANAGE_ROLES = {"admin", "crm_user", "after_sales"}
CONTACT_VIEW_ROLES = CONTACT_MANAGE_ROLES | {"viewer", "sales", "procurement", "warehouse", "engineer"}


def ensure_customer_contact_tables():
    Base.metadata.create_all(bind=engine, tables=[erp.OrganizationDomainMapping.__table__, erp.CustomerContactImportJob.__table__, erp.CustomerContactImportStaging.__table__])
    inspector = inspect(engine)
    if "contacts" not in inspector.get_table_names():
        Base.metadata.create_all(bind=engine, tables=[erp.Contact.__table__])
        return
    existing = {column["name"] for column in inspector.get_columns("contacts")}
    columns = {
        "client_site_id": "INTEGER",
        "manufacturer_id": "INTEGER",
        "supplier_id": "INTEGER",
        "first_name": "VARCHAR(120)",
        "last_name": "VARCHAR(120)",
        "display_name": "VARCHAR(255)",
        "normalized_email": "VARCHAR(255)",
        "role_title": "VARCHAR(255)",
        "department": "VARCHAR(255)",
        "phone_original": "VARCHAR(120)",
        "phone_verified": "BOOLEAN DEFAULT 0 NOT NULL",
        "email_domain": "VARCHAR(255)",
        "contact_type": "VARCHAR(80) DEFAULT 'unknown' NOT NULL",
        "organization_type": "VARCHAR(80) DEFAULT 'unknown' NOT NULL",
        "emails_exchanged": "INTEGER DEFAULT 0 NOT NULL",
        "engagement_level": "VARCHAR(40) DEFAULT 'low' NOT NULL",
        "is_shared_inbox": "BOOLEAN DEFAULT 0 NOT NULL",
        "is_automated_address": "BOOLEAN DEFAULT 0 NOT NULL",
        "is_active": "BOOLEAN DEFAULT 1 NOT NULL",
        "is_primary": "BOOLEAN DEFAULT 0 NOT NULL",
        "source": "VARCHAR(120)",
        "source_reference": "TEXT",
        "data_quality_status": "VARCHAR(80) DEFAULT 'needs_review' NOT NULL",
        "last_imported_at": "DATETIME",
        "contact_owner_user_id": "INTEGER",
        "next_action": "TEXT",
        "created_at": "DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL",
    }
    with engine.begin() as conn:
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(text(f'ALTER TABLE contacts ADD COLUMN "{name}" {ddl}'))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_contacts_normalized_email ON contacts(normalized_email) WHERE normalized_email IS NOT NULL AND normalized_email != ''"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contacts_email_domain ON contacts(email_domain)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contacts_organization_type ON contacts(organization_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contacts_engagement_level ON contacts(engagement_level)"))


def _role(request: Request) -> str:
    return request.session.get("role") or "viewer"


def _require_manage(request: Request):
    if _role(request) not in CONTACT_MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Customer contact import/manage permission required")


def _user_id(request: Request, db: Session) -> int | None:
    username = request.session.get("username")
    if not username:
        return None
    user = db.query(erp.User).filter(erp.User.username == username).first()
    return user.id if user else None


async def _store_import_upload(file: UploadFile) -> tuple[Path, int, str]:
    suffix = Path(file.filename or "").suffix.casefold()
    if suffix not in ALLOWED_CONTACT_IMPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload must be .xlsx or .csv")
    stored_name = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}-{safe_filename(file.filename or 'customer-contacts')}{suffix}"
    path = CONTACT_IMPORT_STORAGE / stored_name
    max_bytes = CONTACT_IMPORT_MAX_FILE_SIZE_MB * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    with path.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                handle.close()
                path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Upload exceeds {CONTACT_IMPORT_MAX_FILE_SIZE_MB} MB")
            digest.update(chunk)
            handle.write(chunk)
    return path, size, digest.hexdigest()


def _contact_payload(db: Session, contact: erp.Contact, include_links: bool = False) -> dict:
    client = db.get(erp.Client, contact.client_id) if contact.client_id else None
    manufacturer = db.get(Manufacturer, contact.manufacturer_id) if contact.manufacturer_id else None
    supplier = db.get(Supplier, contact.supplier_id) if contact.supplier_id else None
    data = {column.name: getattr(contact, column.name) for column in contact.__table__.columns}
    data["organization_name"] = client.name if client else manufacturer.name if manufacturer else supplier.name if supplier else None
    if include_links:
        data["linked_records"] = linked_records(db, contact)
    return data


def _client_contact_query(db: Session, client_id: int, include_inactive: bool = False):
    query = db.query(erp.Contact).filter(erp.Contact.client_id == client_id, erp.Contact.organization_type.in_(["client", "unknown"]))
    if not include_inactive:
        query = query.filter(erp.Contact.is_active.is_(True))
    return query


def linked_records(db: Session, contact: erp.Contact) -> dict:
    result = {"service_cases": [], "equipment": [], "quotations": [], "contracts": [], "pm": [], "client_activities": []}
    if not contact.client_id:
        return result
    result["service_cases"] = [{"id": row.id, "title": row.title, "status": row.status} for row in db.query(erp.Case).filter_by(client_id=contact.client_id).order_by(erp.Case.id.desc()).limit(20)]
    result["equipment"] = [{"id": row.id, "name": row.name, "serial_number": row.serial_number} for row in db.query(erp.Equipment).filter_by(client_id=contact.client_id).order_by(erp.Equipment.id.desc()).limit(20)]
    result["quotations"] = [{"id": row.id, "quotation_number": row.quotation_number or row.quotation_no, "status": row.status} for row in db.query(erp.Quotation).filter_by(client_id=contact.client_id).order_by(erp.Quotation.id.desc()).limit(20)]
    result["contracts"] = [{"id": row.id, "contract_reference": row.contract_reference, "status": row.status} for row in db.query(erp.Contract).filter_by(client_id=contact.client_id).order_by(erp.Contract.id.desc()).limit(20)]
    result["pm"] = [{"id": row.id, "pm_label": row.pm_label, "status": row.status, "scheduled_date": row.scheduled_date} for row in db.query(erp.PMTask).filter_by(client_id=contact.client_id).order_by(erp.PMTask.id.desc()).limit(20)]
    result["client_activities"] = [{"id": row.id, "title": row.title, "status": row.status} for row in db.query(erp.ClientActivity).filter_by(client_id=contact.client_id).order_by(erp.ClientActivity.id.desc()).limit(20)]
    return result


@router.post("/api/imports/customer-contacts/preview")
async def customer_contacts_preview(request: Request, sheet_name: str | None = Form(None), file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_manage(request)
    content = await file.read()
    try:
        return CustomerContactsImportService(db, _user_id(request, db)).preview(content, file.filename or "Customer_Contacts-2.xlsx", sheet_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/imports/customer-contacts/upload")
async def customer_contacts_upload(background_tasks: BackgroundTasks, request: Request, idempotency_key: str | None = Form(None), allow_duplicate: bool = Form(False), file: UploadFile = File(...), db: Session = Depends(get_db)):
    _require_manage(request)
    path, size, checksum = await _store_import_upload(file)
    try:
        payload = CustomerContactsLargeImportService(db, _user_id(request, db)).create_upload_job_from_stored_file(path, file.filename or path.name, size, checksum, idempotency_key, allow_duplicate)
        if payload.get("id"):
            background_tasks.add_task(analyse_customer_contacts_job, int(payload["id"]))
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/imports/customer-contacts/history")
def customer_contacts_history(request: Request, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    _require_manage(request)
    rows = db.query(erp.CustomerContactImportJob).order_by(erp.CustomerContactImportJob.id.desc()).limit(limit).all()
    service = CustomerContactsLargeImportService(db, _user_id(request, db))
    return {"items": [service.job_payload(row) for row in rows]}


@router.get("/api/imports/customer-contacts/{import_id}/status")
def customer_contacts_job_status(import_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        return CustomerContactsLargeImportService(db, _user_id(request, db)).summary(import_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/imports/customer-contacts/{import_id}/summary")
def customer_contacts_job_summary(import_id: int, request: Request, db: Session = Depends(get_db)):
    return customer_contacts_job_status(import_id, request, db)


@router.get("/api/imports/customer-contacts/{import_id}/rows")
def customer_contacts_job_rows(import_id: int, request: Request, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), status: str = "", action: str = "", domain: str = "", organization_id: int | None = None, search: str = "", sort_by: str = "source_row_number", sort_direction: str = Query("asc", pattern="^(asc|desc)$"), db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        return CustomerContactsLargeImportService(db, _user_id(request, db)).rows(import_id, page, page_size, status, action, domain, organization_id, search, sort_by, sort_direction)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/imports/customer-contacts/{import_id}/bulk-decision")
def customer_contacts_bulk_decision(import_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        return CustomerContactsLargeImportService(db, _user_id(request, db)).bulk_decision(import_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/imports/customer-contacts/{import_id}/confirm")
def customer_contacts_job_confirm(import_id: int, background_tasks: BackgroundTasks, request: Request, payload: dict | None = Body(None), idempotency_key: str | None = Header(None, alias="Idempotency-Key"), db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        key = idempotency_key or (payload or {}).get("idempotency_key")
        result = CustomerContactsLargeImportService(db, _user_id(request, db)).confirm_job(import_id, key)
        background_tasks.add_task(import_customer_contacts_job, import_id)
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/imports/customer-contacts/{import_id}/cancel")
def customer_contacts_job_cancel(import_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        return CustomerContactsLargeImportService(db, _user_id(request, db)).cancel(import_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/imports/customer-contacts/{import_id}/resume")
def customer_contacts_job_resume(import_id: int, background_tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        result = CustomerContactsLargeImportService(db, _user_id(request, db)).resume(import_id)
        task = import_customer_contacts_job if result.get("phase") == "database_import" else analyse_customer_contacts_job
        background_tasks.add_task(task, import_id)
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/imports/customer-contacts/confirm")
def customer_contacts_confirm(payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        return CustomerContactsImportService(db, _user_id(request, db)).confirm(int(payload.get("import_id")), payload.get("decisions") or [])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/imports/customer-contacts/{import_id}")
def customer_contacts_import(import_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    try:
        return CustomerContactsImportService(db, _user_id(request, db)).import_payload(import_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/imports/customer-contacts/{import_id}/report")
def customer_contacts_report(import_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    if db.get(erp.CustomerContactImportJob, import_id):
        content = CustomerContactsLargeImportService(db, _user_id(request, db)).report_csv(import_id)
    else:
        content = CustomerContactsImportService(db, _user_id(request, db)).report_csv(import_id)
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="customer-contacts-import-{import_id}.csv"'})


@router.get("/api/contacts")
def list_contacts(q: str = "", organization_type: str = "", contact_type: str = "", engagement_level_filter: str = Query("", alias="engagement_level"), shared_inbox: bool | None = None, missing_phone: bool = False, missing_role: bool = False, needs_review: bool = False, sort: str = "emails_exchanged", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    engagement_level_filter = engagement_level_filter if isinstance(engagement_level_filter, str) else ""
    query = db.query(erp.Contact)
    if q:
        like = f"%{q.casefold()}%"
        query = query.filter(or_(func.lower(erp.Contact.name).like(like), func.lower(erp.Contact.display_name).like(like), func.lower(erp.Contact.email).like(like), func.lower(erp.Contact.phone).like(like), func.lower(erp.Contact.email_domain).like(like)))
    if organization_type:
        query = query.filter(erp.Contact.organization_type == organization_type)
    if contact_type:
        query = query.filter(erp.Contact.contact_type == contact_type)
    if engagement_level_filter:
        query = query.filter(erp.Contact.engagement_level == engagement_level_filter)
    if shared_inbox is not None:
        query = query.filter(erp.Contact.is_shared_inbox.is_(shared_inbox))
    if missing_phone:
        query = query.filter(or_(erp.Contact.phone.is_(None), erp.Contact.phone == ""))
    if missing_role:
        query = query.filter(or_(erp.Contact.role_title.is_(None), erp.Contact.role_title == ""))
    if needs_review:
        query = query.filter(erp.Contact.data_quality_status.in_(["needs_review", "needs_organization_match", "needs_role", "needs_phone"]))
    total = query.count()
    if sort == "name":
        query = query.order_by(erp.Contact.display_name.asc().nullslast(), erp.Contact.name.asc())
    elif sort == "newest_imported":
        query = query.order_by(erp.Contact.last_imported_at.desc().nullslast(), erp.Contact.id.desc())
    else:
        query = query.order_by(erp.Contact.emails_exchanged.desc(), erp.Contact.display_name.asc().nullslast())
    rows = query.offset(offset).limit(limit).all()
    return {"items": [_contact_payload(db, row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/api/contacts/export")
def export_contacts(q: str = "", organization_type: str = "", contact_type: str = "", engagement_level_filter: str = Query("", alias="engagement_level"), shared_inbox: bool | None = None, missing_phone: bool = False, missing_role: bool = False, needs_review: bool = False, sort: str = "emails_exchanged", db: Session = Depends(get_db)):
    engagement_level_filter = engagement_level_filter if isinstance(engagement_level_filter, str) else ""
    data = list_contacts(q, organization_type, contact_type, engagement_level_filter, shared_inbox, missing_phone, missing_role, needs_review, sort, 500, 0, db)
    columns = ["id", "display_name", "email", "phone", "organization_type", "organization_name", "contact_type", "role_title", "department", "engagement_level", "emails_exchanged", "data_quality_status", "last_imported_at", "next_action"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for item in data["items"]:
        writer.writerow({column: item.get(column, "") for column in columns})
    content = stream.getvalue().encode("utf-8-sig")
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="customer-contacts.csv"'})


@router.get("/api/clients/{client_id}/contacts")
def list_client_contacts(client_id: int, q: str = "", primary: bool = False, contact_type: str = "", missing_phone: bool = False, missing_role: bool = False, needs_review: bool = False, inactive: bool = False, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if not db.get(erp.Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    query = _client_contact_query(db, client_id, include_inactive=inactive)
    if q:
        like = f"%{q.casefold()}%"
        query = query.filter(or_(func.lower(erp.Contact.name).like(like), func.lower(erp.Contact.display_name).like(like), func.lower(erp.Contact.email).like(like), func.lower(erp.Contact.phone).like(like), func.lower(erp.Contact.role_title).like(like), func.lower(erp.Contact.department).like(like)))
    if primary:
        query = query.filter(erp.Contact.is_primary.is_(True))
    if contact_type:
        query = query.filter(erp.Contact.contact_type == contact_type)
    if missing_phone:
        query = query.filter(or_(erp.Contact.phone.is_(None), erp.Contact.phone == ""))
    if missing_role:
        query = query.filter(or_(erp.Contact.role_title.is_(None), erp.Contact.role_title == ""))
    if needs_review:
        query = query.filter(erp.Contact.data_quality_status.in_(["needs_review", "needs_organization_match", "needs_role", "needs_phone"]))
    total = query.count()
    rows = query.order_by(erp.Contact.is_primary.desc(), erp.Contact.display_name.asc().nullslast(), erp.Contact.name.asc()).offset(offset).limit(limit).all()
    return {"items": [_contact_payload(db, row, include_links=True) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.post("/api/clients/{client_id}/contacts", status_code=201)
def create_client_contact(client_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    if not db.get(erp.Client, client_id):
        raise HTTPException(status_code=404, detail="Client not found")
    email = normalize_email(payload.get("email"))
    contact = erp.Contact(
        client_id=client_id,
        client_site_id=payload.get("client_site_id") or (payload.get("client_site_ids") or [None])[0],
        name=payload.get("display_name") or payload.get("name") or email or "Client contact",
        display_name=payload.get("display_name") or payload.get("name"),
        email=email or None,
        normalized_email=email or None,
        email_domain=email.split("@", 1)[1] if "@" in email else None,
        organization_type="client",
    )
    for field in ("phone", "role_title", "department", "contact_type", "notes", "next_action", "data_quality_status", "is_primary", "is_active"):
        if field in payload:
            setattr(contact, field, payload[field])
    contact.emails_exchanged = int(payload.get("emails_exchanged") or 0)
    contact.engagement_level = engagement_level(contact.emails_exchanged)
    if contact.is_primary:
        db.query(erp.Contact).filter(erp.Contact.client_id == client_id).update({"is_primary": False}, synchronize_session=False)
    db.add(contact)
    db.flush()
    db.add(AuditEvent(event_type="client_contact_created", entity_type="contact", entity_id=str(contact.id), user_id=_user_id(request, db), source="clients", new_values=payload))
    db.commit()
    db.refresh(contact)
    return _contact_payload(db, contact, include_links=True)


@router.patch("/api/clients/{client_id}/contacts/{contact_id}")
def update_client_contact(client_id: int, contact_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    contact = db.query(erp.Contact).filter_by(id=contact_id, client_id=client_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Client contact not found")
    old = _contact_payload(db, contact)
    if "email" in payload:
        email = normalize_email(payload.get("email"))
        contact.email = email or None
        contact.normalized_email = email or None
        contact.email_domain = email.split("@", 1)[1] if "@" in email else None
    if "client_site_ids" in payload:
        contact.client_site_id = (payload.get("client_site_ids") or [None])[0]
    for field in ("display_name", "name", "phone", "role_title", "department", "contact_type", "client_site_id", "notes", "next_action", "data_quality_status", "is_active", "is_primary"):
        if field in payload:
            setattr(contact, field, payload[field])
    if "emails_exchanged" in payload:
        contact.emails_exchanged = int(payload["emails_exchanged"] or 0)
        contact.engagement_level = engagement_level(contact.emails_exchanged)
    if contact.is_primary:
        db.query(erp.Contact).filter(erp.Contact.client_id == client_id, erp.Contact.id != contact.id).update({"is_primary": False}, synchronize_session=False)
    db.add(AuditEvent(event_type="client_contact_updated", entity_type="contact", entity_id=str(contact.id), user_id=_user_id(request, db), source="clients", old_values=old, new_values=payload))
    db.commit()
    db.refresh(contact)
    return _contact_payload(db, contact, include_links=True)


@router.post("/api/clients/{client_id}/contacts/{contact_id}/deactivate")
def deactivate_client_contact(client_id: int, contact_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    return update_client_contact(client_id, contact_id, {"is_active": False, "is_primary": False}, request, db)


@router.post("/api/clients/{client_id}/contacts/{contact_id}/set-primary")
def set_primary_client_contact(client_id: int, contact_id: int, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    return update_client_contact(client_id, contact_id, {"is_primary": True}, request, db)


@router.get("/api/contacts/analytics")
def contact_analytics(db: Session = Depends(get_db)):
    total = db.query(erp.Contact).filter(erp.Contact.is_active.is_(True)).count()
    return {
        "total_active_contacts": total,
        "needs_organization_matching": db.query(erp.Contact).filter(erp.Contact.data_quality_status == "needs_organization_match").count(),
        "missing_roles": db.query(erp.Contact).filter(or_(erp.Contact.role_title.is_(None), erp.Contact.role_title == "")).count(),
        "missing_phone_numbers": db.query(erp.Contact).filter(or_(erp.Contact.phone.is_(None), erp.Contact.phone == "")).count(),
        "high_engagement_contacts": db.query(erp.Contact).filter(erp.Contact.engagement_level == "high").count(),
        "shared_inbox_count": db.query(erp.Contact).filter(erp.Contact.is_shared_inbox.is_(True)).count(),
        "automated_awaiting_review": db.query(erp.Contact).filter(erp.Contact.is_automated_address.is_(True), erp.Contact.data_quality_status == "needs_review").count(),
    }


@router.get("/api/contacts/{contact_id}")
def get_contact(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(erp.Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return _contact_payload(db, contact, include_links=True)


@router.post("/api/contacts", status_code=201)
def create_contact(payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    email = normalize_email(payload.get("email"))
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    contact = erp.Contact(name=payload.get("display_name") or payload.get("name") or email, display_name=payload.get("display_name") or payload.get("name"), email=email, normalized_email=email, email_domain=email.split("@", 1)[1] if "@" in email else None)
    for field in ("phone", "role_title", "contact_type", "organization_type", "client_id", "manufacturer_id", "supplier_id", "client_site_id", "notes", "data_quality_status"):
        if field in payload:
            setattr(contact, field, payload[field])
    contact.emails_exchanged = int(payload.get("emails_exchanged") or 0)
    contact.engagement_level = engagement_level(contact.emails_exchanged)
    db.add(contact)
    db.flush()
    db.add(AuditEvent(event_type="contact_created", entity_type="contact", entity_id=str(contact.id), user_id=_user_id(request, db), source="crm", new_values=payload))
    db.commit()
    db.refresh(contact)
    return _contact_payload(db, contact)


@router.patch("/api/contacts/{contact_id}")
def update_contact(contact_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    contact = db.get(erp.Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    old = _contact_payload(db, contact)
    for field in ("display_name", "name", "phone", "role_title", "department", "contact_type", "organization_type", "client_id", "manufacturer_id", "supplier_id", "client_site_id", "notes", "data_quality_status", "is_active", "is_primary", "next_action"):
        if field in payload:
            setattr(contact, field, payload[field])
    if "emails_exchanged" in payload:
        contact.emails_exchanged = int(payload["emails_exchanged"] or 0)
        contact.engagement_level = engagement_level(contact.emails_exchanged)
    db.add(AuditEvent(event_type="contact_updated", entity_type="contact", entity_id=str(contact.id), user_id=_user_id(request, db), source="crm", old_values=old, new_values=payload))
    db.commit()
    db.refresh(contact)
    return _contact_payload(db, contact)


@router.post("/api/contacts/bulk-organization-match")
def bulk_organization_match(payload: dict, request: Request, db: Session = Depends(get_db)):
    _require_manage(request)
    domain = str(payload.get("domain") or "").strip().casefold()
    organization_type = payload.get("organization_type")
    organization_id = int(payload.get("organization_id") or 0)
    if not domain or not organization_type or not organization_id:
        raise HTTPException(status_code=400, detail="domain, organization_type, and organization_id are required")
    mapping = db.query(erp.OrganizationDomainMapping).filter(func.lower(erp.OrganizationDomainMapping.domain) == domain).first()
    if not mapping:
        mapping = erp.OrganizationDomainMapping(domain=domain)
        db.add(mapping)
    mapping.organization_type = organization_type
    mapping.organization_id = organization_id
    mapping.status = "approved"
    mapping.created_by_id = _user_id(request, db)
    updates = db.query(erp.Contact).filter(erp.Contact.email_domain == domain).update({"organization_type": organization_type, f"{organization_type}_id": organization_id, "data_quality_status": "needs_role"}, synchronize_session=False) if organization_type in {"client", "manufacturer", "supplier"} else 0
    db.add(AuditEvent(event_type="contact_domain_mapping_selected", entity_type="organization_domain_mapping", entity_id=domain, user_id=_user_id(request, db), source="crm", new_values=payload))
    db.commit()
    return {"domain": domain, "updated_contacts": updates}
