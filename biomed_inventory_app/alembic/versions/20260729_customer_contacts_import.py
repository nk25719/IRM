"""customer contacts importer fields

Revision ID: 20260729_customer_contacts_import
Revises: 20260728_engineer_schedule
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa

revision = "20260729_customer_contacts_import"
down_revision = "20260728_engineer_schedule"
branch_labels = None
depends_on = None


CONTACT_COLUMNS = [
    sa.Column("client_site_id", sa.Integer()),
    sa.Column("manufacturer_id", sa.Integer()),
    sa.Column("supplier_id", sa.Integer()),
    sa.Column("first_name", sa.String(120)),
    sa.Column("last_name", sa.String(120)),
    sa.Column("display_name", sa.String(255)),
    sa.Column("normalized_email", sa.String(255)),
    sa.Column("role_title", sa.String(255)),
    sa.Column("department", sa.String(255)),
    sa.Column("phone_original", sa.String(120)),
    sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("email_domain", sa.String(255)),
    sa.Column("contact_type", sa.String(80), nullable=False, server_default="unknown"),
    sa.Column("organization_type", sa.String(80), nullable=False, server_default="unknown"),
    sa.Column("emails_exchanged", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("engagement_level", sa.String(40), nullable=False, server_default="low"),
    sa.Column("is_shared_inbox", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("is_automated_address", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
    sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("source", sa.String(120)),
    sa.Column("source_reference", sa.Text()),
    sa.Column("data_quality_status", sa.String(80), nullable=False, server_default="needs_review"),
    sa.Column("last_imported_at", sa.DateTime(timezone=True)),
    sa.Column("contact_owner_user_id", sa.Integer()),
    sa.Column("next_action", sa.Text()),
]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("contacts")}
    for column in CONTACT_COLUMNS:
        if column.name not in existing_columns:
            op.add_column("contacts", column)
    existing_indexes = {index["name"] for index in inspector.get_indexes("contacts")}
    if "ix_contacts_email_domain" not in existing_indexes:
        op.create_index("ix_contacts_email_domain", "contacts", ["email_domain"])
    if "ix_contacts_organization_type" not in existing_indexes:
        op.create_index("ix_contacts_organization_type", "contacts", ["organization_type"])
    if "ix_contacts_engagement_level" not in existing_indexes:
        op.create_index("ix_contacts_engagement_level", "contacts", ["engagement_level"])
    if "uq_contacts_normalized_email" not in existing_indexes:
        op.create_index("uq_contacts_normalized_email", "contacts", ["normalized_email"], unique=True)
    if not inspector.has_table("organization_domain_mappings"):
        op.create_table(
            "organization_domain_mappings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("domain", sa.String(255), nullable=False),
            sa.Column("organization_type", sa.String(80), nullable=False),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(50), nullable=False, server_default="approved"),
            sa.Column("notes", sa.Text()),
            sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("domain", name="uq_organization_domain_mappings_domain"),
        )
        op.create_index("ix_organization_domain_mappings_org", "organization_domain_mappings", ["organization_type", "organization_id"])
        op.create_index("ix_organization_domain_mappings_status", "organization_domain_mappings", ["status"])


def downgrade():
    op.drop_table("organization_domain_mappings")
    op.drop_index("uq_contacts_normalized_email", table_name="contacts")
    op.drop_index("ix_contacts_engagement_level", table_name="contacts")
    op.drop_index("ix_contacts_organization_type", table_name="contacts")
    op.drop_index("ix_contacts_email_domain", table_name="contacts")
    with op.batch_alter_table("contacts") as batch:
        for column in reversed(CONTACT_COLUMNS):
            batch.drop_column(column.name)
