"""Quotation generator module

Revision ID: 20260703_quotation_generator
Revises: 20260524_mdmanser_calendar_events
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260703_quotation_generator"
down_revision = "20260524_mdmanser_calendar_events"
branch_labels = None
depends_on = None


def has_table(bind, table_name):
    return sa.inspect(bind).has_table(table_name)


def columns(bind, table_name):
    if not has_table(bind, table_name):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def add_missing_columns(bind, table_name, wanted):
    existing = columns(bind, table_name)
    for column in wanted:
        if column.name not in existing:
            op.add_column(table_name, column)


def create_index_if_missing(bind, name, table_name, fields):
    existing = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)} if has_table(bind, table_name) else set()
    if name not in existing:
        op.create_index(name, table_name, fields)


def upgrade():
    bind = op.get_bind()
    if not has_table(bind, "quotations"):
        op.create_table(
            "quotations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("quotation_number", sa.String(length=120)),
            sa.Column("quotation_no", sa.String(length=120)),
            sa.Column("client_id", sa.Integer()),
            sa.Column("department_id", sa.Integer()),
            sa.Column("contact_id", sa.Integer()),
            sa.Column("case_id", sa.Integer()),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
            sa.Column("quotation_date", sa.Date()),
            sa.Column("quote_date", sa.Date()),
            sa.Column("valid_until", sa.Date()),
            sa.Column("currency", sa.String(length=12), nullable=False, server_default="USD"),
            sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("vat_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("payment_terms", sa.Text()),
            sa.Column("delivery_terms", sa.Text()),
            sa.Column("warranty_terms", sa.Text()),
            sa.Column("sales_person", sa.String(length=255)),
            sa.Column("phone_number", sa.String(length=80)),
            sa.Column("email", sa.String(length=255)),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    else:
        add_missing_columns(
            bind,
            "quotations",
            [
                sa.Column("quotation_number", sa.String(length=120)),
                sa.Column("quotation_no", sa.String(length=120)),
                sa.Column("department_id", sa.Integer()),
                sa.Column("contact_id", sa.Integer()),
                sa.Column("case_id", sa.Integer()),
                sa.Column("quotation_date", sa.Date()),
                sa.Column("quote_date", sa.Date()),
                sa.Column("valid_until", sa.Date()),
                sa.Column("currency", sa.String(length=12), server_default="USD"),
                sa.Column("subtotal", sa.Numeric(12, 2), server_default="0"),
                sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0"),
                sa.Column("vat_rate", sa.Numeric(5, 2), server_default="0"),
                sa.Column("vat_amount", sa.Numeric(12, 2), server_default="0"),
                sa.Column("total_amount", sa.Numeric(12, 2), server_default="0"),
                sa.Column("amount", sa.Numeric(12, 2), server_default="0"),
                sa.Column("payment_terms", sa.Text()),
                sa.Column("delivery_terms", sa.Text()),
                sa.Column("warranty_terms", sa.Text()),
                sa.Column("sales_person", sa.String(length=255)),
                sa.Column("phone_number", sa.String(length=80)),
                sa.Column("email", sa.String(length=255)),
            ],
        )

    if not has_table(bind, "quotation_items"):
        op.create_table(
            "quotation_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("quotation_id", sa.Integer(), nullable=False),
            sa.Column("equipment_group_id", sa.Integer()),
            sa.Column("inventory_item_id", sa.Integer()),
            sa.Column("item_code", sa.String(length=255)),
            sa.Column("manufacturer_part_number", sa.String(length=255)),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("ai_normalized_description", sa.Text()),
            sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="1"),
            sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
            sa.Column("item_type", sa.String(length=40), nullable=False, server_default="spare_part"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("warranty", sa.String(length=255)),
            sa.Column("delivery_time", sa.String(length=255)),
            sa.Column("ai_match_confidence", sa.Numeric(5, 3)),
            sa.Column("ai_validation_status", sa.String(length=40), nullable=False, server_default="missing_info"),
            sa.Column("ai_validation_notes", sa.Text()),
        )
    else:
        add_missing_columns(
            bind,
            "quotation_items",
            [
                sa.Column("equipment_group_id", sa.Integer()),
                sa.Column("inventory_item_id", sa.Integer()),
                sa.Column("item_code", sa.String(length=255)),
                sa.Column("manufacturer_part_number", sa.String(length=255)),
                sa.Column("ai_normalized_description", sa.Text()),
                sa.Column("quantity", sa.Numeric(12, 2), server_default="1"),
                sa.Column("discount_percent", sa.Numeric(5, 2), server_default="0"),
                sa.Column("item_type", sa.String(length=40), server_default="spare_part"),
                sa.Column("sort_order", sa.Integer(), server_default="0"),
                sa.Column("line_total", sa.Numeric(12, 2), server_default="0"),
                sa.Column("warranty", sa.String(length=255)),
                sa.Column("delivery_time", sa.String(length=255)),
                sa.Column("ai_match_confidence", sa.Numeric(5, 3)),
                sa.Column("ai_validation_status", sa.String(length=40), server_default="missing_info"),
                sa.Column("ai_validation_notes", sa.Text()),
            ],
        )

    if not has_table(bind, "quotation_equipment_groups"):
        op.create_table(
            "quotation_equipment_groups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("quotation_id", sa.Integer(), nullable=False),
            sa.Column("equipment_id", sa.Integer()),
            sa.Column("equipment_name", sa.String(length=255)),
            sa.Column("manufacturer", sa.String(length=255)),
            sa.Column("model", sa.String(length=255)),
            sa.Column("serial_number", sa.String(length=255)),
            sa.Column("service_report_number", sa.String(length=255)),
            sa.Column("department_name", sa.String(length=255)),
            sa.Column("location", sa.String(length=255)),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not has_table(bind, "quotation_attachments"):
        op.create_table(
            "quotation_attachments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("quotation_id", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120)),
            sa.Column("storage_path", sa.String(length=500)),
            sa.Column("extracted_text", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    if not has_table(bind, "quotation_templates"):
        op.create_table(
            "quotation_templates",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("currency", sa.String(length=12), nullable=False, server_default="USD"),
            sa.Column("payment_terms", sa.Text()),
            sa.Column("delivery_terms", sa.Text()),
            sa.Column("warranty_terms", sa.Text()),
            sa.Column("notes", sa.Text()),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )

    create_index_if_missing(bind, "ix_quotations_client_id", "quotations", ["client_id"])
    create_index_if_missing(bind, "ix_quotations_number", "quotations", ["quotation_number"])
    create_index_if_missing(bind, "ix_quotations_status", "quotations", ["status"])
    create_index_if_missing(bind, "ix_quotation_items_quotation_id", "quotation_items", ["quotation_id"])
    create_index_if_missing(bind, "ix_quotation_items_equipment_group_id", "quotation_items", ["equipment_group_id"])
    create_index_if_missing(bind, "ix_quotation_equipment_groups_quotation_id", "quotation_equipment_groups", ["quotation_id"])
    create_index_if_missing(bind, "ix_quotation_items_inventory_item_id", "quotation_items", ["inventory_item_id"])
    create_index_if_missing(bind, "ix_quotation_attachments_quotation_id", "quotation_attachments", ["quotation_id"])
    create_index_if_missing(bind, "ix_quotation_templates_default", "quotation_templates", ["is_default"])


def downgrade():
    pass
