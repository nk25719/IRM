from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.erp_models import (
    Case,
    Client,
    ContractPMCommitment,
    CustomerContractEquipment,
    CustomerServiceContract,
    Equipment,
    EquipmentModel,
    ManufacturerAgreement,
    ManufacturerAgreementEquipment,
    PMTask,
    ServiceCall,
    ServiceOpportunity,
)
from app.models.foundation import ClientSite, DataValidationError, ImportBatch, ImportRow, Manufacturer

LIFECYCLE_CONTRACTED = "CONTRACTED"
LIFECYCLE_UNDER_WARRANTY = "UNDER_WARRANTY_NOT_CONTRACTED"
LIFECYCLE_EXPIRING = "WARRANTY_EXPIRING_SOON_NOT_CONTRACTED"
LIFECYCLE_EXPIRED = "OUT_OF_WARRANTY_NOT_CONTRACTED"
LIFECYCLE_UNKNOWN = "WARRANTY_UNKNOWN_NOT_CONTRACTED"

OPEN_STATUSES = {"NEW", "REVIEWED", "ASSIGNED", "CONTACTED", "QUOTE_REQUESTED", "QUOTE_SENT"}
TERMINAL_STATUSES = {"WON", "LOST"}
INACTIVE_STATUSES = {"DISMISSED"}
ACTIVE_CONTRACT_STATUSES = {"active", "in force", "current", "valid"}
COMPLETED_PM_STATUSES = {"completed", "done", "closed"}
CORRECTIVE_CASE_TYPES = {"corrective", "corrective_maintenance", "repair", "service", "breakdown"}
MANUFACTURER_OPPORTUNITY_TYPES = {
    "ADD_TO_MANUFACTURER_COVERAGE",
    "MANUFACTURER_AGREEMENT_RENEWAL",
    "MANUFACTURER_WARRANTY_EXPIRING",
    "MANUFACTURER_COVERAGE_EXPIRED",
    "EOSL_REVIEW",
}
CUSTOMER_OPPORTUNITY_TYPES = {
    "NEW_SERVICE_CONTRACT",
    "PM_CONTRACT",
    "LABOR_CONTRACT",
    "FULL_SERVICE_CONTRACT",
    "CUSTOMER_CONTRACT_RENEWAL",
    "COVERAGE_UPGRADE",
}


def opportunity_domain(opportunity_type: str | None) -> str:
    return "Manufacturer" if opportunity_type in MANUFACTURER_OPPORTUNITY_TYPES else "Customer"


@dataclass
class EquipmentEvaluation:
    equipment: Equipment
    lifecycle_status: str
    score: int
    priority: str
    opportunity_type: str
    warranty_end_date: date | None
    active_contract: CustomerServiceContract | None
    pm_overdue: bool
    latest_pm_date: date | None
    next_pm_date: date | None
    open_corrective_cases: int
    corrective_cases_12m: int
    recommended_next_action: str
    score_reasons: list[str] = field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def today_in_app_timezone() -> date:
    return utcnow().date()


