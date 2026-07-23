from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func

from .database import Base
from .models.mixins import TimestampMixin


class Client(Base, TimestampMixin):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_name", "name"),)
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    address = Column(Text)
    status = Column(String(50), nullable=False, default="active")
    financial_status = Column(String(50), nullable=False, default="good_standing")


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (Index("ix_departments_client_id", "client_id"),)
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    floor_location = Column(String(255))
    contact_name = Column(String(255))
    phone = Column(String(80))
    email = Column(String(255))
    notes = Column(Text)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_client_id", "client_id"), Index("ix_contacts_department_id", "department_id"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    title = Column(String(255))
    phone = Column(String(80))
    email = Column(String(255))
    notes = Column(Text)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False)
    full_name = Column(String(255))
    role = Column(String(80))
    email = Column(String(255))
    phone = Column(String(80))
    active = Column(Boolean, nullable=False, default=True)


class Engineer(Base, TimestampMixin):
    __tablename__ = "engineers"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    engineer_name = Column(String(255), unique=True, nullable=False)
    email = Column(String(255))
    phone = Column(String(80))
    active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text)


class EquipmentModel(Base):
    __tablename__ = "equipment_models"
    __table_args__ = (
        Index("ix_equipment_models_manufacturer_id", "manufacturer_id"),
        Index("ix_equipment_models_equipment_category_id", "equipment_category_id"),
    )
    id = Column(Integer, primary_key=True)
    manufacturer_id = Column(Integer, nullable=True)
    equipment_category_id = Column(Integer, nullable=True)
    manufacturer = Column(String(255))
    model = Column(String(255))


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        Index("ix_equipment_client_id", "client_id"),
        Index("ix_equipment_department_id", "department_id"),
        Index("ix_equipment_serial_number", "serial_number"),
    )
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    equipment_model_id = Column(Integer, ForeignKey("equipment_models.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    manufacturer = Column(String(255))
    model = Column(String(255))
    serial_number = Column(String(255))
    asset_tag = Column(String(255))
    installation_date = Column(Date)
    warranty_start_date = Column(Date)
    warranty_end_date = Column(Date)
    status = Column(String(50), nullable=False, default="active")
    risk_classification = Column(String(80))
    life_support = Column(Boolean, nullable=False, default=False)
    pm_frequency = Column(String(80))
    last_pm_date = Column(Date)
    next_pm_date = Column(Date)
    calibration_required = Column(Boolean, nullable=False, default=False)
    calibration_due_date = Column(Date)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (Index("ix_contracts_client_id", "client_id"), Index("ix_contracts_contract_reference", "contract_reference"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    contract_reference = Column(String(120), unique=True)
    contract_type = Column(String(80), nullable=False, default="service_contract")
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), nullable=False, default="active")
    coverage_notes = Column(Text)
    pms_per_year = Column(Integer)
    pm_pattern = Column(String(120))
    source = Column(String(80))


class Warranty(Base):
    __tablename__ = "warranties"
    __table_args__ = (Index("ix_warranties_equipment_id", "equipment_id"), Index("ix_warranties_client_id", "client_id"))
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), nullable=False, default="active")
    coverage_notes = Column(Text)


class Case(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("parent_case_reference", name="uq_cases_parent_case_reference"),
        Index("ix_cases_client_id", "client_id"),
        Index("ix_cases_department_id", "department_id"),
        Index("ix_cases_parent_case_reference", "parent_case_reference"),
    )
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    parent_case_reference = Column(String(120), nullable=False)
    case_type = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default="open")
    priority = Column(String(50), nullable=False, default="normal")
    blocked_reason = Column(Text)
    responsible_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class ServiceCall(Base):
    __tablename__ = "service_calls"
    __table_args__ = (
        Index("ix_service_calls_client_id", "client_id"),
        Index("ix_service_calls_case_id", "case_id"),
    )
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    call_type = Column(String(120), nullable=False, default="service")
    call_type_2 = Column(String(120))
    priority = Column(String(50), nullable=False, default="normal")
    status = Column(String(50), nullable=False, default="open")
    blocked_reason = Column(Text)
    assigned_engineer_id = Column(Integer, ForeignKey("engineers.id", ondelete="SET NULL"), nullable=True)
    call_reason = Column(Text)
    call_by = Column(String(255))
    received_by = Column(String(255))
    request_date = Column(Date)
    request_time = Column(String(40))
    visit_date = Column(Date)
    visit_time = Column(String(40))
    completed_date = Column(Date)
    completed_time = Column(String(40))
    source = Column(String(80))
    source_row_hash = Column(String(64))


