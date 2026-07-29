from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, inspect, or_, text
from sqlalchemy.orm import Session

from app import erp_models as erp
from app.database import Base, engine, get_db
from app.models.foundation import AuditEvent, Manufacturer, Supplier
from app.services.customer_contacts_import_service import CustomerContactsImportService, engagement_level, normalize_email

router = APIRouter(tags=["customer-contacts"])

CONTACT_MANAGE_ROLES = {"admin", "crm_user", "after_sales"}
CONTACT_VIEW_ROLES = CONTACT_MANAGE_ROLES | {"viewer", "sales", "procurement", "warehouse", "engineer"}


def ensure_customer_contact_tables():
    Base.metadata.create_all(bind=engine, tables=[erp.OrganizationDomainMapping.__table__])
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


def _contact_payload(db: Session, contact: erp.Contact, include_links: bool = False) -> dict:
    client = db.get(erp.Client, contact.client_id) if contact.client_id else None
    manufacturer = db.get(Manufacturer, contact.manufacturer_id) if contact.manufacturer_id else None
    supplier = db.get(Supplier, contact.supplier_id) if contact.supplier_id else None
    data = {column.name: getattr(contact, column.name) for column in contact.__table__.columns}
    data["organization_name"] = client.name if client else manufacturer.name if manufacturer else supplier.name if supplier else None
    if include_links:
        data["linked_records"] = linked_records(db, contact)
    return data


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
    content = CustomerContactsImportService(db, _user_id(request, db)).report_csv(import_id)
    return StreamingResponse(iter([content]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="customer-contacts-import-{import_id}.csv"'})


@router.get("/api/contacts")
def list_contacts(q: str = "", organization_type: str = "", contact_type: str = "", engagement_level_filter: str = Query("", alias="engagement_level"), shared_inbox: bool | None = None, missing_phone: bool = False, missing_role: bool = False, needs_review: bool = False, sort: str = "emails_exchanged", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
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
