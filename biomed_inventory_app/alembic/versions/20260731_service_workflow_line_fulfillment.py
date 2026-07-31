"""service workflow line fulfillment

Revision ID: 20260731_service_workflow_line_fulfillment
Revises: 20260730_cmm_quote_snapshots
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_service_workflow_line_fulfillment"
down_revision = "20260730_cmm_quote_snapshots"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column(table_name: str, column: sa.Column) -> None:
    if table_name in _table_names() and column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _create_table_if_missing(table_name: str, *columns: sa.Column) -> None:
    if table_name not in _table_names():
        op.create_table(table_name, *columns)


def upgrade() -> None:
    _create_table_if_missing(
        "service_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_number", sa.String(120), unique=True),
        sa.Column("call_no", sa.String(120)),
        sa.Column("client_id", sa.Integer()),
        sa.Column("customer_id", sa.Integer()),
        sa.Column("equipment_id", sa.Integer()),
        sa.Column("status", sa.String(80), nullable=False, server_default="open"),
        sa.Column("issue", sa.Text()),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "service_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_call_id", sa.Integer(), sa.ForeignKey("service_calls.id", ondelete="SET NULL")),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("quotations.id", ondelete="SET NULL"), unique=True),
        sa.Column("offer_number", sa.String(120)),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "service_offer_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_offer_id", sa.Integer(), sa.ForeignKey("service_offers.id", ondelete="CASCADE")),
        sa.Column("quotation_item_id", sa.Integer(), sa.ForeignKey("quotation_items.id", ondelete="SET NULL"), unique=True),
        sa.Column("item_type", sa.String(80)),
        sa.Column("description", sa.Text()),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "stock_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_order_id", sa.Integer(), sa.ForeignKey("customer_orders.id", ondelete="CASCADE")),
        sa.Column("client_order_item_id", sa.Integer(), sa.ForeignKey("customer_order_items.id", ondelete="CASCADE")),
        sa.Column("customer_order_item_id", sa.Integer(), sa.ForeignKey("customer_order_items.id", ondelete="CASCADE")),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(80), nullable=False, server_default="reserved"),
        sa.Column("source_document", sa.String(120)),
        sa.Column("source_line_id", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("movement_type", sa.String(80), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("source_document", sa.String(120), nullable=False),
        sa.Column("source_line_id", sa.Integer()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("po_no", sa.String(120), unique=True),
        sa.Column("supplier_id", sa.Integer()),
        sa.Column("supplier", sa.String(255)),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("po_date", sa.Date()),
        sa.Column("expected_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "purchase_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE")),
        sa.Column("po_no", sa.String(120)),
        sa.Column("client_order_item_id", sa.Integer(), sa.ForeignKey("customer_order_items.id", ondelete="SET NULL")),
        sa.Column("customer_order_item_id", sa.Integer(), sa.ForeignKey("customer_order_items.id", ondelete="SET NULL")),
        sa.Column("quotation_item_id", sa.Integer(), sa.ForeignKey("quotation_items.id", ondelete="SET NULL")),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("product_id", sa.Integer()),
        sa.Column("ref", sa.String(255)),
        sa.Column("pn", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ordered_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shipped_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(80), nullable=False, server_default="ordered"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "shipments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_no", sa.String(120), unique=True),
        sa.Column("supplier_id", sa.Integer()),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("shipment_date", sa.Date()),
        sa.Column("expected_arrival", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "shipment_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id", ondelete="CASCADE")),
        sa.Column("purchase_order_item_id", sa.Integer(), sa.ForeignKey("purchase_order_items.id", ondelete="SET NULL")),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("ref", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shipped_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(80), nullable=False, server_default="shipped"),
    )
    _create_table_if_missing(
        "receptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reception_no", sa.String(120), unique=True),
        sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id", ondelete="SET NULL")),
        sa.Column("received_date", sa.Date()),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "reception_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reception_id", sa.Integer(), sa.ForeignKey("receptions.id", ondelete="CASCADE")),
        sa.Column("shipment_item_id", sa.Integer(), sa.ForeignKey("shipment_items.id", ondelete="SET NULL")),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("ref", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serial_number", sa.String(255)),
        sa.Column("batch_lot_number", sa.String(255)),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("warehouse_location", sa.String(255)),
        sa.Column("status", sa.String(80), nullable=False, server_default="received"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "service_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_call_id", sa.Integer(), sa.ForeignKey("service_calls.id", ondelete="SET NULL")),
        sa.Column("customer_order_id", sa.Integer(), sa.ForeignKey("customer_orders.id", ondelete="SET NULL")),
        sa.Column("report_no", sa.String(120), unique=True),
        sa.Column("status", sa.String(80), nullable=False, server_default="draft"),
        sa.Column("report_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    _create_table_if_missing(
        "service_report_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_report_id", sa.Integer(), sa.ForeignKey("service_reports.id", ondelete="CASCADE")),
        sa.Column("client_order_item_id", sa.Integer(), sa.ForeignKey("customer_order_items.id", ondelete="SET NULL")),
        sa.Column("customer_order_item_id", sa.Integer(), sa.ForeignKey("customer_order_items.id", ondelete="SET NULL")),
        sa.Column("stock_item_id", sa.Integer(), sa.ForeignKey("stock_items.id", ondelete="SET NULL")),
        sa.Column("description", sa.Text()),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action", sa.String(80), nullable=False, server_default="delivered"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    for column in [
        sa.Column("service_call_id", sa.Integer()),
        sa.Column("service_offer_id", sa.Integer()),
    ]:
        _add_column("quotations", column)
    for column in [
        sa.Column("service_offer_id", sa.Integer()),
        sa.Column("service_call_id", sa.Integer()),
    ]:
        _add_column("customer_orders", column)
    for column in [
        sa.Column("service_offer_item_id", sa.Integer()),
        sa.Column("available_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("installed_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchasing_status", sa.String(80)),
        sa.Column("shipment_status", sa.String(80)),
        sa.Column("reception_status", sa.String(80)),
        sa.Column("delivery_status", sa.String(80)),
    ]:
        _add_column("customer_order_items", column)
    for column in [
        sa.Column("client_order_item_id", sa.Integer()),
        sa.Column("ordered_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shipped_qty", sa.Integer(), nullable=False, server_default="0"),
    ]:
        _add_column("purchase_order_items", column)
    for column in [
        sa.Column("shipped_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_qty", sa.Integer(), nullable=False, server_default="0"),
    ]:
        _add_column("shipment_items", column)
    for column in [
        sa.Column("accepted_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serial_number", sa.String(255)),
        sa.Column("batch_lot_number", sa.String(255)),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("warehouse_location", sa.String(255)),
    ]:
        _add_column("reception_items", column)
    for column in [
        sa.Column("batch_lot_number", sa.String(255)),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("reserved_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issued_qty", sa.Integer(), nullable=False, server_default="0"),
    ]:
        _add_column("stock_items", column)

    op.create_index("ix_stock_reservations_order_item", "stock_reservations", ["customer_order_item_id"], if_not_exists=True)
    op.create_index("ix_stock_movements_source", "stock_movements", ["source_document", "source_line_id"], if_not_exists=True)


def downgrade() -> None:
    for index_name, table_name in [
        ("ix_stock_movements_source", "stock_movements"),
        ("ix_stock_reservations_order_item", "stock_reservations"),
    ]:
        try:
            op.drop_index(index_name, table_name=table_name)
        except Exception:
            pass
    for table_name in [
        "service_report_items",
        "service_reports",
        "stock_movements",
        "stock_reservations",
        "service_offer_items",
        "service_offers",
    ]:
        if table_name in _table_names():
            op.drop_table(table_name)