class PMTask(Base):
    __tablename__ = "pm_tasks"
    __table_args__ = (
        Index("ix_pm_tasks_client_id", "client_id"),
        Index("ix_pm_tasks_contract_id", "contract_id"),
        Index("ix_pm_tasks_equipment_id", "equipment_id"),
    )
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    scheduled_date = Column(Date)
    completed_date = Column(Date)
    status = Column(String(50), nullable=False, default="scheduled")
    assigned_engineer_id = Column(Integer, ForeignKey("engineers.id", ondelete="SET NULL"), nullable=True)
    pm_label = Column(String(80))
    communication_stage = Column(String(120))
    reminder_1_sent = Column(Boolean, nullable=False, default=False)
    reminder_2_sent = Column(Boolean, nullable=False, default=False)
    final_reminder_sent = Column(Boolean, nullable=False, default=False)
    engineer_alert_sent = Column(Boolean, nullable=False, default=False)
    visit_confirmed_date = Column(Date)
    overdue = Column(Boolean, nullable=False, default=False)
    source = Column(String(80))
    source_row_hash = Column(String(64))


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (Index("ix_inventory_items_pn", "pn"),)
    id = Column(Integer, primary_key=True)
    pn = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False, default="spare_part")
    manufacturer = Column(String(255))
    minimum_qty = Column(Integer, nullable=False, default=0)
    physical_qty = Column(Integer, nullable=False, default=0)
    reserved_qty = Column(Integer, nullable=False, default=0)
    available_qty = Column(Integer, nullable=False, default=0)
    location = Column(String(255))
    status = Column(String(50), nullable=False, default="active")


class CaseItem(Base):
    __tablename__ = "case_items"
    __table_args__ = (Index("ix_case_items_case_id", "case_id"),)
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    item_type = Column(String(80), nullable=False)
    description = Column(Text)
    requested_qty = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    status = Column(String(50), nullable=False, default="open")
    procurement_status = Column(String(50), nullable=False, default="not_ordered")
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)


