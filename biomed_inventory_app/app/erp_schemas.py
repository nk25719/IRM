from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, ConfigDict


class ERPBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClientIn(ERPBase):
    name: str
    location: str | None = None
    address: str | None = None
    status: str = "active"
    financial_status: str = "good_standing"


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


class UserIn(ERPBase):
    username: str
    full_name: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    active: bool = True


class EngineerIn(ERPBase):
    user_id: int | None = None
    engineer_name: str
    email: str | None = None
    phone: str | None = None
    active: bool = True
    notes: str | None = None


class EquipmentIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_model_id: int | None = None
    name: str
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    asset_tag: str | None = None
    installation_date: DateType | None = None
    warranty_start_date: DateType | None = None
    warranty_end_date: DateType | None = None
    status: str = "active"
    risk_classification: str | None = None
    life_support: bool = False
    pm_frequency: str | None = None
    last_pm_date: DateType | None = None
    next_pm_date: DateType | None = None
    calibration_required: bool = False
    calibration_due_date: DateType | None = None
    mdmanser_serial_number: str | None = None
    mdmanser_report_reference: str | None = None
    mdmanser_source_row_hash: str | None = None


class ContractIn(ERPBase):
    client_id: int
    contract_reference: str | None = None
    contract_type: str = "service_contract"
    start_date: DateType | None = None
    end_date: DateType | None = None
    status: str = "active"
    coverage_notes: str | None = None
    pms_per_year: int | None = None
    pm_pattern: str | None = None
    source: str | None = None


class WarrantyIn(ERPBase):
    equipment_id: int
    client_id: int
    start_date: DateType | None = None
    end_date: DateType | None = None
    status: str = "active"
    coverage_notes: str | None = None


class CaseIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_id: int | None = None
    parent_case_reference: str
    mdmanser_report_number: str | None = None
    case_type: str
    title: str
    description: str | None = None
    status: str = "open"
    priority: str = "normal"
    blocked_reason: str | None = None
    responsible_user_id: int | None = None


class ServiceCallIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_id: int | None = None
    case_id: int | None = None
    mdmanser_report_number: str | None = None
    call_type: str = "service"
    call_type_2: str | None = None
    priority: str = "normal"
    status: str = "open"
    blocked_reason: str | None = None
    assigned_engineer_id: int | None = None
    call_reason: str | None = None
    call_by: str | None = None
    received_by: str | None = None
    request_date: DateType | None = None
    request_time: str | None = None
    visit_date: DateType | None = None
    visit_time: str | None = None
    completed_date: DateType | None = None
    completed_time: str | None = None
    source: str | None = None
    source_row_hash: str | None = None


class PMTaskIn(ERPBase):
    client_id: int
    department_id: int | None = None
    equipment_id: int | None = None
    contract_id: int | None = None
    case_id: int | None = None
    scheduled_date: DateType | None = None
    completed_date: DateType | None = None
    status: str = "scheduled"
    assigned_engineer_id: int | None = None
    pm_label: str | None = None
    communication_stage: str | None = None
    reminder_1_sent: bool = False
    reminder_2_sent: bool = False
    final_reminder_sent: bool = False
    engineer_alert_sent: bool = False
    visit_confirmed_date: DateType | None = None
    overdue: bool = False
    source: str | None = None
    source_row_hash: str | None = None


class InventoryItemIn(ERPBase):
    pn: str
    description: str | None = None
    category: str = "spare_part"
    manufacturer: str | None = None
    minimum_qty: int = 0
    physical_qty: int = 0
    reserved_qty: int = 0
    available_qty: int = 0
    location: str | None = None
    status: str = "active"


class CaseItemIn(ERPBase):
    case_id: int
    item_type: str
    description: str | None = None
    requested_qty: int = 1
    unit_price: float = 0
    status: str = "open"
    procurement_status: str = "not_ordered"
    inventory_item_id: int | None = None


class ProcurementRequestIn(ERPBase):
    case_id: int | None = None
    case_item_id: int | None = None
    inventory_item_id: int | None = None
    requested_qty: int = 0
    shortage_qty: int = 0
    procurement_status: str = "not_ordered"
    supplier: str | None = None
    expected_date: DateType | None = None


class ClientActivityIn(ERPBase):
    client_id: int
    department_id: int | None = None
    case_id: int | None = None
    activity_type: str
    title: str
    description: str | None = None
    status: str = "open"
    date: DateType | None = None
    created_by: int | None = None


class InvoiceIn(ERPBase):
    client_id: int
    case_id: int | None = None
    parent_case_reference: str | None = None
    invoice_number: str
    status: str = "draft"
    total_amount: float = 0
    due_date: DateType | None = None
    paid_date: DateType | None = None


class QuotationItemIn(ERPBase):
    quotation_id: int
    inventory_item_id: int | None = None
    item_code: str | None = None
    manufacturer_part_number: str | None = None
    description: str
    ai_normalized_description: str | None = None
    quantity: float = 1
    unit_price: float = 0
    discount_percent: float = 0
    line_total: float = 0
    warranty: str | None = None
    delivery_time: str | None = None
    ai_match_confidence: float | None = None
    ai_validation_status: str = "missing_info"
    ai_validation_notes: str | None = None


class QuotationIn(ERPBase):
    quotation_number: str | None = None
    quotation_no: str | None = None
    client_id: int | None = None
    department_id: int | None = None
    contact_id: int | None = None
    case_id: int | None = None
    status: str = "draft"
    quotation_date: DateType | None = None
    quote_date: DateType | None = None
    valid_until: DateType | None = None
    currency: str = "USD"
    subtotal: float = 0
    discount_amount: float = 0
    vat_rate: float = 0
    vat_amount: float = 0
    total_amount: float = 0
    amount: float = 0
    payment_terms: str | None = None
    delivery_terms: str | None = None
    warranty_terms: str | None = None
    notes: str | None = None


class QuotationAttachmentIn(ERPBase):
    quotation_id: int
    filename: str
    content_type: str | None = None
    storage_path: str | None = None
    extracted_text: str | None = None


class QuotationTemplateIn(ERPBase):
    name: str
    currency: str = "USD"
    payment_terms: str | None = None
    delivery_terms: str | None = None
    warranty_terms: str | None = None
    notes: str | None = None
    is_default: bool = False
