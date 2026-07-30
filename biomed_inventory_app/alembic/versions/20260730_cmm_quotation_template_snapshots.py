"""CMM quotation template snapshots and AI audit log

Revision ID: 20260730_cmm_quote_snapshots
Revises: 20260729_customer_contacts_large_import
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_cmm_quote_snapshots"
down_revision = "20260729_customer_contacts_large_import"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    for column in [
        sa.Column("client_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("client_site_id", sa.Integer(), nullable=True),
        sa.Column("sales_person_id", sa.Integer(), nullable=True),
        sa.Column("sales_person_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("company_phone_snapshot", sa.String(length=80), nullable=True),
        sa.Column("company_email_snapshot", sa.String(length=255), nullable=True),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grand_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        sa.Column("disclaimer_text", sa.Text(), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_version", sa.String(length=80), nullable=True),
        sa.Column("form_code", sa.String(length=120), nullable=True),
        sa.Column("edition", sa.String(length=80), nullable=True),
        sa.Column("template_name", sa.String(length=255), nullable=True),
        sa.Column("footer_form_code", sa.String(length=160), nullable=True),
        sa.Column("template_snapshot", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_pdf_path", sa.String(length=500), nullable=True),
        sa.Column("ai_source", sa.Text(), nullable=True),
        sa.Column("ai_missing_information", sa.Text(), nullable=True),
        sa.Column("ai_warnings", sa.Text(), nullable=True),
    ]:
        _add_column("quotations", column)

    for column in [
        sa.Column("equipment_id", sa.Integer(), nullable=True),
        sa.Column("equipment_description_snapshot", sa.Text(), nullable=True),
        sa.Column("manufacturer_snapshot", sa.String(length=255), nullable=True),
        sa.Column("model_snapshot", sa.String(length=255), nullable=True),
        sa.Column("serial_number_snapshot", sa.String(length=255), nullable=True),
        sa.Column("service_report_number", sa.String(length=120), nullable=True),
        sa.Column("part_number", sa.String(length=255), nullable=True),
        sa.Column("service_code", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("taxable", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    ]:
        _add_column("quotation_items", column)

    for column in [
        sa.Column("template_code", sa.String(length=120), nullable=True),
        sa.Column("edition", sa.String(length=80), nullable=True),
        sa.Column("logo_asset", sa.String(length=500), nullable=True),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("company_legal_information", sa.Text(), nullable=True),
        sa.Column("company_address", sa.Text(), nullable=True),
        sa.Column("company_telephone", sa.String(length=120), nullable=True),
        sa.Column("company_email", sa.String(length=255), nullable=True),
        sa.Column("company_website", sa.String(length=255), nullable=True),
        sa.Column("default_vat_rate", sa.Numeric(5, 2), nullable=False, server_default="11"),
        sa.Column("default_validity_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("default_disclaimer", sa.Text(), nullable=True),
        sa.Column("footer_form_code", sa.String(length=160), nullable=True),
    ]:
        _add_column("quotation_templates", column)

    op.create_table(
        "quotation_ai_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("source_entity", sa.String(length=255), nullable=True),
        sa.Column("prompt_template_version", sa.String(length=120), nullable=True),
        sa.Column("input_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extracted_summary", sa.Text(), nullable=True),
        sa.Column("user_approved_status", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )
    op.create_index("ix_quotation_ai_audit_logs_quotation_id", "quotation_ai_audit_logs", ["quotation_id"], if_not_exists=True)
    op.create_index("ix_quotation_ai_audit_logs_event_type", "quotation_ai_audit_logs", ["event_type"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_quotation_ai_audit_logs_event_type", table_name="quotation_ai_audit_logs", if_exists=True)
    op.drop_index("ix_quotation_ai_audit_logs_quotation_id", table_name="quotation_ai_audit_logs", if_exists=True)
    op.drop_table("quotation_ai_audit_logs", if_exists=True)
