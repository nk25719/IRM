from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import FoundationSchema


class AuditEventCreate(FoundationSchema):
    event_type: str
    entity_type: str
    entity_id: str | None = None
    user_id: int | None = None
    request_id: str | None = None
    source: str | None = None
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    event_metadata: dict[str, Any] | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class AuditEventRead(AuditEventCreate):
    id: int
    created_at: datetime


class StatusHistoryCreate(FoundationSchema):
    entity_type: str
    entity_id: str
    previous_status: str | None = None
    new_status: str
    changed_by_id: int | None = None
    reason: str | None = None


class StatusHistoryRead(StatusHistoryCreate):
    id: int
    changed_at: datetime
