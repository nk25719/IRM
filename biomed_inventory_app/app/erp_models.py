from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from .database import Base


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Client(Base, TimestampMixin):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255))
    address = Column(Text)
    status = Column(String(50), nullable=False, default="active")
    financial_status = Column(String(50), nullable=False, default="good_standing")

    departments = relationship("Department", back_populates="client")


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (Index("ix_departments_client_id", "client_id"),)
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    floor_location = Column(String(255))
    contact_name = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))
    notes = Column(Text)

    client = relationship("Client", back_populates="departments")


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_client_id", "client_id"), Index("ix_contacts_department_id", "department_id"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    title = Column(String(255))
    phone = Column(String(50))
    email = Column(String(255))
    notes = Column(Text)


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
    parent_case_reference = Column(String(80), nullable=False)
    case_type = Column(String(80), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default="open")
    priority = Column(String(50), nullable=False, default="normal")
    blocked_reason = Column(Text)
    responsible_user_id = Column(Integer, nullable=True)


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


class ClientActivity(Base):
    __tablename__ = "client_activities"
    __table_args__ = (Index("ix_client_activities_client_id", "client_id"), Index("ix_client_activities_department_id", "department_id"), Index("ix_client_activities_case_id", "case_id"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    activity_type = Column(String(40), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), nullable=False, default="open")
    date = Column(Date)
    created_by = Column(Integer, nullable=True)


class EquipmentModel(Base):
    __tablename__ = "equipment_models"
    id = Column(Integer, primary_key=True)
    manufacturer = Column(String(255))
    model = Column(String(255))


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (Index("ix_equipment_client_id", "client_id"), Index("ix_equipment_department_id", "department_id"), Index("ix_equipment_serial_number", "serial_number"))
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


class ServiceCall(Base):
    __tablename__ = "service_calls"
    __table_args__ = (Index("ix_service_calls_client_id", "client_id"), Index("ix_service_calls_department_id", "department_id"), Index("ix_service_calls_case_id", "case_id"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    call_type = Column(String(80), nullable=False)
    priority = Column(String(50), nullable=False, default="normal")
    status = Column(String(50), nullable=False, default="open")
    blocked_reason = Column(Text)
    assigned_engineer_id = Column(Integer, nullable=True)
    request_date = Column(Date)
    due_date = Column(Date)


class PMTask(Base):
    __tablename__ = "pm_tasks"
    __table_args__ = (Index("ix_pm_tasks_client_id", "client_id"), Index("ix_pm_tasks_department_id", "department_id"), Index("ix_pm_tasks_case_id", "case_id"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="SET NULL"), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    scheduled_date = Column(Date)
    completed_date = Column(Date, nullable=True)
    status = Column(String(50), nullable=False, default="scheduled")
    assigned_engineer_id = Column(Integer, nullable=True)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (Index("ix_contracts_client_id", "client_id"),)
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    contract_type = Column(String(80), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), nullable=False, default="active")
    coverage_notes = Column(Text)


class Warranty(Base):
    __tablename__ = "warranties"
    __table_args__ = (Index("ix_warranties_client_id", "client_id"),)
    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String(50), nullable=False, default="active")
    coverage_notes = Column(Text)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (Index("ix_invoices_client_id", "client_id"), Index("ix_invoices_case_id", "case_id"), Index("ix_invoices_parent_case_reference", "parent_case_reference"))
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    parent_case_reference = Column(String(80))
    invoice_number = Column(String(80), nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    due_date = Column(Date)
    paid_date = Column(Date, nullable=True)
