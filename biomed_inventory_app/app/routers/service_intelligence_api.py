from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.erp_models import ContractPMCommitment, CustomerContractEquipment, CustomerServiceContract, ManufacturerAgreement, ManufacturerAgreementEquipment, ServiceOpportunity
from app.models.foundation import AuditEvent
from app.services.service_intelligence import ServiceIntelligenceService
from app.data_management.template_registry import all_datasets

router = APIRouter(prefix="/api/service-intelligence", tags=["Service Intelligence"])

DEFAULT_SETTINGS = {
    "warranty_expiring_soon_window_days": 180,
    "default_warning_days": 90,
    "extended_warning_days": 180,
    "high_priority_threshold": 80,
    "medium_priority_threshold": 50,
    "score_weights": {
        "no_active_service_contract": 35,
        "warranty_expired": 40,
        "warranty_expires_90_days": 30,
        "warranty_expires_180_days": 20,
        "warranty_unknown": 10,
        "pm_overdue": 15,
        "no_completed_pm_12_months": 10,
        "open_corrective_case": 10,
        "more_than_two_corrective_cases_12_months": 15,
        "equipment_age_gt_8_years": 10,
    },
    "ignored_equipment_statuses": ["DISPOSED", "INACTIVE"],
    "excluded_equipment_categories": [],
    "serial_normalization_rules": ["trim", "uppercase", "remove_formatting_spaces"],
    "automatic_refresh_after_import": True,
    "automatic_opportunity_creation": True,
    "opportunity_assignment_defaults": {},
    "duplicate_handling_behavior": "flag_for_review",
}


def ensure_service_intelligence_tables() -> None:
    from app.database import engine

    ManufacturerAgreement.__table__.create(bind=engine, checkfirst=True)
    ManufacturerAgreementEquipment.__table__.create(bind=engine, checkfirst=True)
    CustomerServiceContract.__table__.create(bind=engine, checkfirst=True)
    CustomerContractEquipment.__table__.create(bind=engine, checkfirst=True)
    ContractPMCommitment.__table__.create(bind=engine, checkfirst=True)
    ServiceOpportunity.__table__.create(bind=engine, checkfirst=True)


class OpportunityPatch(BaseModel):
    status: str | None = Field(None, pattern="^(NEW|REVIEWED|ASSIGNED|CONTACTED|QUOTE_REQUESTED|QUOTE_SENT|WON|LOST|DISMISSED)$")
    assigned_to_user_id: int | None = None
    notes: str | None = None
    quote_id: int | None = None
    lost_reason: str | None = None


def _filters(
    client_id: int | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    serial_number: str | None = None,
    equipment_id: int | None = None,
    lifecycle_status: str | None = None,
    opportunity_type: str | None = None,
    domain: str | None = Query(None, pattern="^(Manufacturer|Customer)$"),
    status: str | None = None,
    priority: str | None = None,
    assigned_to_user_id: int | None = None,
    warranty_end_from: date | None = None,
    warranty_end_to: date | None = None,
    contract_coverage: str | None = Query(None, pattern="^(covered|uncovered)$"),
    minimum_score: int | None = Query(None, ge=0),
    search: str | None = None,
    sort: str | None = "-score",
) -> dict[str, Any]:
    return {key: value for key, value in locals().items() if value not in (None, "")}


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    return ServiceIntelligenceService(db).summary()


@router.get("/settings")
def settings():
    return DEFAULT_SETTINGS


@router.get("/templates")
def templates():
    datasets = [dataset for dataset in all_datasets() if dataset.domain in {"Contract Intelligence / Manufacturer Coverage", "Contract Intelligence / Customer Contracts"}]
    return [
        {
            "dataset_key": dataset.dataset_key,
            "display_name": dataset.display_name,
            "description": dataset.description,
            "required_columns": dataset.required_fields,
            "optional_columns": dataset.optional_fields,
            "accepted_values": dataset.accepted_values,
            "example_rows": list(dataset.example_rows),
            "download_url": f"/api/data-management/templates/{dataset.dataset_key}/download",
            "template_filename": dataset.template_filename,
            "matching_logic": "Use normalized serial number; use manufacturer when duplicate serials exist; never match by model alone.",
            "validation_rules": [field.validation_rule for field in dataset.fields if field.validation_rule],
        }
        for dataset in datasets
    ]