def normalize_serial(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    return re.sub(r"\s+", "", raw)


class ServiceIntelligenceService:
    def __init__(self, db: Session, today: date | None = None):
        self.db = db
        self.today = today or today_in_app_timezone()

    def active_contract_for(self, equipment: Equipment) -> CustomerServiceContract | None:
        query = (
            self.db.query(CustomerServiceContract)
            .outerjoin(CustomerContractEquipment, CustomerContractEquipment.customer_service_contract_id == CustomerServiceContract.id)
            .filter(CustomerServiceContract.client_id == equipment.client_id)
            .filter(or_(CustomerContractEquipment.equipment_id == equipment.id, CustomerContractEquipment.id.is_(None)))
            .filter(or_(CustomerServiceContract.status.is_(None), func.lower(CustomerServiceContract.status).in_(ACTIVE_CONTRACT_STATUSES)))
            .filter(or_(CustomerServiceContract.start_date.is_(None), CustomerServiceContract.start_date <= self.today))
            .filter(or_(CustomerServiceContract.end_date.is_(None), CustomerServiceContract.end_date >= self.today))
            .order_by(CustomerServiceContract.end_date.desc().nullslast(), CustomerServiceContract.id.desc())
        )
        return query.first()

    def manufacturer_coverage_for(self, equipment: Equipment) -> tuple[ManufacturerAgreement | None, ManufacturerAgreementEquipment | None]:
        serial_key = normalize_serial(equipment.serial_number)
        row = (
            self.db.query(ManufacturerAgreement, ManufacturerAgreementEquipment)
            .join(ManufacturerAgreementEquipment, ManufacturerAgreementEquipment.manufacturer_agreement_id == ManufacturerAgreement.id)
            .filter(or_(ManufacturerAgreementEquipment.equipment_id == equipment.id, func.upper(func.replace(func.trim(ManufacturerAgreementEquipment.serial_number), " ", "")) == serial_key))
            .order_by(ManufacturerAgreementEquipment.coverage_end_date.desc().nullslast(), ManufacturerAgreementEquipment.id.desc())
            .first()
        )
        return row if row else (None, None)

    def manufacturer_opportunity_type(self, equipment: Equipment) -> str | None:
        _agreement, coverage = self.manufacturer_coverage_for(equipment)
        if not coverage:
            return "ADD_TO_MANUFACTURER_COVERAGE"
        if coverage.eosl_date and coverage.eosl_date <= self.today + timedelta(days=365):
            return "EOSL_REVIEW"
        if coverage.coverage_end_date and coverage.coverage_end_date < self.today:
            return "MANUFACTURER_COVERAGE_EXPIRED"
        if coverage.coverage_end_date and coverage.coverage_end_date <= self.today + timedelta(days=180):
            return "MANUFACTURER_AGREEMENT_RENEWAL"
        if coverage.manufacturer_warranty_end_date and self.today <= coverage.manufacturer_warranty_end_date <= self.today + timedelta(days=180):
            return "MANUFACTURER_WARRANTY_EXPIRING"
        return None

    def manufacturer_score(self, equipment: Equipment, opportunity_type: str) -> int:
        _agreement, coverage = self.manufacturer_coverage_for(equipment)
        if opportunity_type == "ADD_TO_MANUFACTURER_COVERAGE":
            return 70
        if opportunity_type == "MANUFACTURER_COVERAGE_EXPIRED":
            return 85
        if opportunity_type == "EOSL_REVIEW":
            return 80
        if opportunity_type == "MANUFACTURER_AGREEMENT_RENEWAL":
            return 65
        if opportunity_type == "MANUFACTURER_WARRANTY_EXPIRING":
            return 55
        return 40

    def manufacturer_lifecycle_status(self, equipment: Equipment, opportunity_type: str) -> str:
        _agreement, coverage = self.manufacturer_coverage_for(equipment)
        if not coverage:
            return "MANUFACTURER_NOT_COVERED"
        if opportunity_type == "MANUFACTURER_COVERAGE_EXPIRED":
            return "MANUFACTURER_COVERAGE_EXPIRED"
        if opportunity_type == "EOSL_REVIEW":
            return "EOSL_REVIEW"
        if opportunity_type == "MANUFACTURER_AGREEMENT_RENEWAL":
            return "MANUFACTURER_COVERAGE_EXPIRING"
        if opportunity_type == "MANUFACTURER_WARRANTY_EXPIRING":
            return "MANUFACTURER_WARRANTY_EXPIRING"
        return "MANUFACTURER_COVERED"

    def classify(self, equipment: Equipment, active_contract: CustomerServiceContract | None = None) -> str:
        contract = active_contract if active_contract is not None else self.active_contract_for(equipment)
        if contract:
            return LIFECYCLE_CONTRACTED
        warranty_end = equipment.warranty_end_date
        if not warranty_end:
            return LIFECYCLE_UNKNOWN
        if warranty_end < self.today:
            return LIFECYCLE_EXPIRED
        if warranty_end <= self.today + timedelta(days=180):
            return LIFECYCLE_EXPIRING
        return LIFECYCLE_UNDER_WARRANTY

    def _pm_status(self, equipment: Equipment) -> tuple[bool, date | None, date | None, bool]:
        latest_completed = (
            self.db.query(func.max(PMTask.completed_date))
            .filter(PMTask.equipment_id == equipment.id)
            .filter(func.lower(PMTask.status).in_(COMPLETED_PM_STATUSES))
            .scalar()
        )
        latest = latest_completed or equipment.last_pm_date
        next_due = (
            self.db.query(func.min(PMTask.scheduled_date))
            .filter(PMTask.equipment_id == equipment.id)
            .filter(PMTask.completed_date.is_(None))
            .filter(PMTask.scheduled_date.isnot(None))
            .scalar()
        ) or equipment.next_pm_date
        overdue = bool(next_due and next_due < self.today)
        has_completed_12m = bool(latest and latest >= self.today - timedelta(days=365))
        return overdue, latest, next_due, has_completed_12m

    def _corrective_counts(self, equipment: Equipment) -> tuple[int, int]:
        open_cases = (
            self.db.query(func.count(Case.id))
            .filter(Case.equipment_id == equipment.id)
            .filter(func.lower(Case.case_type).in_(CORRECTIVE_CASE_TYPES))
            .filter(~func.lower(Case.status).in_(["closed", "completed", "resolved", "cancelled"]))
            .scalar()
            or 0
        )
        open_calls = (
            self.db.query(func.count(ServiceCall.id))
            .filter(ServiceCall.equipment_id == equipment.id)
            .filter(~func.lower(ServiceCall.status).in_(["closed", "completed", "resolved", "cancelled"]))
            .scalar()
            or 0
        )
        cases_12m = (
            self.db.query(func.count(Case.id))
            .filter(Case.equipment_id == equipment.id)
            .filter(func.lower(Case.case_type).in_(CORRECTIVE_CASE_TYPES))
            .filter(or_(Case.created_at.is_(None), Case.created_at >= datetime.combine(self.today - timedelta(days=365), datetime.min.time(), tzinfo=timezone.utc)))
            .scalar()
            or 0
        )
        return int(open_cases + open_calls), int(cases_12m)

    def _equipment_age_gt_8(self, equipment: Equipment) -> bool:
        return bool(equipment.installation_date and equipment.installation_date <= self.today - timedelta(days=365 * 8))

    def evaluate_equipment(self, equipment: Equipment) -> EquipmentEvaluation:
        contract = self.active_contract_for(equipment)
        lifecycle = self.classify(equipment, contract)
        pm_overdue, latest_pm, next_pm, has_completed_12m = self._pm_status(equipment)
        open_corrective, corrective_12m = self._corrective_counts(equipment)
        score = 0
        reasons: list[str] = []
        if not contract:
            score += 35
            reasons.append("No active service contract")
        warranty_end = equipment.warranty_end_date
        if lifecycle == LIFECYCLE_EXPIRED:
            score += 40
            reasons.append("Warranty expired")
        elif warranty_end and self.today <= warranty_end <= self.today + timedelta(days=90) and not contract:
            score += 30
            reasons.append("Warranty expires within 90 days")
        elif warranty_end and self.today + timedelta(days=91) <= warranty_end <= self.today + timedelta(days=180) and not contract:
            score += 20
            reasons.append("Warranty expires within 180 days")
        elif lifecycle == LIFECYCLE_UNKNOWN:
            score += 10
            reasons.append("Warranty unknown")
        if pm_overdue:
            score += 15
            reasons.append("Preventive maintenance overdue")
        if not has_completed_12m:
            score += 10
            reasons.append("No completed PM within 12 months")
        if open_corrective:
            score += 10
            reasons.append("Open corrective-maintenance case")
        if corrective_12m > 2:
            score += 15
            reasons.append("More than two corrective cases in 12 months")
        if self._equipment_age_gt_8(equipment):
            score += 10
            reasons.append("Equipment age greater than eight years")
        priority = "HIGH" if score >= 80 else "MEDIUM" if score >= 50 else "LOW"
        opportunity_type = "CUSTOMER_CONTRACT_RENEWAL" if contract and contract.end_date and contract.end_date <= self.today + timedelta(days=180) else "NEW_SERVICE_CONTRACT"
        return EquipmentEvaluation(
            equipment=equipment,
            lifecycle_status=lifecycle,
            score=score,
            priority=priority,
            opportunity_type=opportunity_type,
            warranty_end_date=warranty_end,
            active_contract=contract,
            pm_overdue=pm_overdue,
            latest_pm_date=latest_pm,
            next_pm_date=next_pm,
            open_corrective_cases=open_corrective,
            corrective_cases_12m=corrective_12m,
            recommended_next_action=self.recommended_next_action(lifecycle, priority, pm_overdue),
            score_reasons=reasons,
        )

    def recommended_next_action(self, lifecycle: str, priority: str, pm_overdue: bool) -> str:
        if lifecycle == LIFECYCLE_CONTRACTED:
            return "Review renewal timing and keep coverage reference current"
        if priority == "HIGH":
            return "Contact client and prepare service contract proposal"
        if lifecycle == LIFECYCLE_EXPIRING:
            return "Schedule warranty-expiry outreach"
        if pm_overdue:
            return "Bundle PM follow-up with contract coverage discussion"
        if lifecycle == LIFECYCLE_UNKNOWN:
            return "Verify warranty and contract details"
        return "Review coverage and qualify service opportunity"

    def refresh(self, equipment_id: int | None = None) -> dict[str, Any]:
        summary = {"equipment_evaluated": 0, "opportunities_created": 0, "opportunities_updated": 0, "opportunities_closed": 0, "errors": []}
        query = self.db.query(Equipment)
        if equipment_id:
            query = query.filter(Equipment.id == equipment_id)
        now = utcnow()
        for equipment in query.order_by(Equipment.id).all():
            try:
                summary["equipment_evaluated"] += 1
                evaluation = self.evaluate_equipment(equipment)
                desired: dict[str, dict[str, Any]] = {}
                customer_applicable = evaluation.lifecycle_status != LIFECYCLE_CONTRACTED or evaluation.opportunity_type == "CUSTOMER_CONTRACT_RENEWAL"
                if customer_applicable:
                    desired[evaluation.opportunity_type] = {
                        "client_id": equipment.client_id,
                        "lifecycle_status": evaluation.lifecycle_status,
                        "priority": evaluation.priority,
                        "score": evaluation.score,
                        "warranty_end_date": evaluation.warranty_end_date,
                        "contract_id": evaluation.active_contract.id if evaluation.active_contract else None,
                        "last_evaluated_at": now,
                    }
                manufacturer_type = self.manufacturer_opportunity_type(equipment)
                if manufacturer_type:
                    manufacturer_score = self.manufacturer_score(equipment, manufacturer_type)
                    desired[manufacturer_type] = {
                        "client_id": equipment.client_id,
                        "lifecycle_status": self.manufacturer_lifecycle_status(equipment, manufacturer_type),
                        "priority": "HIGH" if manufacturer_score >= 80 else "MEDIUM" if manufacturer_score >= 50 else "LOW",
                        "score": manufacturer_score,
                        "warranty_end_date": None,
                        "contract_id": None,
                        "last_evaluated_at": now,
                    }
                for opportunity in (
                    self.db.query(ServiceOpportunity)
                    .filter(ServiceOpportunity.equipment_id == equipment.id)
                    .filter(ServiceOpportunity.status.in_(OPEN_STATUSES | INACTIVE_STATUSES))
                    .all()
                ):
                    if opportunity.opportunity_type not in desired:
                        opportunity.status = "DISMISSED"
                        opportunity.last_evaluated_at = now
                        summary["opportunities_closed"] += 1
                for opportunity_type, values in desired.items():
                    open_opportunity = (
                        self.db.query(ServiceOpportunity)
                        .filter(ServiceOpportunity.equipment_id == equipment.id)
                        .filter(ServiceOpportunity.opportunity_type == opportunity_type)
                        .filter(ServiceOpportunity.status.in_(OPEN_STATUSES | INACTIVE_STATUSES))
                        .order_by(ServiceOpportunity.id.desc())
                        .first()
                    )
                    if open_opportunity:
                        for key, value in values.items():
                            setattr(open_opportunity, key, value)
                        if open_opportunity.status == "DISMISSED":
                            open_opportunity.status = "NEW"
                        summary["opportunities_updated"] += 1
                    else:
                        self.db.add(ServiceOpportunity(equipment_id=equipment.id, opportunity_type=opportunity_type, status="NEW", detected_at=now, **values))
                        summary["opportunities_created"] += 1
            except Exception as exc:  # pragma: no cover - defensive batch boundary
                summary["errors"].append({"equipment_id": equipment.id, "error": str(exc)})
        self.db.commit()
        return summary

    def opportunity_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        query = (
            self.db.query(ServiceOpportunity, Equipment, Client, CustomerServiceContract, EquipmentModel)
            .join(Equipment, ServiceOpportunity.equipment_id == Equipment.id)
            .join(Client, ServiceOpportunity.client_id == Client.id)
            .outerjoin(CustomerServiceContract, ServiceOpportunity.contract_id == CustomerServiceContract.id)
            .outerjoin(EquipmentModel, Equipment.equipment_model_id == EquipmentModel.id)
        )
        query = self._apply_filters(query, filters)
        return [self._row_payload(op, equipment, client, contract, model) for op, equipment, client, contract, model in query.all()]

    def _apply_filters(self, query, filters: dict[str, Any]):
        if filters.get("client_id"):
            query = query.filter(ServiceOpportunity.client_id == int(filters["client_id"]))
        if filters.get("equipment_id"):
            query = query.filter(ServiceOpportunity.equipment_id == int(filters["equipment_id"]))
        if filters.get("manufacturer"):
            query = query.filter(Equipment.manufacturer.ilike(f"%{filters['manufacturer']}%"))
        if filters.get("model"):
            query = query.filter(Equipment.model.ilike(f"%{filters['model']}%"))
        if filters.get("serial_number"):
            query = query.filter(Equipment.serial_number.ilike(f"%{filters['serial_number']}%"))
        if filters.get("lifecycle_status"):
            query = query.filter(ServiceOpportunity.lifecycle_status == filters["lifecycle_status"])
        if filters.get("opportunity_type"):
            query = query.filter(ServiceOpportunity.opportunity_type == filters["opportunity_type"])
        if filters.get("domain") == "Manufacturer":
            query = query.filter(ServiceOpportunity.opportunity_type.in_(MANUFACTURER_OPPORTUNITY_TYPES))
        if filters.get("domain") == "Customer":
            query = query.filter(ServiceOpportunity.opportunity_type.in_(CUSTOMER_OPPORTUNITY_TYPES))
        if filters.get("status"):
            query = query.filter(ServiceOpportunity.status == filters["status"])
        if filters.get("priority"):
            query = query.filter(ServiceOpportunity.priority == filters["priority"])
        if filters.get("assigned_to_user_id"):
            query = query.filter(ServiceOpportunity.assigned_to_user_id == int(filters["assigned_to_user_id"]))
        if filters.get("minimum_score") is not None:
            query = query.filter(ServiceOpportunity.score >= int(filters["minimum_score"]))
        if filters.get("warranty_end_from"):
            query = query.filter(ServiceOpportunity.warranty_end_date >= filters["warranty_end_from"])
        if filters.get("warranty_end_to"):
            query = query.filter(ServiceOpportunity.warranty_end_date <= filters["warranty_end_to"])
        if filters.get("contract_coverage") == "covered":
            query = query.filter(ServiceOpportunity.contract_id.isnot(None))
        if filters.get("contract_coverage") == "uncovered":
            query = query.filter(ServiceOpportunity.contract_id.is_(None))
        if filters.get("search"):
            term = f"%{filters['search']}%"
            query = query.filter(or_(Client.name.ilike(term), Equipment.name.ilike(term), Equipment.model.ilike(term), Equipment.serial_number.ilike(term), Equipment.manufacturer.ilike(term)))
        sort = filters.get("sort") or "-score"
        order_map = {
            "score": ServiceOpportunity.score,
            "priority": ServiceOpportunity.priority,
            "warranty_end_date": ServiceOpportunity.warranty_end_date,
            "client": Client.name,
            "equipment": Equipment.name,
            "status": ServiceOpportunity.status,
        }
        desc = str(sort).startswith("-")
        column = order_map.get(str(sort).lstrip("-"), ServiceOpportunity.score)
        return query.order_by(column.desc() if desc else column.asc(), ServiceOpportunity.id.desc())

    def _row_payload(self, opportunity: ServiceOpportunity, equipment: Equipment, client: Client, contract: CustomerServiceContract | None, model: EquipmentModel | None = None) -> dict[str, Any]:
        evaluation = self.evaluate_equipment(equipment)
        return {
            "id": opportunity.id,
            "domain": opportunity_domain(opportunity.opportunity_type),
            "priority": opportunity.priority,
            "score": opportunity.score,
            "client_id": client.id,
            "client": client.name,
            "site": "",
            "equipment_id": equipment.id,
            "equipment": equipment.name,
            "manufacturer": equipment.manufacturer or (model.manufacturer if model else None),
            "model": equipment.model or (model.model if model else None),
            "serial_number": equipment.serial_number,
            "warranty_end_date": opportunity.warranty_end_date.isoformat() if opportunity.warranty_end_date else None,
            "warranty_status": opportunity.lifecycle_status,
            "contract_status": "active" if opportunity.contract_id else "not_contracted",
            "contract_id": opportunity.contract_id,
            "contract_reference": contract.contract_number if contract else None,
            "contract_end_date": contract.end_date.isoformat() if contract and contract.end_date else None,
            "pm_status": "overdue" if evaluation.pm_overdue else "current",
            "opportunity_type": opportunity.opportunity_type,
            "opportunity_status": opportunity.status,
            "assigned_to_user_id": opportunity.assigned_to_user_id,
            "recommended_next_action": self.recommended_next_action_for_opportunity(opportunity.opportunity_type, evaluation),
            "notes": opportunity.notes,
        }

    def recommended_next_action_for_opportunity(self, opportunity_type: str, evaluation: EquipmentEvaluation) -> str:
        actions = {
            "ADD_TO_MANUFACTURER_COVERAGE": "Compare installed base with manufacturer coverage and request addendum",
            "MANUFACTURER_AGREEMENT_RENEWAL": "Prepare manufacturer agreement renewal review",
            "MANUFACTURER_WARRANTY_EXPIRING": "Review manufacturer warranty expiry and coverage handoff",
            "MANUFACTURER_COVERAGE_EXPIRED": "Escalate expired manufacturer coverage",
            "EOSL_REVIEW": "Review EOSL risk and replacement or support options",
            "PM_CONTRACT": "Prepare PM contract proposal",
            "LABOR_CONTRACT": "Prepare labor coverage proposal",
            "FULL_SERVICE_CONTRACT": "Prepare full-service coverage proposal",
            "CUSTOMER_CONTRACT_RENEWAL": "Review renewal timing and quotation status",
            "COVERAGE_UPGRADE": "Review customer coverage upgrade options",
        }
        return actions.get(opportunity_type, evaluation.recommended_next_action)

    def summary(self) -> dict[str, Any]:
        equipment = self.db.query(Equipment).all()
        evaluations = [self.evaluate_equipment(row) for row in equipment]
        total = len(evaluations)
        contracted = sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_CONTRACTED)
        manufacturer_coverages = [self.manufacturer_coverage_for(row)[1] for row in equipment]
        covered_by_manufacturer = sum(1 for row in manufacturer_coverages if row)
        manufacturer_warranty_active = sum(1 for row in manufacturer_coverages if row and row.manufacturer_warranty_end_date and row.manufacturer_warranty_end_date >= self.today)
        manufacturer_warranty_expiring = sum(1 for row in manufacturer_coverages if row and row.manufacturer_warranty_end_date and self.today <= row.manufacturer_warranty_end_date <= self.today + timedelta(days=180))
        manufacturer_agreements_expiring = sum(1 for row in manufacturer_coverages if row and row.coverage_end_date and self.today <= row.coverage_end_date <= self.today + timedelta(days=180))
        customer_contracts = self.db.query(CustomerServiceContract).all()
        open_count = self.db.query(func.count(ServiceOpportunity.id)).filter(ServiceOpportunity.status.in_(OPEN_STATUSES)).scalar() or 0
        high_count = self.db.query(func.count(ServiceOpportunity.id)).filter(ServiceOpportunity.priority == "HIGH", ServiceOpportunity.status.in_(OPEN_STATUSES)).scalar() or 0
        won_count = self.db.query(func.count(ServiceOpportunity.id)).filter(ServiceOpportunity.status == "WON").scalar() or 0
        by_client: dict[str, dict[str, Any]] = {}
        by_model: dict[str, dict[str, Any]] = {}
        clients = {client.id: client.name for client in self.db.query(Client).all()}
        for evaluation in evaluations:
            client_name = clients.get(evaluation.equipment.client_id, "Unknown")
            client_bucket = by_client.setdefault(client_name, {"client": client_name, "total_installed": 0, "contracted": 0, "uncovered": 0, "contract_coverage_percentage": 0, "high_priority_opportunities": 0})
            model_key = evaluation.equipment.model or evaluation.equipment.name or "Unknown"
            model_bucket = by_model.setdefault(model_key, {"model_or_category": model_key, "installed_count": 0, "contracted_count": 0, "uncovered_count": 0, "expiring_warranty_count": 0, "expired_warranty_count": 0})
            client_bucket["total_installed"] += 1
            model_bucket["installed_count"] += 1
            if evaluation.lifecycle_status == LIFECYCLE_CONTRACTED:
                client_bucket["contracted"] += 1
                model_bucket["contracted_count"] += 1
            else:
                client_bucket["uncovered"] += 1
                model_bucket["uncovered_count"] += 1
            if evaluation.priority == "HIGH":
                client_bucket["high_priority_opportunities"] += 1
            if evaluation.lifecycle_status == LIFECYCLE_EXPIRING:
                model_bucket["expiring_warranty_count"] += 1
            if evaluation.lifecycle_status == LIFECYCLE_EXPIRED:
                model_bucket["expired_warranty_count"] += 1
        for bucket in by_client.values():
            bucket["contract_coverage_percentage"] = round((bucket["contracted"] / bucket["total_installed"] * 100), 1) if bucket["total_installed"] else 0
        return {
            "total_installed_equipment": total,
            "active_contracted_equipment": contracted,
            "contract_coverage_percentage": round((contracted / total * 100), 1) if total else 0,
            "under_warranty_equipment_without_contract": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_UNDER_WARRANTY),
            "warranties_expiring_within_90_days": sum(1 for row in evaluations if row.warranty_end_date and self.today <= row.warranty_end_date <= self.today + timedelta(days=90) and row.lifecycle_status != LIFECYCLE_CONTRACTED),
            "warranties_expiring_within_180_days": sum(1 for row in evaluations if row.warranty_end_date and self.today <= row.warranty_end_date <= self.today + timedelta(days=180) and row.lifecycle_status != LIFECYCLE_CONTRACTED),
            "out_of_warranty_equipment_without_contract": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_EXPIRED),
            "warranty_unknown_equipment_without_contract": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_UNKNOWN),
            "open_opportunities": int(open_count),
            "high_priority_opportunities": int(high_count),
            "won_opportunities": int(won_count),
            "manufacturer_covered_equipment": covered_by_manufacturer,
            "manufacturer_uncovered_equipment": max(0, total - covered_by_manufacturer),
            "manufacturer_warranty_active": manufacturer_warranty_active,
            "manufacturer_warranty_expiring": manufacturer_warranty_expiring,
            "manufacturer_agreements_expiring": manufacturer_agreements_expiring,
            "active_customer_contracts": sum(1 for row in customer_contracts if (row.status or "").casefold() in ACTIVE_CONTRACT_STATUSES),
            "pm_contracts": sum(1 for row in customer_contracts if (row.pm_visits_per_year or 0) > 0),
            "labor_contracts": sum(1 for row in customer_contracts if row.labor_included),
            "customer_contracts_expiring": sum(1 for row in customer_contracts if row.end_date and self.today <= row.end_date <= self.today + timedelta(days=180)),
            "customer_renewal_opportunities": self.db.query(func.count(ServiceOpportunity.id)).filter(ServiceOpportunity.opportunity_type == "CUSTOMER_CONTRACT_RENEWAL", ServiceOpportunity.status.in_(OPEN_STATUSES)).scalar() or 0,
            "opportunities_by_client": sorted(by_client.values(), key=lambda row: row["high_priority_opportunities"], reverse=True),
            "opportunities_by_model_or_category": sorted(by_model.values(), key=lambda row: row["uncovered_count"], reverse=True),
        }

    def client_summary(self, client_id: int) -> dict[str, Any]:
        evaluations = [self.evaluate_equipment(row) for row in self.db.query(Equipment).filter(Equipment.client_id == client_id).all()]
        open_opportunities = (
            self.db.query(func.count(ServiceOpportunity.id))
            .filter(ServiceOpportunity.client_id == client_id, ServiceOpportunity.status.in_(OPEN_STATUSES))
            .scalar()
            or 0
        )
        high_opportunities = (
            self.db.query(func.count(ServiceOpportunity.id))
            .filter(ServiceOpportunity.client_id == client_id, ServiceOpportunity.priority == "HIGH", ServiceOpportunity.status.in_(OPEN_STATUSES))
            .scalar()
            or 0
        )
        return {
            "client_id": client_id,
            "total_installed_equipment": len(evaluations),
            "contracted_equipment": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_CONTRACTED),
            "uncovered_equipment": sum(1 for row in evaluations if row.lifecycle_status != LIFECYCLE_CONTRACTED),
            "active_warranty_without_contract": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_UNDER_WARRANTY),
            "expiring_warranties": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_EXPIRING),
            "expired_warranties_without_contract": sum(1 for row in evaluations if row.lifecycle_status == LIFECYCLE_EXPIRED),
            "open_opportunities": int(open_opportunities),
            "high_priority_opportunities": int(high_opportunities),
        }

    def equipment_summary(self, equipment_id: int) -> dict[str, Any] | None:
        equipment = self.db.query(Equipment).filter(Equipment.id == equipment_id).first()
        if not equipment:
            return None
        evaluation = self.evaluate_equipment(equipment)
        opportunity = (
            self.db.query(ServiceOpportunity)
            .filter(ServiceOpportunity.equipment_id == equipment_id, ServiceOpportunity.status.in_(OPEN_STATUSES))
            .order_by(ServiceOpportunity.score.desc(), ServiceOpportunity.id.desc())
            .first()
        )
        contract = evaluation.active_contract
        manufacturer_agreement, manufacturer_equipment = self.manufacturer_coverage_for(equipment)
        pm_commitment = None
        if contract:
            pm_commitment = (
                self.db.query(ContractPMCommitment)
                .filter(ContractPMCommitment.customer_service_contract_id == contract.id)
                .filter(or_(ContractPMCommitment.equipment_id == equipment_id, ContractPMCommitment.equipment_id.is_(None)))
                .order_by(ContractPMCommitment.equipment_id.desc().nullslast(), ContractPMCommitment.id.desc())
                .first()
            )
        return {
            "equipment_id": equipment_id,
            "manufacturer_coverage": {
                "manufacturer": manufacturer_agreement.manufacturer if manufacturer_agreement else equipment.manufacturer,
                "agreement_id": manufacturer_agreement.id if manufacturer_agreement else None,
                "agreement_number": manufacturer_agreement.agreement_number if manufacturer_agreement else None,
                "coverage_status": manufacturer_equipment.coverage_status if manufacturer_equipment else "not_covered",
                "coverage_start_date": manufacturer_equipment.coverage_start_date.isoformat() if manufacturer_equipment and manufacturer_equipment.coverage_start_date else None,
                "coverage_end_date": manufacturer_equipment.coverage_end_date.isoformat() if manufacturer_equipment and manufacturer_equipment.coverage_end_date else None,
                "warranty_status": "active" if manufacturer_equipment and manufacturer_equipment.manufacturer_warranty_end_date and manufacturer_equipment.manufacturer_warranty_end_date >= self.today else "unknown" if not manufacturer_equipment or not manufacturer_equipment.manufacturer_warranty_end_date else "expired",
                "warranty_end_date": manufacturer_equipment.manufacturer_warranty_end_date.isoformat() if manufacturer_equipment and manufacturer_equipment.manufacturer_warranty_end_date else None,
                "eosl_date": manufacturer_equipment.eosl_date.isoformat() if manufacturer_equipment and manufacturer_equipment.eosl_date else None,
                "manufacturer_renewal_opportunity": "MANUFACTURER_AGREEMENT_RENEWAL" if manufacturer_equipment and manufacturer_equipment.coverage_end_date and manufacturer_equipment.coverage_end_date <= self.today + timedelta(days=180) else None,
            },
            "customer_service_contract": {
                "customer": equipment.client_id,
                "contract_id": contract.id if contract else None,
                "contract_number": contract.contract_number if contract else None,
                "contract_status": contract.status if contract else "not_contracted",
                "coverage_type": contract.coverage_type if contract else None,
                "contract_start_date": contract.start_date.isoformat() if contract and contract.start_date else None,
                "contract_end_date": contract.end_date.isoformat() if contract and contract.end_date else None,
                "pm_visits_per_year": contract.pm_visits_per_year if contract else None,
                "pm_visits_completed": pm_commitment.completed_visits_year_to_date if pm_commitment else 0,
                "pm_commitment_status": pm_commitment.commitment_status if pm_commitment else "not_committed",
                "labor_included": contract.labor_included if contract else False,
                "parts_included": contract.parts_included if contract else False,
                "quotation_id": contract.quotation_id if contract else None,
                "customer_renewal_opportunity": "CUSTOMER_CONTRACT_RENEWAL" if contract and contract.end_date and contract.end_date <= self.today + timedelta(days=180) else None,
            },
            "warranty_status": evaluation.lifecycle_status,
            "warranty_end_date": equipment.warranty_end_date.isoformat() if equipment.warranty_end_date else None,
            "active_contract_status": "active" if contract else "not_contracted",
            "contract_id": contract.id if contract else None,
            "contract_reference": contract.contract_number if contract else None,
            "contract_start_date": contract.start_date.isoformat() if contract and contract.start_date else None,
            "contract_end_date": contract.end_date.isoformat() if contract and contract.end_date else None,
            "latest_pm_date": evaluation.latest_pm_date.isoformat() if evaluation.latest_pm_date else None,
            "next_pm_date": evaluation.next_pm_date.isoformat() if evaluation.next_pm_date else None,
            "pm_status": "overdue" if evaluation.pm_overdue else "current",
            "open_corrective_cases": evaluation.open_corrective_cases,
            "current_opportunity_id": opportunity.id if opportunity else None,
            "opportunity_priority": opportunity.priority if opportunity else None,
            "opportunity_score": opportunity.score if opportunity else None,
            "recommended_next_action": evaluation.recommended_next_action,
        }

    def reconciliation_items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        duplicate_serials = (
            self.db.query(Equipment.serial_number, func.count(Equipment.id))
            .filter(Equipment.serial_number.isnot(None), func.trim(Equipment.serial_number) != "")
            .group_by(func.upper(func.replace(func.trim(Equipment.serial_number), " ", "")))
            .having(func.count(Equipment.id) > 1)
            .all()
        )
        for serial, count in duplicate_serials:
            items.append({"issue_type": "duplicate_serial_numbers", "severity": "warning", "reference": serial, "detail": f"{count} equipment records share this normalized serial.", "recommended_action": "Review manufacturer/client and link the correct serial to contract rows."})
        for equipment in self.db.query(Equipment).filter(or_(Equipment.client_id.is_(None), Equipment.serial_number.is_(None), func.trim(Equipment.serial_number) == "")).limit(100):
            items.append({"issue_type": "equipment_missing_required_reference", "severity": "error", "reference": equipment.id, "detail": "Equipment is missing client or serial number.", "recommended_action": "Correct imported value or link to an existing record."})
        for equipment in self.db.query(Equipment).filter(Equipment.warranty_start_date.isnot(None), Equipment.warranty_end_date.isnot(None), Equipment.warranty_end_date < Equipment.warranty_start_date).limit(100):
            items.append({"issue_type": "invalid_warranty_dates", "severity": "error", "reference": equipment.serial_number or equipment.id, "detail": "Warranty end date is before warranty start date.", "recommended_action": "Correct warranty dates and re-run validation."})
        for contract in self.db.query(CustomerServiceContract).filter(CustomerServiceContract.start_date.isnot(None), CustomerServiceContract.end_date.isnot(None), CustomerServiceContract.end_date < CustomerServiceContract.start_date).limit(100):
            items.append({"issue_type": "active_customer_contract_invalid_dates", "severity": "error", "reference": contract.contract_number or contract.id, "detail": "Customer contract end date is before contract start date.", "recommended_action": "Correct customer contract coverage dates."})
        for agreement in self.db.query(ManufacturerAgreement).filter(ManufacturerAgreement.start_date.isnot(None), ManufacturerAgreement.end_date.isnot(None), ManufacturerAgreement.end_date < ManufacturerAgreement.start_date).limit(100):
            items.append({"issue_type": "manufacturer_agreement_invalid_dates", "severity": "error", "reference": agreement.agreement_number or agreement.id, "detail": "Manufacturer agreement end date is before agreement start date.", "recommended_action": "Correct manufacturer agreement coverage dates."})
        known_manufacturers = {row[0].casefold() for row in self.db.query(Manufacturer.name).all() if row[0]}
        if known_manufacturers:
            for manufacturer, count in self.db.query(Equipment.manufacturer, func.count(Equipment.id)).filter(Equipment.manufacturer.isnot(None), func.trim(Equipment.manufacturer) != "").group_by(Equipment.manufacturer).all():
                if manufacturer.casefold() not in known_manufacturers:
                    items.append({"issue_type": "inconsistent_manufacturer_names", "severity": "warning", "reference": manufacturer, "detail": f"{count} equipment records use a non-canonical manufacturer name.", "recommended_action": "Map to a verified manufacturer alias."})
        open_errors = (
            self.db.query(DataValidationError, ImportRow, ImportBatch)
            .join(ImportBatch, DataValidationError.import_batch_id == ImportBatch.id)
            .outerjoin(ImportRow, DataValidationError.import_row_id == ImportRow.id)
            .filter(DataValidationError.is_resolved.is_(False), ImportBatch.source_type.like("service_intelligence_%"))
            .limit(100)
            .all()
        )
        for error, row, batch in open_errors:
            items.append({"issue_type": error.error_code, "severity": error.severity, "reference": f"batch {batch.id} row {row.row_number if row else ''}", "detail": error.error_message, "recommended_action": "Review validation error before committing import."})
        return items
