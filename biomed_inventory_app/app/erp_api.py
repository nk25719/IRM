from typing import Type

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from . import erp_models as m
from . import erp_schemas as s

router = APIRouter(prefix="/api/erp", tags=["ERP Foundation"])

RESOURCE_MAP: dict[str, tuple[Type, Type[BaseModel]]] = {
    "clients": (m.Client, s.ClientIn),
    "departments": (m.Department, s.DepartmentIn),
    "contacts": (m.Contact, s.ContactIn),
    "cases": (m.Case, s.CaseIn),
    "case-items": (m.CaseItem, s.CaseItemIn),
    "client-activities": (m.ClientActivity, s.ClientActivityIn),
    "equipment": (m.Equipment, s.EquipmentIn),
    "inventory-items": (m.InventoryItem, s.InventoryItemIn),
    "procurement-requests": (m.ProcurementRequest, s.ProcurementRequestIn),
    "service-calls": (m.ServiceCall, s.ServiceCallIn),
    "pm-tasks": (m.PMTask, s.PMTaskIn),
    "contracts": (m.Contract, s.ContractIn),
    "warranties": (m.Warranty, s.WarrantyIn),
    "invoices": (m.Invoice, s.InvoiceIn),
}


def _resource(name: str):
    if name not in RESOURCE_MAP:
        raise HTTPException(status_code=404, detail=f"Unknown ERP resource: {name}")
    return RESOURCE_MAP[name]


def _serialize(obj):
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


@router.get("/{resource}")
def list_records(resource: str, db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
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
    valid_fields = set(schema.model_fields.keys())
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
