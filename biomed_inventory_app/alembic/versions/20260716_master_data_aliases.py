"""Master data aliases

Revision ID: 20260716_master_data_aliases
Revises: 20260716_database_foundation
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa


revision = "20260716_master_data_aliases"
down_revision = "20260716_database_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manufacturer_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("manufacturer_id", sa.Integer(), sa.ForeignKey("manufacturers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=120)),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("normalized_alias", name="uq_manufacturer_aliases_normalized_alias"),
    )
    op.create_index("ix_manufacturer_aliases_manufacturer_id", "manufacturer_aliases", ["manufacturer_id"])
    op.create_index("ix_manufacturer_aliases_normalized_alias", "manufacturer_aliases", ["normalized_alias"])
    op.create_index("ix_manufacturer_aliases_is_verified", "manufacturer_aliases", ["is_verified"])

    op.create_table(
        "equipment_category_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_category_id", sa.Integer(), sa.ForeignKey("equipment_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=120)),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("normalized_alias", name="uq_equipment_category_aliases_normalized_alias"),
    )
    op.create_index("ix_equipment_category_aliases_equipment_category_id", "equipment_category_aliases", ["equipment_category_id"])
    op.create_index("ix_equipment_category_aliases_normalized_alias", "equipment_category_aliases", ["normalized_alias"])
    op.create_index("ix_equipment_category_aliases_is_verified", "equipment_category_aliases", ["is_verified"])


def downgrade():
    op.drop_index("ix_equipment_category_aliases_is_verified", table_name="equipment_category_aliases")
    op.drop_index("ix_equipment_category_aliases_normalized_alias", table_name="equipment_category_aliases")
    op.drop_index("ix_equipment_category_aliases_equipment_category_id", table_name="equipment_category_aliases")
    op.drop_table("equipment_category_aliases")
    op.drop_index("ix_manufacturer_aliases_is_verified", table_name="manufacturer_aliases")
    op.drop_index("ix_manufacturer_aliases_normalized_alias", table_name="manufacturer_aliases")
    op.drop_index("ix_manufacturer_aliases_manufacturer_id", table_name="manufacturer_aliases")
    op.drop_table("manufacturer_aliases")
