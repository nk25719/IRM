from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func

from app.database import Base
from app.models.mixins import TimestampMixin


class EngineerScheduleEvent(Base, TimestampMixin):
    __tablename__ = "engineer_schedule_events"
    __table_args__ = (
        Index("ix_schedule_events_start_end", "start_datetime", "end_datetime"),
        Index("ix_schedule_events_type_status", "event_type", "status"),
        Index("ix_schedule_events_client_id", "client_id"),
        Index("ix_schedule_events_service_case_id", "service_case_id"),
        Index("ix_schedule_events_import_batch_id", "import_batch_id"),
    )

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    internal_notes = Column(Text)
    event_type = Column(String(80), nullable=False, default="other", server_default="other")
    status = Column(String(50), nullable=False, default="draft", server_default="draft")
    priority = Column(String(50), nullable=False, default="normal", server_default="normal")
    start_datetime = Column(DateTime(timezone=True))
    end_datetime = Column(DateTime(timezone=True))
    all_day = Column(Boolean, nullable=False, default=False, server_default="0")
    timezone = Column(String(80), nullable=False, default="Asia/Beirut", server_default="Asia/Beirut")
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"))
    client_site_id = Column(Integer, ForeignKey("client_sites.id", ondelete="SET NULL"))
    equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"))
    service_case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"))
    service_call_id = Column(Integer, ForeignKey("service_calls.id", ondelete="SET NULL"))
    contract_id = Column(Integer, ForeignKey("contracts.id", ondelete="SET NULL"))
    customer_service_contract_id = Column(Integer, ForeignKey("customer_service_contracts.id", ondelete="SET NULL"))
    preventive_maintenance_id = Column(Integer, ForeignKey("pm_tasks.id", ondelete="SET NULL"))
    installation_id = Column(Integer)
    delivery_id = Column(Integer)
    training_id = Column(Integer)
    location_text = Column(String(500))
    meeting_link = Column(String(500))
    travel_time_before_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    travel_time_after_minutes = Column(Integer, nullable=False, default=0, server_default="0")
    conflict_override_reason = Column(Text)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_at = Column(DateTime(timezone=True))
    source = Column(String(120))
    source_reference = Column(Text)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="SET NULL"))
    is_recurring = Column(Boolean, nullable=False, default=False, server_default="0")
    recurrence_rule = Column(Text)
    parent_event_id = Column(Integer, ForeignKey("engineer_schedule_events.id", ondelete="SET NULL"))


class EngineerScheduleAssignment(Base):
    __tablename__ = "engineer_schedule_assignments"
    __table_args__ = (
        UniqueConstraint("schedule_event_id", "engineer_id", name="uq_schedule_assignment_event_engineer"),
        Index("ix_schedule_assignments_event_id", "schedule_event_id"),
        Index("ix_schedule_assignments_engineer_id", "engineer_id"),
    )

    id = Column(Integer, primary_key=True)
    schedule_event_id = Column(Integer, ForeignKey("engineer_schedule_events.id", ondelete="CASCADE"), nullable=False)
    engineer_id = Column(Integer, ForeignKey("engineers.id", ondelete="RESTRICT"), nullable=False)
    assignment_role = Column(String(50), nullable=False, default="lead", server_default="lead")
    assignment_status = Column(String(50), nullable=False, default="assigned", server_default="assigned")
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    assigned_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    notes = Column(Text)


class EngineerAvailability(Base, TimestampMixin):
    __tablename__ = "engineer_availability"
    __table_args__ = (
        Index("ix_engineer_availability_engineer_id", "engineer_id"),
        Index("ix_engineer_availability_start_end", "start_datetime", "end_datetime"),
    )

    id = Column(Integer, primary_key=True)
    engineer_id = Column(Integer, ForeignKey("engineers.id", ondelete="CASCADE"), nullable=False)
    availability_type = Column(String(80), nullable=False, default="standard_hours", server_default="standard_hours")
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=False)
    is_available = Column(Boolean, nullable=False, default=True, server_default="1")
    notes = Column(Text)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))


class ScheduleChangeLog(Base):
    __tablename__ = "schedule_change_log"
    __table_args__ = (
        Index("ix_schedule_change_log_event_id", "schedule_event_id"),
        Index("ix_schedule_change_log_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    schedule_event_id = Column(Integer, ForeignKey("engineer_schedule_events.id", ondelete="CASCADE"), nullable=False)
    change_type = Column(String(120), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    old_values = Column(Text)
    new_values = Column(Text)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