@router.get("/reconciliation")
def reconciliation(db: Session = Depends(get_db)):
    service = ServiceIntelligenceService(db)
    return {"items": service.reconciliation_items(), "actions": ["link_existing_record", "create_missing_client", "create_missing_site", "create_missing_equipment", "ignore_with_reason", "correct_imported_value", "rerun_validation"]}


@router.get("/opportunities")
def opportunities(
    filters: dict[str, Any] = Depends(_filters),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = ServiceIntelligenceService(db).opportunity_rows(filters)
    start = (page - 1) * page_size
    return {"items": rows[start : start + page_size], "total": len(rows), "page": page, "page_size": page_size}


@router.get("/opportunities/{opportunity_id}")
def opportunity_detail(opportunity_id: int, db: Session = Depends(get_db)):
    rows = ServiceIntelligenceService(db).opportunity_rows({})
    for row in rows:
        if row["id"] == opportunity_id:
            return row
    raise HTTPException(status_code=404, detail="Opportunity not found")


@router.get("/clients/{client_id}/summary")
def client_intelligence_summary(client_id: int, db: Session = Depends(get_db)):
    return ServiceIntelligenceService(db).client_summary(client_id)


@router.get("/equipment/{equipment_id}/summary")
def equipment_intelligence_summary(equipment_id: int, db: Session = Depends(get_db)):
    summary = ServiceIntelligenceService(db).equipment_summary(equipment_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return summary


@router.post("/refresh")
def refresh(request: Request, equipment_id: int | None = None, db: Session = Depends(get_db)):
    result = ServiceIntelligenceService(db).refresh(equipment_id)
    db.add(
        AuditEvent(
            event_type="service_intelligence.refresh",
            entity_type="service_intelligence",
            entity_id=str(equipment_id) if equipment_id else None,
            new_values=result,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
    )
    db.commit()
    return result


@router.patch("/opportunities/{opportunity_id}")
def patch_opportunity(opportunity_id: int, payload: OpportunityPatch, request: Request, db: Session = Depends(get_db)):
    opportunity = db.query(ServiceOpportunity).filter(ServiceOpportunity.id == opportunity_id).first()
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    before = {
        "status": opportunity.status,
        "assigned_to_user_id": opportunity.assigned_to_user_id,
        "notes": opportunity.notes,
        "quote_id": opportunity.quote_id,
        "lost_reason": opportunity.lost_reason,
    }
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(opportunity, key, value)
    db.add(
        AuditEvent(
            event_type="service_opportunity.update",
            entity_type="service_opportunity",
            entity_id=str(opportunity_id),
            old_values=before,
            new_values=updates,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    db.commit()
    db.refresh(opportunity)
    return {"id": opportunity.id, "status": opportunity.status}


@router.get("/export")
def export_opportunities(filters: dict[str, Any] = Depends(_filters), db: Session = Depends(get_db)):
    rows = ServiceIntelligenceService(db).opportunity_rows(filters)
    columns = [
        "domain",
        "client",
        "site",
        "manufacturer",
        "equipment",
        "model",
        "serial_number",
        "warranty_end_date",
        "warranty_status",
        "contract_reference",
        "contract_end_date",
        "pm_status",
        "opportunity_type",
        "score",
        "priority",
        "opportunity_status",
        "assigned_to_user_id",
        "recommended_next_action",
        "notes",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    content = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    headers = {"Content-Disposition": 'attachment; filename="service_intelligence_opportunities.csv"'}
    return StreamingResponse(content, media_type="text/csv", headers=headers)
