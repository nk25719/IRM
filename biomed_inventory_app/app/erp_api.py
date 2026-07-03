from typing import Type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import erp_models as m
from . import erp_schemas as s
from .database import get_db

router = APIRouter(prefix="/api/erp", tags=["ERP Foundation"])

RESOURCE_MAP: dict[str, tuple[Type, Type[BaseModel]]] = {
    "clients": (m.Client, s.ClientIn),
    "departments": (m.Department, s.DepartmentIn),
    "contacts": (m.Contact, s.ContactIn),
    "users": (m.User, s.UserIn),
    "engineers": (m.Engineer, s.EngineerIn),
    "equipment": (m.Equipment, s.EquipmentIn),
    "contracts": (m.Contract, s.ContractIn),
    "warranties": (m.Warranty, s.WarrantyIn),
    "cases": (m.Case, s.CaseIn),
    "service_calls": (m.ServiceCall, s.ServiceCallIn),
    "service-calls": (m.ServiceCall, s.ServiceCallIn),
    "pm_tasks": (m.PMTask, s.PMTaskIn),
    "pm-tasks": (m.PMTask, s.PMTaskIn),
    "inventory_items": (m.InventoryItem, s.InventoryItemIn),
    "inventory-items": (m.InventoryItem, s.InventoryItemIn),
    "case_items": (m.CaseItem, s.CaseItemIn),
    "case-items": (m.CaseItem, s.CaseItemIn),
    "procurement_requests": (m.ProcurementRequest, s.ProcurementRequestIn),
    "procurement-requests": (m.ProcurementRequest, s.ProcurementRequestIn),
    "client_activities": (m.ClientActivity, s.ClientActivityIn),
    "client-activities": (m.ClientActivity, s.ClientActivityIn),
    "invoices": (m.Invoice, s.InvoiceIn),
    "quotations": (m.Quotation, s.QuotationIn),
    "quotation_items": (m.QuotationItem, s.QuotationItemIn),
    "quotation-items": (m.QuotationItem, s.QuotationItemIn),
    "quotation_attachments": (m.QuotationAttachment, s.QuotationAttachmentIn),
    "quotation-attachments": (m.QuotationAttachment, s.QuotationAttachmentIn),
    "quotation_templates": (m.QuotationTemplate, s.QuotationTemplateIn),
    "quotation-templates": (m.QuotationTemplate, s.QuotationTemplateIn),
}


def _resource(name: str):
    if name not in RESOURCE_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown ERP resource: {name}")
    return RESOURCE_MAP[name]


def _serialize(obj):
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    return {
        "clients": db.query(func.count(m.Client.id)).scalar() or 0,
        "equipment": db.query(func.count(m.Equipment.id)).scalar() or 0,
        "service_calls": db.query(func.count(m.ServiceCall.id)).scalar() or 0,
        "pm_tasks": db.query(func.count(m.PMTask.id)).scalar() or 0,
        "cases": db.query(func.count(m.Case.id)).scalar() or 0,
        "mdmanser_service_records": db.query(func.count(m.MDManserServiceRecord.id)).scalar() or 0,
    }


@router.get("/mdmanser/service-records")
def mdmanser_service_records(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    q: str = "",
    institution: str = "",
    engineer_name: str = "",
    serial_number: str = "",
    report_number: str = "",
):
    query = db.query(m.MDManserServiceRecord)
    if q:
        needle = f"%{q}%"
        query = query.filter(
            m.MDManserServiceRecord.report_number.ilike(needle)
            | m.MDManserServiceRecord.institution.ilike(needle)
            | m.MDManserServiceRecord.engineer_name.ilike(needle)
            | m.MDManserServiceRecord.serial_number.ilike(needle)
            | m.MDManserServiceRecord.product_type.ilike(needle)
            | m.MDManserServiceRecord.model.ilike(needle)
        )
    if institution:
        query = query.filter(m.MDManserServiceRecord.institution.ilike(f"%{institution}%"))
    if engineer_name:
        query = query.filter(m.MDManserServiceRecord.engineer_name.ilike(f"%{engineer_name}%"))
    if serial_number:
        query = query.filter(m.MDManserServiceRecord.serial_number.ilike(f"%{serial_number}%"))
    if report_number:
        query = query.filter(m.MDManserServiceRecord.report_number.ilike(f"%{report_number}%"))
    rows = query.order_by(m.MDManserServiceRecord.id.desc()).offset(offset).limit(limit).all()
    return [_serialize(row) for row in rows]


@router.get("/mdmanser/import-summary")
def mdmanser_import_summary(db: Session = Depends(get_db)):
    return {
        "service_records": db.query(func.count(m.MDManserServiceRecord.id)).scalar() or 0,
        "institutions": db.query(func.count(func.distinct(m.MDManserServiceRecord.institution))).scalar() or 0,
        "engineers": db.query(func.count(func.distinct(m.MDManserServiceRecord.engineer_name))).scalar() or 0,
        "suppliers": db.query(func.count(func.distinct(m.MDManserServiceRecord.supplier))).scalar() or 0,
        "product_types": db.query(func.count(func.distinct(m.MDManserServiceRecord.product_type))).scalar() or 0,
        "models": db.query(func.count(func.distinct(m.MDManserServiceRecord.model))).scalar() or 0,
        "calendar_events": db.query(func.count(m.MDManserCalendarEvent.id)).scalar() or 0,
    }


@router.get("/pm/tasks")
def pm_tasks(db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    rows = db.query(m.PMTask).order_by(m.PMTask.scheduled_date.asc().nullslast(), m.PMTask.id.desc()).offset(offset).limit(limit).all()
    return [_serialize(row) for row in rows]


@router.get("/{resource}")
def list_records(resource: str, db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    model, _ = _resource(resource)
    rows = db.query(model).order_by(model.id.desc()).offset(offset).limit(limit).all()
    return [_serialize(row) for row in rows]


@router.get("/{resource}/{record_id}")
def get_record(resource: str, record_id: int, db: Session = Depends(get_db)):
    model, _ = _resource(resource)
    row = db.get(model, record_id)
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    return _serialize(row)


@router.post("/{resource}", status_code=201)
def create_record(resource: str, payload: dict, db: Session = Depends(get_db)):
    model, schema = _resource(resource)
    data = schema.model_validate(payload).model_dump(exclude_unset=True)
    row = model(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.put("/{resource}/{record_id}")
def update_record(resource: str, record_id: int, payload: dict, db: Session = Depends(get_db)):
    model, schema = _resource(resource)
    row = db.get(model, record_id)
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    valid_fields = set(schema.model_fields)
    for key, value in payload.items():
        if key in valid_fields:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/{resource}/{record_id}", status_code=204)
def delete_record(resource: str, record_id: int, db: Session = Depends(get_db)):
    model, _ = _resource(resource)
    row = db.get(model, record_id)
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(row)
    db.commit()
    return None
