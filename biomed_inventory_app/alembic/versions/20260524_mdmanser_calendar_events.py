"""MDManser calendar events

Revision ID: 20260524_mdmanser_calendar_events
Revises: 20260524_erp_mdmanser
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260524_mdmanser_calendar_events"
down_revision = "20260524_erp_mdmanser"
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


def add_missing_column(bind, table_name, column):
    if column.name not in columns(bind, table_name):
        op.add_column(table_name, column)


def create_missing_index(bind, name, table_name, columns_, unique=False):
    if name not in indexes(bind, table_name):
        op.create_index(name, table_name, columns_, unique=unique)


def upgrade():
    bind = op.get_bind()
    if not has_table(bind, "mdmanser_calendar_events"):
        op.create_table(
            "mdmanser_calendar_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source", sa.String(length=80), nullable=True),
            sa.Column("source_event_key", sa.String(length=64), nullable=True),
            sa.Column("event_type", sa.String(length=80), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("engineer_name", sa.String(length=255), nullable=True),
            sa.Column("call_reasons", sa.Text(), nullable=True),
            sa.Column("contract_reference", sa.String(length=120), nullable=True),
            sa.Column("client_name", sa.String(length=255), nullable=True),
            sa.Column("equipment_name", sa.String(length=255), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("raw_payload", sa.Text(), nullable=True),
            sa.Column("mapped_client_id", sa.Integer(), nullable=True),
            sa.Column("mapped_equipment_id", sa.Integer(), nullable=True),
            sa.Column("mapped_case_id", sa.Integer(), nullable=True),
            sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        )
    else:
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("source", sa.String(length=80), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("source_event_key", sa.String(length=64), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("event_type", sa.String(length=80), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("title", sa.String(length=255), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("engineer_name", sa.String(length=255), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("call_reasons", sa.Text(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("contract_reference", sa.String(length=120), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("client_name", sa.String(length=255), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("equipment_name", sa.String(length=255), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("start_date", sa.Date(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("end_date", sa.Date(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("raw_payload", sa.Text(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("mapped_client_id", sa.Integer(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("mapped_equipment_id", sa.Integer(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("mapped_case_id", sa.Integer(), nullable=True))
        add_missing_column(bind, "mdmanser_calendar_events", sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))
    create_missing_index(bind, "ix_mdmanser_calendar_events_source_event_key", "mdmanser_calendar_events", ["source_event_key"], unique=True)
    create_missing_index(bind, "ix_mdmanser_calendar_events_start_date", "mdmanser_calendar_events", ["start_date"])
    create_missing_index(bind, "ix_mdmanser_calendar_events_engineer_name", "mdmanser_calendar_events", ["engineer_name"])
    create_missing_index(bind, "ix_mdmanser_calendar_events_contract_reference", "mdmanser_calendar_events", ["contract_reference"])
    create_missing_index(bind, "ix_mdmanser_calendar_events_mapped_client_id", "mdmanser_calendar_events", ["mapped_client_id"])


def downgrade():
    # Data-preserving downgrade. Imported MDManser calendar data is not dropped.
    pass
