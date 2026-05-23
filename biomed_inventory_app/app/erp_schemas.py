from __future__ import annotations
from datetime import date as dt_date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ERPBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClientIn(ERPBase):
    name: str
    location: str | None = None
    address: str | None = None
    status: str = "active"
    financial_status: str = "good_standing"


class ClientOut(ClientIn):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DepartmentIn(ERPBase):
    client_id: int
    name: str
    floor_location: str | None = None
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class ContactIn(ERPBase):
    client_id: int
    department_id: int | None = None
    name: str
    title: str | None = None
    phone: str | None = None
    email: str | None = None
    notes: str | None = None


class CaseIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_id: int | None = None
    parent_case_reference: str
    case_type: str
    title: str
    description: str | None = None
    status: str = "open"
    priority: str = "normal"
    blocked_reason: str | None = None
    responsible_user_id: int | None = None


class CaseItemIn(ERPBase):
    case_id: int
    item_type: str
    description: str | None = None
    requested_qty: int = 1
    unit_price: Decimal = Decimal("0")
    status: str = "open"
    procurement_status: str = "not_ordered"
    inventory_item_id: int | None = None


class ClientActivityIn(ERPBase):
    client_id: int
    department_id: int | None = None
    case_id: int | None = None
    activity_type: str = Field(pattern="^(sales|after_sales|client_operations)$")
    title: str
    description: str | None = None
    status: str = "open"
    date: dt_date | None = None
    created_by: int | None = None


class EquipmentIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_model_id: int | None = None
    name: str
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    asset_tag: str | None = None
    installation_date: dt_date | None = None
    warranty_start_date: dt_date | None = None
    warranty_end_date: dt_date | None = None
    status: str = "active"
    risk_classification: str | None = None
    life_support: bool = False
    pm_frequency: str | None = None
    last_pm_date: dt_date | None = None
    next_pm_date: dt_date | None = None
    calibration_required: bool = False
    calibration_due_date: dt_date | None = None


class InventoryItemIn(ERPBase):
    pn: str
    description: str | None = None
    category: str = Field(default="spare_part", pattern="^(spare_part|accessory|equipment|consumable)$")
    manufacturer: str | None = None
    minimum_qty: int = 0
    physical_qty: int = 0
    reserved_qty: int = 0
    available_qty: int = 0
    location: str | None = None
    status: str = "active"


class ProcurementRequestIn(ERPBase):
    case_id: int | None = None
    case_item_id: int | None = None
    inventory_item_id: int | None = None
    requested_qty: int = 0
    shortage_qty: int = 0
    procurement_status: str = "not_ordered"
    supplier: str | None = None
    expected_date: dt_date | None = None


class ServiceCallIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_id: int | None = None
    case_id: int | None = None
    call_type: str
    priority: str = "normal"
    status: str = "open"
    blocked_reason: str | None = None
    assigned_engineer_id: int | None = None
    request_date: dt_date | None = None
    due_date: dt_date | None = None


class PMTaskIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_id: int | None = None
    contract_id: int | None = None
    case_id: int | None = None
    scheduled_date: dt_date | None = None
    completed_date: dt_date | None = None
    status: str = "scheduled"
    assigned_engineer_id: int | None = None


class ContractIn(ERPBase):
    client_id: int
    contract_type: str
    start_date: dt_date | None = None
    end_date: dt_date | None = None
    status: str = "active"
    coverage_notes: str | None = None


class WarrantyIn(ERPBase):
    equipment_id: int
    client_id: int
    start_date: dt_date | None = None
    end_date: dt_date | None = None
    status: str = "active"
    coverage_notes: str | None = None


class InvoiceIn(ERPBase):
    client_id: int
    case_id: int | None = None
    parent_case_reference: str | None = None
    invoice_number: str
    status: str = "draft"
    total_amount: Decimal = Decimal("0")
    due_date: dt_date | None = None
    paid_date: dt_date | None = None


class ERPRecordOut(ERPBase):
    id: int
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)
