"""Database foundation

Revision ID: 20260716_database_foundation
Revises: 20260709_aftermarket_service_reports
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260716_database_foundation"
down_revision = "20260709_aftermarket_service_reports"
branch_labels = None
depends_on = None


JSON_VALUE = sa.JSON().with_variant(postgresql.JSONB, "postgresql")


def has_table(bind, table_name):
    return sa.inspect(bind).has_table(table_name)


def columns(bind, table_name):
    if not has_table(bind, table_name):
        return set()
    return {column["name"] for column in sa.inspect(bind).get_columns(table_name)}


def indexes(bind, table_name):
    if not has_table(bind, table_name):
        return set()
    return {index["name"] for index in sa.inspect(bind).get_indexes(table_name)}


def add_missing_column(bind, table_name, column):
    if column.name not in columns(bind, table_name):
        op.add_column(table_name, column)


def create_index_if_missing(bind, name, table_name, fields, unique=False):
    if name not in indexes(bind, table_name):
        op.create_index(name, table_name, fields, unique=unique)


def drop_index_if_exists(bind, name, table_name):
    if has_table(bind, table_name) and name in indexes(bind, table_name):
        op.drop_index(name, table_name=table_name)


def ensure_import_batch_timestamps(bind):
    existing = columns(bind, "import_batches")
    missing = [name for name in ("created_at", "updated_at") if name not in existing]
    if not missing:
        return
    with op.batch_alter_table("import_batches", recreate="always") as batch:
        if "created_at" in missing:
            batch.add_column(sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
        if "updated_at" in missing:
            batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def upgrade():
    bind = op.get_bind()

    if not has_table(bind, "manufacturers"):
        op.create_table(
            "manufacturers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=80), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("legal_name", sa.String(length=255)),
            sa.Column("website", sa.String(length=500)),
            sa.Column("email", sa.String(length=255)),
            sa.Column("phone", sa.String(length=80)),
            sa.Column("country_code", sa.String(length=2)),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("code", name="uq_manufacturers_code"),
            sa.UniqueConstraint("normalized_name", name="uq_manufacturers_normalized_name"),
        )
    create_index_if_missing(bind, "ix_manufacturers_name", "manufacturers", ["name"])
    create_index_if_missing(bind, "ix_manufacturers_status", "manufacturers", ["status"])

    if not has_table(bind, "suppliers"):
        op.create_table(
            "suppliers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("supplier_code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("legal_name", sa.String(length=255)),
            sa.Column("email", sa.String(length=255)),
            sa.Column("phone", sa.String(length=80)),
            sa.Column("website", sa.String(length=500)),
            sa.Column("tax_number", sa.String(length=120)),
            sa.Column("country_code", sa.String(length=2)),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("supplier_code", name="uq_suppliers_supplier_code"),
        )
    create_index_if_missing(bind, "ix_suppliers_name", "suppliers", ["name"])
    create_index_if_missing(bind, "ix_suppliers_status", "suppliers", ["status"])

    if not has_table(bind, "client_sites"):
        op.create_table(
            "client_sites",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("site_code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("address_line_1", sa.String(length=255)),
            sa.Column("address_line_2", sa.String(length=255)),
            sa.Column("city", sa.String(length=120)),
            sa.Column("region", sa.String(length=120)),
            sa.Column("postal_code", sa.String(length=40)),
            sa.Column("country_code", sa.String(length=2)),
            sa.Column("phone", sa.String(length=80)),
            sa.Column("email", sa.String(length=255)),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("client_id", "site_code", name="uq_client_sites_client_site_code"),
        )
    create_index_if_missing(bind, "ix_client_sites_client_id", "client_sites", ["client_id"])
    create_index_if_missing(bind, "ix_client_sites_city", "client_sites", ["city"])
    create_index_if_missing(bind, "ix_client_sites_status", "client_sites", ["status"])

    if not has_table(bind, "locations"):
        op.create_table(
            "locations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="SET NULL")),
            sa.Column("site_id", sa.Integer(), sa.ForeignKey("client_sites.id", ondelete="SET NULL")),
            sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
            sa.Column("parent_location_id", sa.Integer(), sa.ForeignKey("locations.id", ondelete="SET NULL")),
            sa.Column("location_code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("location_type", sa.String(length=80), nullable=False, server_default="site_area"),
            sa.Column("floor", sa.String(length=80)),
            sa.Column("room", sa.String(length=80)),
            sa.Column("description", sa.Text()),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("site_id", "location_code", name="uq_locations_site_location_code"),
        )
    for name, fields in [
        ("ix_locations_client_id", ["client_id"]),
        ("ix_locations_site_id", ["site_id"]),
        ("ix_locations_department_id", ["department_id"]),
        ("ix_locations_parent_location_id", ["parent_location_id"]),
        ("ix_locations_status", ["status"]),
    ]:
        create_index_if_missing(bind, name, "locations", fields)

    if not has_table(bind, "equipment_categories"):
        op.create_table(
            "equipment_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("normalized_name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("parent_category_id", sa.Integer(), sa.ForeignKey("equipment_categories.id", ondelete="SET NULL")),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True)),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("code", name="uq_equipment_categories_code"),
            sa.UniqueConstraint("parent_category_id", "normalized_name", name="uq_equipment_categories_parent_name"),
        )
    create_index_if_missing(bind, "ix_equipment_categories_parent_category_id", "equipment_categories", ["parent_category_id"])
    create_index_if_missing(bind, "ix_equipment_categories_status", "equipment_categories", ["status"])

    equipment_model_columns = columns(bind, "equipment_models")
    if "manufacturer_id" not in equipment_model_columns or "equipment_category_id" not in equipment_model_columns:
        with op.batch_alter_table("equipment_models") as batch:
            if "manufacturer_id" not in equipment_model_columns:
                batch.add_column(sa.Column("manufacturer_id", sa.Integer(), nullable=True))
            if "equipment_category_id" not in equipment_model_columns:
                batch.add_column(sa.Column("equipment_category_id", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_equipment_models_manufacturer_id", "manufacturers", ["manufacturer_id"], ["id"], ondelete="SET NULL")
            batch.create_foreign_key("fk_equipment_models_equipment_category_id", "equipment_categories", ["equipment_category_id"], ["id"], ondelete="SET NULL")
    create_index_if_missing(bind, "ix_equipment_models_manufacturer_id", "equipment_models", ["manufacturer_id"])
    create_index_if_missing(bind, "ix_equipment_models_equipment_category_id", "equipment_models", ["equipment_category_id"])

    import_batch_simple_columns = [
        sa.Column("source_type", sa.String(length=80)),
        sa.Column("source_filename", sa.String(length=255)),
        sa.Column("source_checksum", sa.String(length=128)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
    ]
    for column in import_batch_simple_columns:
        add_missing_column(bind, "import_batches", column)
    ensure_import_batch_timestamps(bind)
    if "imported_by_id" not in columns(bind, "import_batches"):
        with op.batch_alter_table("import_batches") as batch:
            batch.add_column(sa.Column("imported_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_import_batches_imported_by_id")))
    for name, fields in [
        ("ix_import_batches_source_filename", ["source_filename"]),
        ("ix_import_batches_source_checksum", ["source_checksum"]),
        ("ix_import_batches_status", ["status"]),
        ("ix_import_batches_started_at", ["started_at"]),
    ]:
        create_index_if_missing(bind, name, "import_batches", fields)

    if not has_table(bind, "import_rows"):
        op.create_table(
            "import_rows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("raw_data", JSON_VALUE),
            sa.Column("normalized_data", JSON_VALUE),
            sa.Column("processing_status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("matched_client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="SET NULL")),
            sa.Column("matched_department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="SET NULL")),
            sa.Column("matched_equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="SET NULL")),
            sa.Column("matched_case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="SET NULL")),
            sa.Column("error_message", sa.Text()),
            sa.Column("warning_message", sa.Text()),
            sa.Column("processed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("import_batch_id", "row_number", name="uq_import_rows_batch_row_number"),
        )
    for name, fields in [
        ("ix_import_rows_import_batch_id", ["import_batch_id"]),
        ("ix_import_rows_processing_status", ["processing_status"]),
        ("ix_import_rows_matched_client_id", ["matched_client_id"]),
        ("ix_import_rows_matched_equipment_id", ["matched_equipment_id"]),
    ]:
        create_index_if_missing(bind, name, "import_rows", fields)

    if not has_table(bind, "data_validation_errors"):
        op.create_table(
            "data_validation_errors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("import_row_id", sa.Integer(), sa.ForeignKey("import_rows.id", ondelete="RESTRICT")),
            sa.Column("field_name", sa.String(length=120)),
            sa.Column("raw_value", sa.Text()),
            sa.Column("error_code", sa.String(length=120), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(length=50), nullable=False, server_default="error"),
            sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for name, fields in [
        ("ix_data_validation_errors_import_batch_id", ["import_batch_id"]),
        ("ix_data_validation_errors_import_row_id", ["import_row_id"]),
        ("ix_data_validation_errors_severity", ["severity"]),
        ("ix_data_validation_errors_is_resolved", ["is_resolved"]),
    ]:
        create_index_if_missing(bind, name, "data_validation_errors", fields)

    if not has_table(bind, "audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("entity_type", sa.String(length=120), nullable=False),
            sa.Column("entity_id", sa.String(length=120)),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("request_id", sa.String(length=120)),
            sa.Column("source", sa.String(length=120)),
            sa.Column("old_values", JSON_VALUE),
            sa.Column("new_values", JSON_VALUE),
            sa.Column("metadata", JSON_VALUE),
            sa.Column("ip_address", sa.String(length=80)),
            sa.Column("user_agent", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for name, fields in [
        ("ix_audit_events_entity", ["entity_type", "entity_id"]),
        ("ix_audit_events_user_id", ["user_id"]),
        ("ix_audit_events_event_type", ["event_type"]),
        ("ix_audit_events_created_at", ["created_at"]),
        ("ix_audit_events_entity_created_at", ["entity_type", "entity_id", "created_at"]),
    ]:
        create_index_if_missing(bind, name, "audit_events", fields)

    if not has_table(bind, "status_history"):
        op.create_table(
            "status_history",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("entity_type", sa.String(length=120), nullable=False),
            sa.Column("entity_id", sa.String(length=120), nullable=False),
            sa.Column("previous_status", sa.String(length=80)),
            sa.Column("new_status", sa.String(length=80), nullable=False),
            sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("reason", sa.Text()),
            sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("previous_status IS NULL OR previous_status != new_status", name="ck_status_history_status_changed"),
        )
    create_index_if_missing(bind, "ix_status_history_entity", "status_history", ["entity_type", "entity_id"])
    create_index_if_missing(bind, "ix_status_history_changed_at", "status_history", ["changed_at"])


def downgrade():
    bind = op.get_bind()
    for name, table in [
        ("ix_status_history_changed_at", "status_history"),
        ("ix_status_history_entity", "status_history"),
        ("ix_audit_events_entity_created_at", "audit_events"),
        ("ix_audit_events_created_at", "audit_events"),
        ("ix_audit_events_event_type", "audit_events"),
        ("ix_audit_events_user_id", "audit_events"),
        ("ix_audit_events_entity", "audit_events"),
        ("ix_data_validation_errors_is_resolved", "data_validation_errors"),
        ("ix_data_validation_errors_severity", "data_validation_errors"),
        ("ix_data_validation_errors_import_row_id", "data_validation_errors"),
        ("ix_data_validation_errors_import_batch_id", "data_validation_errors"),
        ("ix_import_rows_matched_equipment_id", "import_rows"),
        ("ix_import_rows_matched_client_id", "import_rows"),
        ("ix_import_rows_processing_status", "import_rows"),
        ("ix_import_rows_import_batch_id", "import_rows"),
    ]:
        drop_index_if_exists(bind, name, table)

    for name in ["ix_equipment_models_equipment_category_id", "ix_equipment_models_manufacturer_id"]:
        drop_index_if_exists(bind, name, "equipment_models")
    if has_table(bind, "equipment_models"):
        existing = columns(bind, "equipment_models")
        with op.batch_alter_table("equipment_models") as batch:
            if "equipment_category_id" in existing:
                batch.drop_column("equipment_category_id")
            if "manufacturer_id" in existing:
                batch.drop_column("manufacturer_id")

    for name in [
        "ix_import_batches_started_at",
        "ix_import_batches_status",
        "ix_import_batches_source_checksum",
        "ix_import_batches_source_filename",
    ]:
        drop_index_if_exists(bind, name, "import_batches")

    if has_table(bind, "import_batches"):
        existing = columns(bind, "import_batches")
        with op.batch_alter_table("import_batches") as batch:
            for column in ["updated_at", "created_at", "failed_rows", "successful_rows", "processed_rows", "completed_at", "started_at", "imported_by_id", "source_checksum", "source_filename", "source_type"]:
                if column in existing:
                    batch.drop_column(column)

    for table in ["status_history", "audit_events", "data_validation_errors", "import_rows", "locations", "client_sites", "equipment_categories", "suppliers", "manufacturers"]:
        if has_table(bind, table):
            op.drop_table(table)
