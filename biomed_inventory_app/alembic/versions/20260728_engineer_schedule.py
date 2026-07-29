"""engineer schedule

Revision ID: 20260728_engineer_schedule
Revises: 20260723_service_contract_intelligence
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa

revision = "20260728_engineer_schedule"
down_revision = "20260723_service_contract_intelligence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "engineer_schedule_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("internal_notes", sa.Text()),
        sa.Column("event_type", sa.String(80), nullable=False, server_default="other"),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("priority", sa.String(50), nullable=False, server_default="normal"),
        sa.Column("start_datetime", sa.DateTime(timezone=True)),
        sa.Column("end_datetime", sa.DateTime(timezone=True)),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("timezone", sa.String(80), nullable=False, server_default="Asia/Beirut"),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="SET NULL")),
        sa.Column("client_site_id", sa.Integer(), sa.ForeignKey("client_sites.id", ondelete="SET NULL")),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL")),
        sa.Column("service_case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")),
        sa.Column("service_call_id", sa.Integer(), sa.ForeignKey("service_calls.id", ondelete="SET NULL")),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="SET NULL")),
        sa.Column("customer_service_contract_id", sa.Integer(), sa.ForeignKey("customer_service_contracts.id", ondelete="SET NULL")),
        sa.Column("preventive_maintenance_id", sa.Integer(), sa.ForeignKey("pm_tasks.id", ondelete="SET NULL")),
        sa.Column("installation_id", sa.Integer()),
        sa.Column("delivery_id", sa.Integer()),
        sa.Column("training_id", sa.Integer()),
        sa.Column("location_text", sa.String(500)),
        sa.Column("meeting_link", sa.String(500)),
        sa.Column("travel_time_before_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("travel_time_after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_override_reason", sa.Text()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(120)),
        sa.Column("source_reference", sa.Text()),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="SET NULL")),
        sa.Column("is_recurring", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("recurrence_rule", sa.Text()),
        sa.Column("parent_event_id", sa.Integer(), sa.ForeignKey("engineer_schedule_events.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_schedule_events_start_end", "engineer_schedule_events", ["start_datetime", "end_datetime"])
    op.create_index("ix_schedule_events_type_status", "engineer_schedule_events", ["event_type", "status"])
    op.create_index("ix_schedule_events_client_id", "engineer_schedule_events", ["client_id"])
    op.create_index("ix_schedule_events_service_case_id", "engineer_schedule_events", ["service_case_id"])
    op.create_index("ix_schedule_events_import_batch_id", "engineer_schedule_events", ["import_batch_id"])
    op.create_table(
        "engineer_schedule_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_event_id", sa.Integer(), sa.ForeignKey("engineer_schedule_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engineer_id", sa.Integer(), sa.ForeignKey("engineers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignment_role", sa.String(50), nullable=False, server_default="lead"),
        sa.Column("assignment_status", sa.String(50), nullable=False, server_default="assigned"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("schedule_event_id", "engineer_id", name="uq_schedule_assignment_event_engineer"),
    )
    op.create_index("ix_schedule_assignments_event_id", "engineer_schedule_assignments", ["schedule_event_id"])
    op.create_index("ix_schedule_assignments_engineer_id", "engineer_schedule_assignments", ["engineer_id"])
    op.create_table(
        "engineer_availability",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("engineer_id", sa.Integer(), sa.ForeignKey("engineers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("availability_type", sa.String(80), nullable=False, server_default="standard_hours"),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_engineer_availability_engineer_id", "engineer_availability", ["engineer_id"])
    op.create_index("ix_engineer_availability_start_end", "engineer_availability", ["start_datetime", "end_datetime"])
    op.create_table(
        "schedule_change_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("schedule_event_id", sa.Integer(), sa.ForeignKey("engineer_schedule_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_type", sa.String(120), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("old_values", sa.Text()),
        sa.Column("new_values", sa.Text()),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_schedule_change_log_event_id", "schedule_change_log", ["schedule_event_id"])
    op.create_index("ix_schedule_change_log_created_at", "schedule_change_log", ["created_at"])


def downgrade():
    op.drop_table("schedule_change_log")
    op.drop_table("engineer_availability")
    op.drop_table("engineer_schedule_assignments")
    op.drop_table("engineer_schedule_events")
