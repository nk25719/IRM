"""Repair equipment model master data foreign keys

Revision ID: 20260716_equipment_model_master_fks
Revises: 20260716_master_data_aliases
Create Date: 2026-07-16
"""
from alembic import op
import sqlalchemy as sa


revision = "20260716_equipment_model_master_fks"
down_revision = "20260716_master_data_aliases"
branch_labels = None
depends_on = None


def _fk_names(bind):
    inspector = sa.inspect(bind)
    return {fk.get("name") for fk in inspector.get_foreign_keys("equipment_models")}


def upgrade():
    bind = op.get_bind()
    names = _fk_names(bind)
    with op.batch_alter_table("equipment_models", recreate="always") as batch:
        if "fk_equipment_models_manufacturer_id" not in names:
            batch.create_foreign_key("fk_equipment_models_manufacturer_id", "manufacturers", ["manufacturer_id"], ["id"], ondelete="SET NULL")
        if "fk_equipment_models_equipment_category_id" not in names:
            batch.create_foreign_key("fk_equipment_models_equipment_category_id", "equipment_categories", ["equipment_category_id"], ["id"], ondelete="SET NULL")


def downgrade():
    names = _fk_names(op.get_bind())
    with op.batch_alter_table("equipment_models", recreate="always") as batch:
        if "fk_equipment_models_equipment_category_id" in names:
            batch.drop_constraint("fk_equipment_models_equipment_category_id", type_="foreignkey")
        if "fk_equipment_models_manufacturer_id" in names:
            batch.drop_constraint("fk_equipment_models_manufacturer_id", type_="foreignkey")
