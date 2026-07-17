from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import postgresql

from app.database import Base
from app.models.mixins import SoftDeleteMixin, TimestampMixin

JSON_VALUE = JSON().with_variant(postgresql.JSONB, "postgresql")


class Manufacturer(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "manufacturers"
    __table_args__ = (
        UniqueConstraint("code", name="uq_manufacturers_code"),
        UniqueConstraint("normalized_name", name="uq_manufacturers_normalized_name"),
        Index("ix_manufacturers_name", "name"),
        Index("ix_manufacturers_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(80), nullable=True)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    legal_name = Column(String(255))
    website = Column(String(500))
    email = Column(String(255))
    phone = Column(String(80))
    country_code = Column(String(2))
    status = Column(String(50), nullable=False, default="active", server_default="active")


class ManufacturerAlias(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "manufacturer_aliases"
    __table_args__ = (
        UniqueConstraint("normalized_alias", name="uq_manufacturer_aliases_normalized_alias"),
        Index("ix_manufacturer_aliases_manufacturer_id", "manufacturer_id"),
        Index("ix_manufacturer_aliases_normalized_alias", "normalized_alias"),
        Index("ix_manufacturer_aliases_is_verified", "is_verified"),
    )

    id = Column(Integer, primary_key=True)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id", ondelete="RESTRICT"), nullable=False)
    alias = Column(String(255), nullable=False)
    normalized_alias = Column(String(255), nullable=False)
    source = Column(String(120))
    is_verified = Column(Boolean, nullable=False, default=False, server_default="0")
    confidence = Column(Integer, nullable=False, default=0, server_default="0")


class Supplier(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("supplier_code", name="uq_suppliers_supplier_code"),
        Index("ix_suppliers_name", "name"),
        Index("ix_suppliers_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    supplier_code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(80))
    website = Column(String(500))
    tax_number = Column(String(120))
    country_code = Column(String(2))
    status = Column(String(50), nullable=False, default="active", server_default="active")


class ClientSite(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "client_sites"
    __table_args__ = (
        UniqueConstraint("client_id", "site_code", name="uq_client_sites_client_site_code"),
        Index("ix_client_sites_client_id", "client_id"),
        Index("ix_client_sites_city", "city"),
        Index("ix_client_sites_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False)
    site_code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    address_line_1 = Column(String(255))
    address_line_2 = Column(String(255))
    city = Column(String(120))
    region = Column(String(120))
    postal_code = Column(String(40))
    country_code = Column(String(2))
    phone = Column(String(80))
    email = Column(String(255))
    is_primary = Column(Boolean, nullable=False, default=False, server_default="0")
    status = Column(String(50), nullable=False, default="active", server_default="active")


class Location(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("site_id", "location_code", name="uq_locations_site_location_code"),
        Index("ix_locations_client_id", "client_id"),
        Index("ix_locations_site_id", "site_id"),
        Index("ix_locations_department_id", "department_id"),
        Index("ix_locations_parent_location_id", "parent_location_id"),
        Index("ix_locations_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    site_id = Column(Integer, ForeignKey("client_sites.id", ondelete="SET NULL"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    parent_location_id = Column(Integer, ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    location_code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    location_type = Column(String(80), nullable=False, default="site_area", server_default="site_area")
    floor = Column(String(80))
    room = Column(String(80))
    description = Column(Text)
    status = Column(String(50), nullable=False, default="active", server_default="active")


class EquipmentCategory(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "equipment_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_equipment_categories_code"),
        UniqueConstraint("parent_category_id", "normalized_name", name="uq_equipment_categories_parent_name"),
        Index("ix_equipment_categories_parent_category_id", "parent_category_id"),
        Index("ix_equipment_categories_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    code = Column(String(80), nullable=False)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    description = Column(Text)
    parent_category_id = Column(Integer, ForeignKey("equipment_categories.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), nullable=False, default="active", server_default="active")


class EquipmentCategoryAlias(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "equipment_category_aliases"
    __table_args__ = (
        UniqueConstraint("normalized_alias", name="uq_equipment_category_aliases_normalized_alias"),
        Index("ix_equipment_category_aliases_equipment_category_id", "equipment_category_id"),
        Index("ix_equipment_category_aliases_normalized_alias", "normalized_alias"),
        Index("ix_equipment_category_aliases_is_verified", "is_verified"),
    )

    id = Column(Integer, primary_key=True)
    equipment_category_id = Column(Integer, ForeignKey("equipment_categories.id", ondelete="RESTRICT"), nullable=False)
    alias = Column(String(255), nullable=False)
    normalized_alias = Column(String(255), nullable=False)
    source = Column(String(120))
    is_verified = Column(Boolean, nullable=False, default=False, server_default="0")
    confidence = Column(Integer, nullable=False, default=0, server_default="0")


class ImportBatch(Base, TimestampMixin):
    __tablename__ = "import_batches"
    __table_args__ = (
        Index("ix_import_batches_source_filename", "source_filename"),
        Index("ix_import_batches_source_checksum", "source_checksum"),
        Index("ix_import_batches_status", "status"),
        Index("ix_import_batches_started_at", "started_at"),
    )

    id = Column(Integer, primary_key=True)
    source_type = Column(String(80))
    source_filename = Column(String(255))
    source_checksum = Column(String(128))
    imported_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), nullable=False, default="pending", server_default="pending")
    total_rows = Column(Integer, nullable=False, default=0, server_default="0")
    processed_rows = Column(Integer, nullable=False, default=0, server_default="0")
    successful_rows = Column(Integer, nullable=False, default=0, server_default="0")
    failed_rows = Column(Integer, nullable=False, default=0, server_default="0")
    notes = Column(Text)


class ImportRow(Base, TimestampMixin):
    __tablename__ = "import_rows"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "row_number", name="uq_import_rows_batch_row_number"),
        Index("ix_import_rows_import_batch_id", "import_batch_id"),
        Index("ix_import_rows_processing_status", "processing_status"),
        Index("ix_import_rows_matched_client_id", "matched_client_id"),
        Index("ix_import_rows_matched_equipment_id", "matched_equipment_id"),
    )

    id = Column(Integer, primary_key=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    row_number = Column(Integer, nullable=False)
    raw_data = Column(JSON_VALUE)
    normalized_data = Column(JSON_VALUE)
    processing_status = Column(String(50), nullable=False, default="pending", server_default="pending")
    matched_client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    matched_department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    matched_equipment_id = Column(Integer, ForeignKey("equipment.id", ondelete="SET NULL"), nullable=True)
    matched_case_id = Column(Integer, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True)
    error_message = Column(Text)
    warning_message = Column(Text)
    processed_at = Column(DateTime(timezone=True))


class DataValidationError(Base, TimestampMixin):
    __tablename__ = "data_validation_errors"
    __table_args__ = (
        Index("ix_data_validation_errors_import_batch_id", "import_batch_id"),
        Index("ix_data_validation_errors_import_row_id", "import_row_id"),
        Index("ix_data_validation_errors_severity", "severity"),
        Index("ix_data_validation_errors_is_resolved", "is_resolved"),
    )

    id = Column(Integer, primary_key=True)
    import_batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="RESTRICT"), nullable=False)
    import_row_id = Column(Integer, ForeignKey("import_rows.id", ondelete="RESTRICT"), nullable=True)
    field_name = Column(String(120))
    raw_value = Column(Text)
    error_code = Column(String(120), nullable=False)
    error_message = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False, default="error", server_default="error")
    is_resolved = Column(Boolean, nullable=False, default=False, server_default="0")
    resolved_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at = Column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_user_id", "user_id"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_entity_created_at", "entity_type", "entity_id", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    event_type = Column(String(120), nullable=False)
    entity_type = Column(String(120), nullable=False)
    entity_id = Column(String(120), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    request_id = Column(String(120))
    source = Column(String(120))
    old_values = Column(JSON_VALUE)
    new_values = Column(JSON_VALUE)
    event_metadata = Column("metadata", JSON_VALUE)
    ip_address = Column(String(80))
    user_agent = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StatusHistory(Base):
    __tablename__ = "status_history"
    __table_args__ = (
        CheckConstraint(
            "previous_status IS NULL OR previous_status != new_status",
            name="ck_status_history_status_changed",
        ),
        Index("ix_status_history_entity", "entity_type", "entity_id"),
        Index("ix_status_history_changed_at", "changed_at"),
    )

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(120), nullable=False)
    entity_id = Column(String(120), nullable=False)
    previous_status = Column(String(80))
    new_status = Column(String(80), nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
