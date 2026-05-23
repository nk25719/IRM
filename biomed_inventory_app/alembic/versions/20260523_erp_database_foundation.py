"""ERP database foundation

Revision ID: 20260523_erp_foundation
Revises:
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

from app.schema_compat import LEGACY_STARTUP_COMPAT_COLUMNS

revision = "20260523_erp_foundation"
down_revision = None
branch_labels = None
depends_on = None


def has_table(bind, table_name):
    return sa.inspect(bind).has_table(table_name)


def columns(bind, table_name):
    if not has_table(bind, table_name):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(table_name)}


def add_col(bind, table, column):
    if column.name not in columns(bind, table):
        op.add_column(table, column)


def create_index_if_missing(bind, name, table, cols, unique=False):
    if not has_table(bind, table):
        return
    existing = {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, cols, unique=unique)



def create_fk_if_missing(bind, name, source_table, referent_table, local_cols, remote_cols, ondelete=None):
    if bind.dialect.name == "sqlite" or not has_table(bind, source_table) or not has_table(bind, referent_table):
        return
    existing = {fk.get("name") for fk in sa.inspect(bind).get_foreign_keys(source_table)}
    if name not in existing:
        op.create_foreign_key(name, source_table, referent_table, local_cols, remote_cols, ondelete=ondelete)


def compat_type(sqlite_type):
    normalized = sqlite_type.upper()
    if normalized.startswith("INTEGER"):
        return sa.Integer()
    if normalized.startswith("REAL"):
        return sa.Float()
    return sa.Text()


def compat_default(sqlite_type):
    marker = " DEFAULT "
    normalized = sqlite_type.upper()
    if marker not in normalized:
        return None
    default = sqlite_type[normalized.index(marker) + len(marker):].strip()
    if default.startswith("'") and default.endswith("'"):
        return default[1:-1]
    return default


def add_legacy_startup_compat_columns(bind):
    for table, compat_columns in LEGACY_STARTUP_COMPAT_COLUMNS.items():
        if not has_table(bind, table):
            continue
        for name, sqlite_type in compat_columns.items():
            add_col(bind, table, sa.Column(name, compat_type(sqlite_type), server_default=compat_default(sqlite_type)))


def upgrade():
    bind = op.get_bind()

    if not has_table(bind, "clients"):
        op.create_table(
            "clients",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("location", sa.String(255)),
            sa.Column("address", sa.Text()),
            sa.Column("status", sa.String(50), nullable=False, server_default="active"),
            sa.Column("financial_status", sa.String(50), nullable=False, server_default="good_standing"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    else:
        add_col(bind, "clients", sa.Column("location", sa.String(255)))
        add_col(bind, "clients", sa.Column("financial_status", sa.String(50), server_default="good_standing"))
        add_col(bind, "clients", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        add_col(bind, "clients", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        if "city" in columns(bind, "clients"):
            op.execute("UPDATE clients SET location = COALESCE(location, city)")

    if not has_table(bind, "departments"):
        op.create_table(
            "departments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("floor_location", sa.String(255)),
            sa.Column("contact_name", sa.String(255)),
            sa.Column("phone", sa.String(50)),
            sa.Column("email", sa.String(255)),
            sa.Column("notes", sa.Text()),
        )
    else:
        add_col(bind, "departments", sa.Column("name", sa.String(255)))
        add_col(bind, "departments", sa.Column("contact_name", sa.String(255)))
        if "department_name" in columns(bind, "departments"):
            op.execute("UPDATE departments SET name = COALESCE(name, department_name)")
        if "main_contact_name" in columns(bind, "departments"):
            op.execute("UPDATE departments SET contact_name = COALESCE(contact_name, main_contact_name)")
    create_index_if_missing(bind, "ix_departments_client_id", "departments", ["client_id"])

    if not has_table(bind, "contacts"):
        op.create_table(
            "contacts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("title", sa.String(255)),
            sa.Column("phone", sa.String(50)),
            sa.Column("email", sa.String(255)),
            sa.Column("notes", sa.Text()),
        )
    else:
        add_col(bind, "contacts", sa.Column("title", sa.String(255)))
        if "role" in columns(bind, "contacts"):
            op.execute("UPDATE contacts SET title = COALESCE(title, role)")
    create_index_if_missing(bind, "ix_contacts_client_id", "contacts", ["client_id"])
    create_index_if_missing(bind, "ix_contacts_department_id", "contacts", ["department_id"])

    if not has_table(bind, "equipment_models"):
        op.create_table("equipment_models", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("manufacturer", sa.String(255)), sa.Column("model", sa.String(255)))

    if not has_table(bind, "inventory_items"):
        op.create_table(
            "inventory_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pn", sa.String(255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("category", sa.String(50), nullable=False, server_default="spare_part"),
            sa.Column("manufacturer", sa.String(255)),
            sa.Column("minimum_qty", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("physical_qty", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reserved_qty", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("available_qty", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("location", sa.String(255)),
            sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        )
    else:
        for col in [sa.Column("category", sa.String(50), server_default="spare_part"), sa.Column("manufacturer", sa.String(255)), sa.Column("minimum_qty", sa.Integer(), server_default="0"), sa.Column("reserved_qty", sa.Integer(), server_default="0"), sa.Column("available_qty", sa.Integer(), server_default="0"), sa.Column("status", sa.String(50), server_default="active")]:
            add_col(bind, "inventory_items", col)
    create_index_if_missing(bind, "ix_inventory_items_pn", "inventory_items", ["pn"])

    if not has_table(bind, "equipment"):
        op.create_table(
            "equipment",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
            sa.Column("equipment_model_id", sa.Integer(), sa.ForeignKey("equipment_models.id", ondelete="SET NULL")),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("manufacturer", sa.String(255)),
            sa.Column("model", sa.String(255)),
            sa.Column("serial_number", sa.String(255)),
            sa.Column("asset_tag", sa.String(255)),
            sa.Column("installation_date", sa.Date()),
            sa.Column("warranty_start_date", sa.Date()),
            sa.Column("warranty_end_date", sa.Date()),
            sa.Column("status", sa.String(50), nullable=False, server_default="active"),
            sa.Column("risk_classification", sa.String(80)),
            sa.Column("life_support", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("pm_frequency", sa.String(80)),
            sa.Column("last_pm_date", sa.Date()),
            sa.Column("next_pm_date", sa.Date()),
            sa.Column("calibration_required", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("calibration_due_date", sa.Date()),
        )
    else:
        for col in [sa.Column("equipment_model_id", sa.Integer()), sa.Column("name", sa.String(255)), sa.Column("installation_date", sa.Date()), sa.Column("warranty_start_date", sa.Date()), sa.Column("warranty_end_date", sa.Date()), sa.Column("risk_classification", sa.String(80)), sa.Column("life_support", sa.Boolean(), server_default=sa.false()), sa.Column("pm_frequency", sa.String(80)), sa.Column("last_pm_date", sa.Date()), sa.Column("next_pm_date", sa.Date()), sa.Column("calibration_required", sa.Boolean(), server_default=sa.false()), sa.Column("calibration_due_date", sa.Date())]:
            add_col(bind, "equipment", col)
        if "name" in columns(bind, "equipment"):
            op.execute("UPDATE equipment SET name = COALESCE(name, model, asset_tag, serial_number, 'Equipment')")
    create_index_if_missing(bind, "ix_equipment_client_id", "equipment", ["client_id"])
    create_index_if_missing(bind, "ix_equipment_department_id", "equipment", ["department_id"])
    create_index_if_missing(bind, "ix_equipment_serial_number", "equipment", ["serial_number"])

    if not has_table(bind, "contracts"):
        op.create_table("contracts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False), sa.Column("contract_type", sa.String(80), nullable=False), sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()), sa.Column("status", sa.String(50), nullable=False, server_default="active"), sa.Column("coverage_notes", sa.Text()))
    create_index_if_missing(bind, "ix_contracts_client_id", "contracts", ["client_id"])

    if not has_table(bind, "cases"):
        op.create_table(
            "cases",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
            sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
            sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL")),
            sa.Column("parent_case_reference", sa.String(80), nullable=False, unique=True),
            sa.Column("case_type", sa.String(80), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("status", sa.String(50), nullable=False, server_default="open"),
            sa.Column("priority", sa.String(50), nullable=False, server_default="normal"),
            sa.Column("blocked_reason", sa.Text()),
            sa.Column("responsible_user_id", sa.Integer()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    else:
        for col in [sa.Column("department_id", sa.Integer()), sa.Column("parent_case_reference", sa.String(80)), sa.Column("title", sa.String(255)), sa.Column("description", sa.Text()), sa.Column("blocked_reason", sa.Text()), sa.Column("responsible_user_id", sa.Integer())]:
            add_col(bind, "cases", col)
        if "case_no" in columns(bind, "cases"):
            op.execute("UPDATE cases SET parent_case_reference = COALESCE(parent_case_reference, case_no)")
        if "notes" in columns(bind, "cases"):
            op.execute("UPDATE cases SET description = COALESCE(description, notes)")
        op.execute("UPDATE cases SET title = COALESCE(title, case_type, parent_case_reference, 'Case')")
    create_index_if_missing(bind, "ix_cases_client_id", "cases", ["client_id"])
    create_index_if_missing(bind, "ix_cases_department_id", "cases", ["department_id"])
    create_index_if_missing(bind, "ix_cases_parent_case_reference", "cases", ["parent_case_reference"], unique=True)

    if not has_table(bind, "case_items"):
        op.create_table("case_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False), sa.Column("item_type", sa.String(80), nullable=False), sa.Column("description", sa.Text()), sa.Column("requested_qty", sa.Integer(), nullable=False, server_default="1"), sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("status", sa.String(50), nullable=False, server_default="open"), sa.Column("procurement_status", sa.String(50), nullable=False, server_default="not_ordered"), sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="SET NULL")))
    else:
        for col in [sa.Column("item_type", sa.String(80)), sa.Column("description", sa.Text()), sa.Column("requested_qty", sa.Integer(), server_default="1"), sa.Column("unit_price", sa.Numeric(12, 2), server_default="0"), sa.Column("status", sa.String(50), server_default="open")]:
            add_col(bind, "case_items", col)
        if "requested_item" in columns(bind, "case_items"):
            op.execute("UPDATE case_items SET description = COALESCE(description, requested_item)")
        if "quantity" in columns(bind, "case_items"):
            op.execute("UPDATE case_items SET requested_qty = COALESCE(requested_qty, quantity)")
    create_index_if_missing(bind, "ix_case_items_case_id", "case_items", ["case_id"])

    # Additive updates for remaining ERP tables. Create them when absent; otherwise add only missing columns.
    if not has_table(bind, "client_activities"):
        op.create_table("client_activities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False), sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")), sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")), sa.Column("activity_type", sa.String(40), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("status", sa.String(50), nullable=False, server_default="open"), sa.Column("date", sa.Date()), sa.Column("created_by", sa.Integer()))
    else:
        for col in [sa.Column("description", sa.Text()), sa.Column("date", sa.Date()), sa.Column("created_by", sa.Integer())]:
            add_col(bind, "client_activities", col)
        if "activity_date" in columns(bind, "client_activities"):
            op.execute("UPDATE client_activities SET date = COALESCE(date, activity_date)")
        if "notes" in columns(bind, "client_activities"):
            op.execute("UPDATE client_activities SET description = COALESCE(description, notes)")

    if not has_table(bind, "procurement_requests"):
        op.create_table("procurement_requests", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")), sa.Column("case_item_id", sa.Integer(), sa.ForeignKey("case_items.id", ondelete="SET NULL")), sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="SET NULL")), sa.Column("requested_qty", sa.Integer(), nullable=False, server_default="0"), sa.Column("shortage_qty", sa.Integer(), nullable=False, server_default="0"), sa.Column("procurement_status", sa.String(50), nullable=False, server_default="not_ordered"), sa.Column("supplier", sa.String(255)), sa.Column("expected_date", sa.Date()))
    else:
        for col in [sa.Column("case_id", sa.Integer()), sa.Column("case_item_id", sa.Integer()), sa.Column("expected_date", sa.Date())]:
            add_col(bind, "procurement_requests", col)
        if "expected_delivery_date" in columns(bind, "procurement_requests"):
            op.execute("UPDATE procurement_requests SET expected_date = COALESCE(expected_date, expected_delivery_date)")

    if not has_table(bind, "service_calls"):
        op.create_table("service_calls", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False), sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")), sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL")), sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")), sa.Column("call_type", sa.String(80), nullable=False), sa.Column("priority", sa.String(50), nullable=False, server_default="normal"), sa.Column("status", sa.String(50), nullable=False, server_default="open"), sa.Column("blocked_reason", sa.Text()), sa.Column("assigned_engineer_id", sa.Integer()), sa.Column("request_date", sa.Date()), sa.Column("due_date", sa.Date()))
    else:
        for col in [sa.Column("department_id", sa.Integer()), sa.Column("case_id", sa.Integer()), sa.Column("call_type", sa.String(80)), sa.Column("priority", sa.String(50), server_default="normal"), sa.Column("blocked_reason", sa.Text()), sa.Column("assigned_engineer_id", sa.Integer()), sa.Column("request_date", sa.Date()), sa.Column("due_date", sa.Date())]:
            add_col(bind, "service_calls", col)
        if "opened_at" in columns(bind, "service_calls"):
            op.execute("UPDATE service_calls SET request_date = COALESCE(request_date, opened_at)")

    if not has_table(bind, "pm_tasks"):
        op.create_table("pm_tasks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False), sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")), sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL")), sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="SET NULL")), sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")), sa.Column("scheduled_date", sa.Date()), sa.Column("completed_date", sa.Date()), sa.Column("status", sa.String(50), nullable=False, server_default="scheduled"), sa.Column("assigned_engineer_id", sa.Integer()))
    else:
        for col in [sa.Column("client_id", sa.Integer()), sa.Column("department_id", sa.Integer()), sa.Column("equipment_id", sa.Integer()), sa.Column("contract_id", sa.Integer()), sa.Column("case_id", sa.Integer()), sa.Column("scheduled_date", sa.Date()), sa.Column("completed_date", sa.Date()), sa.Column("assigned_engineer_id", sa.Integer())]:
            add_col(bind, "pm_tasks", col)
        if "due_date" in columns(bind, "pm_tasks"):
            op.execute("UPDATE pm_tasks SET scheduled_date = COALESCE(scheduled_date, due_date)")

    if not has_table(bind, "warranties"):
        op.create_table("warranties", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False), sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False), sa.Column("start_date", sa.Date()), sa.Column("end_date", sa.Date()), sa.Column("status", sa.String(50), nullable=False, server_default="active"), sa.Column("coverage_notes", sa.Text()))
    if not has_table(bind, "invoices"):
        op.create_table("invoices", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False), sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")), sa.Column("parent_case_reference", sa.String(80)), sa.Column("invoice_number", sa.String(80), nullable=False), sa.Column("status", sa.String(50), nullable=False, server_default="draft"), sa.Column("total_amount", sa.Numeric(12, 2), nullable=False, server_default="0"), sa.Column("due_date", sa.Date()), sa.Column("paid_date", sa.Date()))

    add_legacy_startup_compat_columns(bind)
    create_index_if_missing(
        bind,
        "ux_procurement_requests_customer_request_item_id",
        "procurement_requests",
        ["customer_request_item_id"],
        unique=True,
    )

    for table, cols in {
        "client_activities": ["client_id", "department_id", "case_id"],
        "procurement_requests": ["case_id", "case_item_id"],
        "service_calls": ["client_id", "department_id", "case_id"],
        "pm_tasks": ["client_id", "department_id", "case_id"],
        "warranties": ["client_id"],
        "invoices": ["client_id", "case_id", "parent_case_reference"],
        "sales_requests": ["offer_reference"],
    }.items():
        for col in cols:
            if col in columns(bind, table):
                create_index_if_missing(bind, f"ix_{table}_{col}", table, [col])


    # PostgreSQL foreign keys for legacy tables that already existed before this migration.
    create_fk_if_missing(bind, "fk_departments_client_id_clients", "departments", "clients", ["client_id"], ["id"], ondelete="CASCADE")
    create_fk_if_missing(bind, "fk_contacts_client_id_clients", "contacts", "clients", ["client_id"], ["id"], ondelete="CASCADE")
    create_fk_if_missing(bind, "fk_contacts_department_id_departments", "contacts", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_cases_client_id_clients", "cases", "clients", ["client_id"], ["id"], ondelete="CASCADE")
    create_fk_if_missing(bind, "fk_cases_department_id_departments", "cases", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_cases_equipment_id_equipment", "cases", "equipment", ["equipment_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_case_items_case_id_cases", "case_items", "cases", ["case_id"], ["id"], ondelete="CASCADE")
    create_fk_if_missing(bind, "fk_case_items_inventory_item_id_inventory_items", "case_items", "inventory_items", ["inventory_item_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_equipment_client_id_clients", "equipment", "clients", ["client_id"], ["id"], ondelete="CASCADE")
    create_fk_if_missing(bind, "fk_equipment_department_id_departments", "equipment", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_procurement_requests_case_id_cases", "procurement_requests", "cases", ["case_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_procurement_requests_case_item_id_case_items", "procurement_requests", "case_items", ["case_item_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_service_calls_case_id_cases", "service_calls", "cases", ["case_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_pm_tasks_contract_id_contracts", "pm_tasks", "contracts", ["contract_id"], ["id"], ondelete="SET NULL")
    create_fk_if_missing(bind, "fk_invoices_case_id_cases", "invoices", "cases", ["case_id"], ["id"], ondelete="SET NULL")

def downgrade():
    # Data-preserving downgrade: remove only tables created exclusively by this foundation when desired.
    # Existing legacy tables are intentionally not dropped.
    for table in ["invoices", "warranties", "contracts"]:
        op.drop_table(table)
