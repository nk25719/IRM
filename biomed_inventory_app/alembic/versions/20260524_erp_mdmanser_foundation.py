"""ERP and MDManser foundation

Revision ID: 20260524_erp_mdmanser
Revises:
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

from app.database import Base
from app import erp_models  # noqa: F401

revision = "20260524_erp_mdmanser"
down_revision = None
branch_labels = None
depends_on = None


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


def clone_column(column):
    return sa.Column(
        column.name,
        column.type,
        primary_key=column.primary_key,
        nullable=False if column.primary_key else True,
        server_default=column.server_default,
    )


def create_or_extend_table(bind, table):
    if not has_table(bind, table.name):
        # Keep this foundation migration additive and friendly to the existing
        # SQLite startup sync. Application schemas enforce required fields.
        op.create_table(table.name, *[clone_column(column) for column in table.columns])
        return
    existing = columns(bind, table.name)
    for column in table.columns:
        if column.name not in existing:
            op.add_column(table.name, clone_column(column))


def create_indexes(bind, table):
    existing = indexes(bind, table.name)
    for index in table.indexes:
        if index.name not in existing:
            op.create_index(index.name, table.name, [expr.name for expr in index.expressions], unique=index.unique)


def upgrade():
    bind = op.get_bind()
    for table in Base.metadata.sorted_tables:
        create_or_extend_table(bind, table)
    for table in Base.metadata.sorted_tables:
        create_indexes(bind, table)


def downgrade():
    # Data-preserving downgrade. Existing legacy and imported ERP data are not dropped.
    pass
