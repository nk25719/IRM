"""add service contract intelligence opportunities

Revision ID: 20260723_service_contract_intelligence
Revises: 20260716_equipment_model_master_fk_constraints
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260723_service_contract_intelligence"
down_revision = "20260716_equipment_model_master_fks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manufacturer_agreements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manufacturer", sa.String(length=255), nullable=False),
        sa.Column("agreement_number", sa.String(length=120), nullable=True),
        sa.Column("agreement_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("last_covered_date", sa.Date(), nullable=True),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=12), nullable=True),
        sa.Column("restricted_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agreement_number"),
    )
    op.create_table(
        "manufacturer_agreement_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manufacturer_agreement_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("system_id", sa.String(length=120), nullable=True),
        sa.Column("serial_number", sa.String(length=255), nullable=False),
        sa.Column("global_order_number", sa.String(length=120), nullable=True),
        sa.Column("equipment_description", sa.Text(), nullable=True),
        sa.Column("client_site", sa.String(length=255), nullable=True),
        sa.Column("coverage_status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("coverage_start_date", sa.Date(), nullable=True),
        sa.Column("coverage_end_date", sa.Date(), nullable=True),
        sa.Column("last_covered_date", sa.Date(), nullable=True),
        sa.Column("manufacturer_warranty_end_date", sa.Date(), nullable=True),
        sa.Column("eosl_date", sa.Date(), nullable=True),
        sa.Column("restricted_manufacturer_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["manufacturer_agreement_id"], ["manufacturer_agreements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("manufacturer_agreement_id", "equipment_id", name="uq_manufacturer_agreement_equipment"),
    )
    op.create_table(
        "customer_service_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("client_site_id", sa.Integer(), nullable=True),
        sa.Column("contract_number", sa.String(length=120), nullable=True),
        sa.Column("contract_name", sa.String(length=255), nullable=True),
        sa.Column("coverage_type", sa.String(length=80), nullable=False, server_default="FULL_SERVICE"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("renewal_notice_date", sa.Date(), nullable=True),
        sa.Column("renewal_status", sa.String(length=50), nullable=True),
        sa.Column("quotation_id", sa.Integer(), nullable=True),
        sa.Column("contract_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=12), nullable=True),
        sa.Column("response_time", sa.String(length=120), nullable=True),
        sa.Column("pm_visits_per_year", sa.Integer(), nullable=True),
        sa.Column("labor_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("parts_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("calibration_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("travel_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("emergency_support_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("contract_owner_user_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_site_id"], ["client_sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quotation_id"], ["quotations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("contract_number"),
    )
    op.create_table(
        "customer_contract_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_service_contract_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.String(length=255), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("coverage_status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("coverage_start_date", sa.Date(), nullable=True),
        sa.Column("coverage_end_date", sa.Date(), nullable=True),
        sa.Column("labor_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("parts_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("calibration_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("travel_included", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_service_contract_id"], ["customer_service_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("customer_service_contract_id", "equipment_id", name="uq_customer_contract_equipment"),
    )
    op.create_table(
        "contract_pm_commitments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_service_contract_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("pm_visits_per_year", sa.Integer(), nullable=True),
        sa.Column("completed_visits_year_to_date", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_pm_date", sa.Date(), nullable=True),
        sa.Column("commitment_status", sa.String(length=50), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["customer_service_contract_id"], ["customer_service_contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "service_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("client_site_id", sa.Integer(), nullable=True),
        sa.Column("opportunity_type", sa.String(length=80), nullable=False, server_default="NEW_SERVICE_CONTRACT"),
        sa.Column("lifecycle_status", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.String(length=40), nullable=False, server_default="LOW"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="NEW"),
        sa.Column("assigned_to_user_id", sa.Integer(), nullable=True),
        sa.Column("warranty_end_date", sa.Date(), nullable=True),
        sa.Column("contract_id", sa.Integer(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote_id", sa.Integer(), nullable=True),
        sa.Column("won_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_site_id"], ["client_sites.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["customer_service_contracts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("equipment_id", "opportunity_type", "status", name="uq_service_opportunities_equipment_type_status"),
    )
    for name, columns in {
        "ix_service_opportunities_equipment_id": ["equipment_id"],
        "ix_service_opportunities_client_id": ["client_id"],
        "ix_service_opportunities_client_site_id": ["client_site_id"],
        "ix_service_opportunities_lifecycle_status": ["lifecycle_status"],
        "ix_service_opportunities_opportunity_type": ["opportunity_type"],
        "ix_service_opportunities_priority": ["priority"],
        "ix_service_opportunities_status": ["status"],
        "ix_service_opportunities_assigned_to_user_id": ["assigned_to_user_id"],
        "ix_service_opportunities_detected_at": ["detected_at"],
    }.items():
        op.create_index(name, "service_opportunities", columns)


def downgrade():
    for name in [
        "ix_service_opportunities_detected_at",
        "ix_service_opportunities_assigned_to_user_id",
        "ix_service_opportunities_status",
        "ix_service_opportunities_priority",
        "ix_service_opportunities_opportunity_type",
        "ix_service_opportunities_lifecycle_status",
        "ix_service_opportunities_client_site_id",
        "ix_service_opportunities_client_id",
        "ix_service_opportunities_equipment_id",
    ]:
        op.drop_index(name, table_name="service_opportunities")
    op.drop_table("service_opportunities")
    op.drop_table("contract_pm_commitments")
    op.drop_table("customer_contract_equipment")
    op.drop_table("customer_service_contracts")
    op.drop_table("manufacturer_agreement_equipment")
    op.drop_table("manufacturer_agreements")
