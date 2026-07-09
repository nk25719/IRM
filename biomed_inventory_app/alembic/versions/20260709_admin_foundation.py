"""Admin database foundation

Revision ID: 20260709_admin_foundation
Revises: 20260703_quotation_generator
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa


revision = "20260709_admin_foundation"
down_revision = "20260703_quotation_generator"
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

    if not has_table(bind, "roles"):
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=80), nullable=False, unique=True),
            sa.Column("description", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not has_table(bind, "permissions"):
        op.create_table(
            "permissions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=120), nullable=False, unique=True),
            sa.Column("description", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not has_table(bind, "role_permissions"):
        op.create_table(
            "role_permissions",
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("permission_id", sa.Integer(), nullable=False),
            sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_permission"),
        )

    if not has_table(bind, "user_roles"):
        op.create_table(
            "user_roles",
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        )

    if not has_table(bind, "import_batches"):
        op.create_table(
            "import_batches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_type", sa.String(length=80)),
            sa.Column("target_table", sa.String(length=120)),
            sa.Column("filename", sa.String(length=255)),
            sa.Column("status", sa.String(length=40), server_default="preview"),
            sa.Column("total_rows", sa.Integer(), server_default="0"),
            sa.Column("valid_rows", sa.Integer(), server_default="0"),
            sa.Column("error_rows", sa.Integer(), server_default="0"),
            sa.Column("saved_rows", sa.Integer(), server_default="0"),
            sa.Column("created_by", sa.String(length=120)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("committed_at", sa.DateTime(timezone=True)),
            sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
            sa.Column("mapping_json", sa.Text()),
            sa.Column("preview_json", sa.Text()),
            sa.Column("source_columns_json", sa.Text()),
            sa.Column("notes", sa.Text()),
        )
    else:
        add_missing_columns(
            bind,
            "import_batches",
            [
                sa.Column("target_table", sa.String(length=120)),
                sa.Column("mapping_json", sa.Text()),
                sa.Column("preview_json", sa.Text()),
                sa.Column("source_columns_json", sa.Text()),
                sa.Column("saved_rows", sa.Integer(), server_default="0"),
            ],
        )

    if not has_table(bind, "import_errors"):
        op.create_table(
            "import_errors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer()),
            sa.Column("row_no", sa.Integer()),
            sa.Column("field", sa.String(length=120)),
            sa.Column("error_message", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if not has_table(bind, "audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=120)),
            sa.Column("action", sa.String(length=120)),
            sa.Column("table_name", sa.String(length=120)),
            sa.Column("record_id", sa.Integer()),
            sa.Column("batch_id", sa.Integer()),
            sa.Column("old_value", sa.Text()),
            sa.Column("new_value", sa.Text()),
            sa.Column("notes", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    else:
        add_missing_columns(
            bind,
            "audit_log",
            [
                sa.Column("username", sa.String(length=120)),
                sa.Column("table_name", sa.String(length=120)),
                sa.Column("record_id", sa.Integer()),
                sa.Column("batch_id", sa.Integer()),
            ],
        )

    create_index_if_missing(bind, "ix_import_batches_target_table", "import_batches", ["target_table"])
    create_index_if_missing(bind, "ix_import_errors_batch_id", "import_errors", ["batch_id"])
    create_index_if_missing(bind, "ix_audit_log_table_record", "audit_log", ["table_name", "record_id"])


def downgrade():
    pass
