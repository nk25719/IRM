"""Aftermarket imported service reports

Revision ID: 20260709_aftermarket_service_reports
Revises: 20260709_admin_foundation
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa


revision = "20260709_aftermarket_service_reports"
down_revision = "20260709_admin_foundation"
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


def create_index_if_missing(bind, name, table_name, fields, unique=False):
    existing = {index["name"] for index in sa.inspect(bind).get_indexes(table_name)} if has_table(bind, table_name) else set()
    if name not in existing:
        op.create_index(name, table_name, fields, unique=unique)


SERVICE_REPORT_COLUMNS = [
    sa.Column("sr_number", sa.String(length=120)),
    sa.Column("engineer_id", sa.Integer()),
    sa.Column("customer_id", sa.Integer()),
    sa.Column("equipment_asset_id", sa.Integer()),
    sa.Column("equipment_id", sa.Integer()),
    sa.Column("institution", sa.String(length=255)),
    sa.Column("city", sa.String(length=120)),
    sa.Column("country", sa.String(length=120)),
    sa.Column("supplier", sa.String(length=255)),
    sa.Column("equipment_model", sa.String(length=255)),
    sa.Column("equipment_serial_number", sa.String(length=255)),
    sa.Column("call_date", sa.String(length=40)),
    sa.Column("call_time", sa.String(length=40)),
    sa.Column("visit_date", sa.String(length=40)),
    sa.Column("visit_time", sa.String(length=40)),
    sa.Column("completed_date", sa.String(length=40)),
    sa.Column("completed_time", sa.String(length=40)),
    sa.Column("description", sa.Text()),
    sa.Column("call_reason", sa.Text()),
    sa.Column("ct1", sa.String(length=255)),
    sa.Column("ct2", sa.String(length=255)),
    sa.Column("total_travel_hours", sa.Numeric(12, 2), server_default="0"),
    sa.Column("total_labor_hours", sa.Numeric(12, 2), server_default="0"),
    sa.Column("total_working_hours", sa.Numeric(12, 2), server_default="0"),
    sa.Column("total_travel_km", sa.Numeric(12, 2), server_default="0"),
    sa.Column("status", sa.String(length=80)),
    sa.Column("match_status", sa.String(length=80)),
    sa.Column("source_file", sa.String(length=255)),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
]


def upgrade():
    bind = op.get_bind()
    if not has_table(bind, "equipment_assets"):
        op.create_table(
            "equipment_assets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("company", sa.String(length=255)),
            sa.Column("supplier", sa.String(length=255)),
            sa.Column("product_type", sa.String(length=255)),
            sa.Column("model", sa.String(length=255)),
            sa.Column("serial_number", sa.String(length=255), unique=True),
            sa.Column("institution", sa.String(length=255)),
            sa.Column("unit_status", sa.String(length=120)),
            sa.Column("order_number", sa.String(length=120)),
            sa.Column("installation_date", sa.String(length=40)),
            sa.Column("warranty_end_date", sa.String(length=40)),
            sa.Column("customer_id", sa.Integer()),
            sa.Column("department_id", sa.Integer()),
            sa.Column("source_file", sa.String(length=255)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    else:
        add_missing_columns(
            bind,
            "equipment_assets",
            [
                sa.Column("company", sa.String(length=255)),
                sa.Column("supplier", sa.String(length=255)),
                sa.Column("product_type", sa.String(length=255)),
                sa.Column("model", sa.String(length=255)),
                sa.Column("serial_number", sa.String(length=255)),
                sa.Column("institution", sa.String(length=255)),
                sa.Column("unit_status", sa.String(length=120)),
                sa.Column("order_number", sa.String(length=120)),
                sa.Column("installation_date", sa.String(length=40)),
                sa.Column("warranty_end_date", sa.String(length=40)),
                sa.Column("customer_id", sa.Integer()),
                sa.Column("department_id", sa.Integer()),
                sa.Column("source_file", sa.String(length=255)),
                sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            ],
        )

    if not has_table(bind, "service_reports"):
        op.create_table(
            "service_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            *SERVICE_REPORT_COLUMNS,
        )
    else:
        add_missing_columns(bind, "service_reports", SERVICE_REPORT_COLUMNS)

    if not has_table(bind, "service_report_parts"):
        op.create_table(
            "service_report_parts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("service_report_id", sa.Integer()),
            sa.Column("sr_number", sa.String(length=120)),
            sa.Column("supplier", sa.String(length=255)),
            sa.Column("part_number", sa.String(length=255)),
            sa.Column("description", sa.Text()),
            sa.Column("quantity", sa.Numeric(12, 2), server_default="0"),
            sa.Column("unit_price", sa.Numeric(12, 2), server_default="0"),
            sa.Column("total_price", sa.Numeric(12, 2), server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    create_index_if_missing(bind, "ux_equipment_assets_serial_number", "equipment_assets", ["serial_number"], unique=True)
    create_index_if_missing(bind, "ix_equipment_assets_model", "equipment_assets", ["model"])
    create_index_if_missing(bind, "ix_equipment_assets_institution", "equipment_assets", ["institution"])
    create_index_if_missing(bind, "ux_service_reports_sr_number", "service_reports", ["sr_number"], unique=True)
    create_index_if_missing(bind, "ix_service_reports_asset", "service_reports", ["equipment_asset_id"])
    create_index_if_missing(bind, "ix_service_reports_serial", "service_reports", ["equipment_serial_number"])
    create_index_if_missing(bind, "ix_service_report_parts_report", "service_report_parts", ["service_report_id"])


def downgrade():
    pass
