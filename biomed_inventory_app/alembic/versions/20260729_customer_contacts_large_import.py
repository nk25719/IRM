"""customer contacts large import jobs

Revision ID: 20260729_customer_contacts_large_import
Revises: 20260729_customer_contacts_import
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa

revision = "20260729_customer_contacts_large_import"
down_revision = "20260729_customer_contacts_import"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_contact_import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dataset_key", sa.String(120), nullable=False, server_default="customer_contacts"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("stored_file_path", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_checksum", sa.String(128), nullable=False),
        sa.Column("status", sa.String(80), nullable=False, server_default="uploaded"),
        sa.Column("phase", sa.String(80), nullable=False, server_default="file_validation"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_batch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("last_processed_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_completed_batch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(120)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failed_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="SET NULL")),
        sa.Column("report_path", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_contact_import_jobs_status", "customer_contact_import_jobs", ["status"])
    op.create_index("ix_customer_contact_import_jobs_checksum", "customer_contact_import_jobs", ["file_checksum"])
    op.create_index("ix_customer_contact_import_jobs_dataset", "customer_contact_import_jobs", ["dataset_key"])
    op.create_table(
        "customer_contact_import_staging",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("customer_contact_import_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(255)),
        sa.Column("original_email", sa.String(255)),
        sa.Column("normalized_email", sa.String(255)),
        sa.Column("original_domain", sa.String(255)),
        sa.Column("normalized_domain", sa.String(255)),
        sa.Column("email_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("phone", sa.String(120)),
        sa.Column("role", sa.String(255)),
        sa.Column("notes", sa.Text()),
        sa.Column("suggested_organization_id", sa.Integer()),
        sa.Column("suggested_organization_type", sa.String(80)),
        sa.Column("suggested_organization_name", sa.String(255)),
        sa.Column("existing_contact_id", sa.Integer()),
        sa.Column("proposed_action", sa.String(80), nullable=False, server_default="create_contact"),
        sa.Column("validation_status", sa.String(80), nullable=False, server_default="valid"),
        sa.Column("error_code", sa.String(120)),
        sa.Column("warning_code", sa.String(120)),
        sa.Column("decision_status", sa.String(80), nullable=False, server_default="pending"),
        sa.Column("decision_action", sa.String(80)),
        sa.Column("is_shared_inbox", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("is_automated_address", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("engagement_level", sa.String(40), nullable=False, server_default="low"),
        sa.Column("contact_type", sa.String(80), nullable=False, server_default="unknown"),
        sa.Column("data_quality_status", sa.String(80), nullable=False, server_default="needs_review"),
        sa.Column("duplicate_of_row", sa.Integer()),
        sa.Column("duplicate_row_numbers", sa.Text()),
        sa.Column("validation_metadata", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("import_job_id", "normalized_email", name="uq_customer_contact_stage_job_email"),
    )
    op.create_index("ix_customer_contact_stage_job_id", "customer_contact_import_staging", ["import_job_id"])
    op.create_index("ix_customer_contact_stage_normalized_email", "customer_contact_import_staging", ["normalized_email"])
    op.create_index("ix_customer_contact_stage_domain", "customer_contact_import_staging", ["normalized_domain"])
    op.create_index("ix_customer_contact_stage_status", "customer_contact_import_staging", ["validation_status"])
    op.create_index("ix_customer_contact_stage_action", "customer_contact_import_staging", ["proposed_action"])
    op.create_index("ix_customer_contact_stage_existing_contact", "customer_contact_import_staging", ["existing_contact_id"])
    op.create_index("ix_customer_contact_stage_suggested_org", "customer_contact_import_staging", ["suggested_organization_type", "suggested_organization_id"])


def downgrade():
    op.drop_table("customer_contact_import_staging")
    op.drop_table("customer_contact_import_jobs")
