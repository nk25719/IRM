from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import FoundationSchema, TimestampFields


class ImportBatchCreate(FoundationSchema):
    source_type: str | None = None
    source_filename: str | None = None
    source_checksum: str | None = None
    imported_by_id: int | None = None
    status: str = "pending"
    total_rows: int = 0
    notes: str | None = None


class ImportBatchUpdate(FoundationSchema):
    source_type: str | None = None
    source_filename: str | None = None
    source_checksum: str | None = None
    completed_at: datetime | None = None
    status: str | None = None
    total_rows: int | None = None
    processed_rows: int | None = None
    successful_rows: int | None = None
    failed_rows: int | None = None
    notes: str | None = None


class ImportBatchRead(ImportBatchCreate, TimestampFields):
    id: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    processed_rows: int = 0
    successful_rows: int = 0
    failed_rows: int = 0


class ImportBatchList(FoundationSchema):
    items: list[ImportBatchRead]
    total: int
    limit: int
    offset: int


class ImportRowCreate(FoundationSchema):
    import_batch_id: int
    row_number: int
    raw_data: dict[str, Any] | list[Any] | None = None
    normalized_data: dict[str, Any] | list[Any] | None = None
    processing_status: str = "pending"


class ImportRowRead(ImportRowCreate, TimestampFields):
    id: int
    matched_client_id: int | None = None
    matched_department_id: int | None = None
    matched_equipment_id: int | None = None
    matched_case_id: int | None = None
    error_message: str | None = None
    warning_message: str | None = None
    processed_at: datetime | None = None


class DataValidationErrorCreate(FoundationSchema):
    import_batch_id: int
    import_row_id: int | None = None
    field_name: str | None = None
    raw_value: str | None = None
    error_code: str
    error_message: str
    severity: str = "error"


class DataValidationErrorRead(DataValidationErrorCreate, TimestampFields):
    id: int
    is_resolved: bool = False
    resolved_by_id: int | None = None
    resolved_at: datetime | None = None