class ProcurementRequest(Base):
    __tablename__ = "procurement_requests"
    __table_args__ = (Index("ix_procurement_requests_case_id", "case_id"), Index("ix_procurement_requests_case_item_id", "case_item_id"))
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    case_item_id = Column(Integer, ForeignKey("case_items.id", ondelete="SET NULL"), nullable=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    requested_qty = Column(Integer, nullable=False, default=0)
    shortage_qty = Column(Integer, nullable=False, default=0)
    procurement_status = Column(String(50), nullable=False, default="not_ordered")
    supplier = Column(String(255))
    expected_date = Column(Date)


class ClientActivity(Base):
    __tablename__ = "client_activities"
    __table_args__ = (Index("ix_client_activities_client_id", "client_id"), Index("ix_client_activities_case_id", "case_id"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    activity_type = Column(String(40), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default="open")
    date = Column(Date)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (Index("ix_invoices_client_id", "client_id"), Index("ix_invoices_case_id", "case_id"), Index("ix_invoices_parent_case_reference", "parent_case_reference"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    parent_case_reference = Column(String(120))
    invoice_number = Column(String(120), nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    due_date = Column(Date)
    paid_date = Column(Date)


class Quotation(Base, TimestampMixin):
    __tablename__ = "quotations"
    __table_args__ = (
        Index("ix_quotations_client_id", "client_id"),
        Index("ix_quotations_number", "quotation_number"),
        Index("ix_quotations_status", "status"),
    )
    id = Column(Integer, primary_key=True)
    quotation_number = Column(String(120))
    quotation_no = Column(String(120))
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="draft")
    quotation_date = Column(Date)
    quote_date = Column(Date)
    valid_until = Column(Date)
    currency = Column(String(12), nullable=False, default="USD")
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(12, 2), nullable=False, default=0)
    vat_rate = Column(Numeric(5, 2), nullable=False, default=0)
    vat_amount = Column(Numeric(12, 2), nullable=False, default=0)
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    amount = Column(Numeric(12, 2), nullable=False, default=0)
    payment_terms = Column(Text)
    delivery_terms = Column(Text)
    warranty_terms = Column(Text)
    notes = Column(Text)


class QuotationItem(Base):
    __tablename__ = "quotation_items"
    __table_args__ = (
        Index("ix_quotation_items_quotation_id", "quotation_id"),
        Index("ix_quotation_items_inventory_item_id", "inventory_item_id"),
    )
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True)
    item_code = Column(String(255))
    manufacturer_part_number = Column(String(255))
    description = Column(Text, nullable=False)
    ai_normalized_description = Column(Text)
    quantity = Column(Numeric(12, 2), nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False, default=0)
    discount_percent = Column(Numeric(5, 2), nullable=False, default=0)
    line_total = Column(Numeric(12, 2), nullable=False, default=0)
    warranty = Column(String(255))
    delivery_time = Column(String(255))
    ai_match_confidence = Column(Numeric(5, 3))
    ai_validation_status = Column(String(40), nullable=False, default="missing_info")
    ai_validation_notes = Column(Text)
    product_id = Column(Integer)
    ref = Column(String(255))
    qty = Column(Integer)
    total_price = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text)


class QuotationAttachment(Base):
    __tablename__ = "quotation_attachments"
    __table_args__ = (Index("ix_quotation_attachments_quotation_id", "quotation_id"),)
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(120))
    storage_path = Column(String(500))
    extracted_text = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QuotationTemplate(Base, TimestampMixin):
    __tablename__ = "quotation_templates"
    __table_args__ = (Index("ix_quotation_templates_default", "is_default"),)
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    currency = Column(String(12), nullable=False, default="USD")
    payment_terms = Column(Text)
    delivery_terms = Column(Text)
    warranty_terms = Column(Text)
    notes = Column(Text)
    is_default = Column(Boolean, nullable=False, default=False)


class ServiceOpportunity(Base, TimestampMixin):
    __tablename__ = "service_opportunities"
    __table_args__ = (
        UniqueConstraint("equipment_id", "opportunity_type", "status", name="uq_service_opportunities_equipment_type_status"),
        Index("ix_service_opportunities_equipment_id", "equipment_id"),
        Index("ix_service_opportunities_client_id", "client_id"),
        Index("ix_service_opportunities_client_site_id", "client_site_id"),
        Index("ix_service_opportunities_lifecycle_status", "lifecycle_status"),
        Index("ix_service_opportunities_opportunity_type", "opportunity_type"),
        Index("ix_service_opportunities_priority", "priority"),
        Index("ix_service_opportunities_status", "status"),
        Index("ix_service_opportunities_assigned_to_user_id", "assigned_to_user_id"),
        Index("ix_service_opportunities_detected_at", "detected_at"),
    )
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    client_site_id = Column(Integer, ForeignKey("client_sites.id", ondelete="SET NULL"), nullable=True)
    opportunity_type = Column(String(80), nullable=False, default="SERVICE_CONTRACT")
    lifecycle_status = Column(String(80), nullable=False)
    priority = Column(String(40), nullable=False, default="LOW")
    score = Column(Integer, nullable=False, default=0)
    status = Column(String(40), nullable=False, default="NEW")
    assigned_to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    warranty_end_date = Column(Date)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    contacted_at = Column(DateTime(timezone=True))
    quote_id = Column(Integer, ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True)
    won_at = Column(DateTime(timezone=True))
    lost_at = Column(DateTime(timezone=True))
    lost_reason = Column(Text)
    notes = Column(Text)


class ManufacturerAgreement(Base, TimestampMixin):
    __tablename__ = "manufacturer_agreements"
    __table_args__ = (
        Index("ix_manufacturer_agreements_manufacturer", "manufacturer"),
        Index("ix_manufacturer_agreements_agreement_number", "agreement_number"),
        Index("ix_manufacturer_agreements_status", "status"),
    )
    id = Column(Integer, primary_key=True)
    manufacturer = Column(String(255), nullable=False)
    agreement_number = Column(String(120), unique=True)
    agreement_name = Column(String(255))
    status = Column(String(50), nullable=False, default="active")
    start_date = Column(Date)
    end_date = Column(Date)
    last_covered_date = Column(Date)
    provider = Column(String(255))
    currency = Column(String(12))
    restricted_value = Column(Numeric(12, 2), nullable=True)
    source = Column(String(120))
    notes = Column(Text)


class ManufacturerAgreementEquipment(Base, TimestampMixin):
    __tablename__ = "manufacturer_agreement_equipment"
    __table_args__ = (
        UniqueConstraint("manufacturer_agreement_id", "equipment_id", name="uq_manufacturer_agreement_equipment"),
        Index("ix_manufacturer_agreement_equipment_agreement_id", "manufacturer_agreement_id"),
        Index("ix_manufacturer_agreement_equipment_equipment_id", "equipment_id"),
        Index("ix_manufacturer_agreement_equipment_serial", "serial_number"),
        Index("ix_manufacturer_agreement_equipment_status", "coverage_status"),
    )
    id = Column(Integer, primary_key=True)
    manufacturer_agreement_id = Column(Integer, ForeignKey("manufacturer_agreements.id", ondelete="CASCADE"), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    system_id = Column(String(120))
    serial_number = Column(String(255), nullable=False)
    global_order_number = Column(String(120))
    equipment_description = Column(Text)
    client_site = Column(String(255))
    coverage_status = Column(String(50), nullable=False, default="active")
    coverage_start_date = Column(Date)
    coverage_end_date = Column(Date)
    last_covered_date = Column(Date)
    manufacturer_warranty_end_date = Column(Date)
    eosl_date = Column(Date)
    restricted_manufacturer_value = Column(Numeric(12, 2), nullable=True)
    source = Column(String(120))
    notes = Column(Text)


class CustomerServiceContract(Base, TimestampMixin):
    __tablename__ = "customer_service_contracts"
    __table_args__ = (
        Index("ix_customer_service_contracts_client_id", "client_id"),
        Index("ix_customer_service_contracts_contract_number", "contract_number"),
        Index("ix_customer_service_contracts_status", "status"),
    )
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    client_site_id = Column(Integer, ForeignKey("client_sites.id", ondelete="SET NULL"), nullable=True)
    contract_number = Column(String(120), unique=True)
    contract_name = Column(String(255))
    coverage_type = Column(String(80), nullable=False, default="FULL_SERVICE")
    status = Column(String(50), nullable=False, default="active")
    start_date = Column(Date)
    end_date = Column(Date)
    renewal_notice_date = Column(Date)
    renewal_status = Column(String(50))
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True)
    contract_value = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(12))
    response_time = Column(String(120))
    pm_visits_per_year = Column(Integer)
    labor_included = Column(Boolean, nullable=False, default=False)
    parts_included = Column(Boolean, nullable=False, default=False)
    calibration_included = Column(Boolean, nullable=False, default=False)
    travel_included = Column(Boolean, nullable=False, default=False)
    emergency_support_included = Column(Boolean, nullable=False, default=False)
    contract_owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(120))
    notes = Column(Text)


class CustomerContractEquipment(Base, TimestampMixin):
    __tablename__ = "customer_contract_equipment"
    __table_args__ = (
        UniqueConstraint("customer_service_contract_id", "equipment_id", name="uq_customer_contract_equipment"),
        Index("ix_customer_contract_equipment_contract_id", "customer_service_contract_id"),
        Index("ix_customer_contract_equipment_equipment_id", "equipment_id"),
        Index("ix_customer_contract_equipment_serial", "serial_number"),
        Index("ix_customer_contract_equipment_status", "coverage_status"),
    )
    id = Column(Integer, primary_key=True)
    customer_service_contract_id = Column(Integer, ForeignKey("customer_service_contracts.id", ondelete="CASCADE"), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    serial_number = Column(String(255), nullable=False)
    manufacturer = Column(String(255))
    model = Column(String(255))
    coverage_status = Column(String(50), nullable=False, default="active")
    coverage_start_date = Column(Date)
    coverage_end_date = Column(Date)
    labor_included = Column(Boolean, nullable=False, default=False)
    parts_included = Column(Boolean, nullable=False, default=False)
    calibration_included = Column(Boolean, nullable=False, default=False)
    travel_included = Column(Boolean, nullable=False, default=False)
    exclusion_reason = Column(Text)
    source = Column(String(120))
    notes = Column(Text)


class ContractPMCommitment(Base, TimestampMixin):
    __tablename__ = "contract_pm_commitments"
    __table_args__ = (
        Index("ix_contract_pm_commitments_contract_id", "customer_service_contract_id"),
        Index("ix_contract_pm_commitments_equipment_id", "equipment_id"),
    )
    id = Column(Integer, primary_key=True)
    customer_service_contract_id = Column(Integer, ForeignKey("customer_service_contracts.id", ondelete="CASCADE"), nullable=False)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    pm_visits_per_year = Column(Integer)
    completed_visits_year_to_date = Column(Integer, nullable=False, default=0)
    next_pm_date = Column(Date)
    commitment_status = Column(String(50), nullable=False, default="scheduled")
    notes = Column(Text)
