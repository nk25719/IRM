from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import erp_models as erp
from app.models.foundation import AuditEvent
from app.schedule_models import EngineerScheduleAssignment, EngineerScheduleEvent, ScheduleChangeLog
from app.services.schedule_conflict_service import ScheduleConflictService


WRITE_PERMISSIONS = {"admin", "after_sales"}
READ_PERMISSIONS = WRITE_PERMISSIONS | {"engineer", "viewer", "warehouse", "sales", "procurement"}


def parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def week_bounds(value: date | None = None) -> tuple[datetime, datetime]:
    day = value or date.today()
    start = day - timedelta(days=day.weekday())
    return datetime.combine(start, time.min), datetime.combine(start + timedelta(days=7), time.min)


def serialize_event(db: Session, event: EngineerScheduleEvent, include_conflicts: bool = True) -> dict:
    assignments = (
        db.query(EngineerScheduleAssignment, erp.Engineer)
        .join(erp.Engineer, erp.Engineer.id == EngineerScheduleAssignment.engineer_id)
        .filter(EngineerScheduleAssignment.schedule_event_id == event.id)
        .order_by(EngineerScheduleAssignment.id)
        .all()
    )
    client = db.get(erp.Client, event.client_id) if event.client_id else None
    site = None
    try:
        from app.models.foundation import ClientSite
        site = db.get(ClientSite, event.client_site_id) if event.client_site_id else None
    except Exception:
        site = None
    data = {column.name: getattr(event, column.name) for column in event.__table__.columns}
    data["assignments"] = [
        {
            "id": assignment.id,
            "engineer_id": assignment.engineer_id,
            "engineer_name": engineer.engineer_name,
            "assignment_role": assignment.assignment_role,
            "assignment_status": assignment.assignment_status,
            "notes": assignment.notes,
        }
        for assignment, engineer in assignments
    ]
    data["client_name"] = client.name if client else None
    data["site_name"] = site.name if site else None
    data["conflicts"] = ScheduleConflictService(db).detect_for_event(event) if include_conflicts else []
    data["has_conflict"] = bool(data["conflicts"])
    return data


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value


class ScheduleService:
    def __init__(self, db: Session, user_id: int | None = None, role: str = "viewer"):
        self.db = db
        self.user_id = user_id
        self.role = role or "viewer"

    def can_write(self) -> bool:
        return self.role in WRITE_PERMISSIONS

    def require_write(self):
        if not self.can_write():
            raise PermissionError("schedule.manage permission required")

    def list_events(self, filters: dict[str, Any]) -> list[dict]:
        start = parse_dt(filters.get("start"))
        end = parse_dt(filters.get("end"))
        if not start or not end:
            start, end = week_bounds()
        query = self.db.query(EngineerScheduleEvent).filter(
            or_(EngineerScheduleEvent.start_datetime.is_(None), EngineerScheduleEvent.start_datetime < end),
            or_(EngineerScheduleEvent.end_datetime.is_(None), EngineerScheduleEvent.end_datetime >= start),
        )
        if filters.get("engineer_id"):
            query = query.join(EngineerScheduleAssignment).filter(EngineerScheduleAssignment.engineer_id == int(filters["engineer_id"]))
        for key in ("event_type", "status", "priority", "client_id", "client_site_id"):
            if filters.get(key):
                query = query.filter(getattr(EngineerScheduleEvent, key) == filters[key])
        rows = query.order_by(EngineerScheduleEvent.start_datetime.asc().nullslast(), EngineerScheduleEvent.id.desc()).limit(int(filters.get("limit") or 500)).all()
        serialized = [serialize_event(self.db, row) for row in rows]
        if filters.get("conflict_status") == "conflict":
            serialized = [row for row in serialized if row["has_conflict"]]
        elif filters.get("conflict_status") == "clear":
            serialized = [row for row in serialized if not row["has_conflict"]]
        return serialized

    def create_event(self, payload: dict[str, Any]) -> dict:
        self.require_write()
        assignments = payload.pop("assignments", [])
        engineer_ids = payload.pop("engineer_ids", None)
        if engineer_ids:
            assignments.extend({"engineer_id": item, "assignment_role": "lead"} for item in engineer_ids)
        for field in ("start_datetime", "end_datetime", "cancelled_at"):
            if field in payload:
                payload[field] = parse_dt(payload[field])
        event = EngineerScheduleEvent(**{k: v for k, v in payload.items() if hasattr(EngineerScheduleEvent, k)})
        event.created_by_id = event.created_by_id or self.user_id
        event.updated_by_id = self.user_id
        self.db.add(event)
        self.db.flush()
        for assignment in assignments:
            self.db.add(EngineerScheduleAssignment(schedule_event_id=event.id, assigned_by_id=self.user_id, **assignment))
        self.db.flush()
        conflicts = ScheduleConflictService(self.db).detect_for_event(event)
        if conflicts and payload.get("conflict_override_reason"):
            event.conflict_override_reason = payload["conflict_override_reason"]
        self._log(event, "event_created", None, payload, event.conflict_override_reason)
        self.db.commit()
        self.db.refresh(event)
        return serialize_event(self.db, event)

    def update_event(self, event_id: int, payload: dict[str, Any]) -> dict:
        self.require_write()
        event = self.db.get(EngineerScheduleEvent, event_id)
        if not event:
            raise LookupError("Schedule event not found")
        old_values = serialize_event(self.db, event, include_conflicts=False)
        for field in ("start_datetime", "end_datetime", "cancelled_at"):
            if field in payload:
                payload[field] = parse_dt(payload[field])
        assignments = payload.pop("assignments", None)
        for key, value in payload.items():
            if key != "id" and hasattr(event, key):
                setattr(event, key, value)
        event.updated_by_id = self.user_id
        if event.status == "cancelled" and not event.cancelled_at:
            event.cancelled_at = datetime.now(UTC)
        if assignments is not None:
            self.db.query(EngineerScheduleAssignment).filter_by(schedule_event_id=event.id).delete()
            for assignment in assignments:
                self.db.add(EngineerScheduleAssignment(schedule_event_id=event.id, assigned_by_id=self.user_id, **assignment))
        self.db.flush()
        conflicts = ScheduleConflictService(self.db).detect_for_event(event)
        if conflicts and payload.get("conflict_override_reason"):
            event.conflict_override_reason = payload["conflict_override_reason"]
        self._log(event, "event_updated", old_values, payload, event.conflict_override_reason)
        self.db.commit()
        self.db.refresh(event)
        return serialize_event(self.db, event)

    def delete_event(self, event_id: int):
        self.require_write()
        event = self.db.get(EngineerScheduleEvent, event_id)
        if not event:
            raise LookupError("Schedule event not found")
        event.status = "cancelled"
        event.cancelled_at = datetime.now(UTC)
        self._log(event, "event_cancelled", None, {"status": "cancelled"}, None)
        self.db.commit()

    def add_assignment(self, event_id: int, payload: dict[str, Any]) -> dict:
        self.require_write()
        event = self.db.get(EngineerScheduleEvent, event_id)
        if not event:
            raise LookupError("Schedule event not found")
        assignment = EngineerScheduleAssignment(schedule_event_id=event_id, assigned_by_id=self.user_id, **payload)
        self.db.add(assignment)
        self._log(event, "engineer_assigned", None, payload, None)
        self.db.commit()
        return serialize_event(self.db, event)

    def remove_assignment(self, event_id: int, assignment_id: int):
        self.require_write()
        assignment = self.db.get(EngineerScheduleAssignment, assignment_id)
        event = self.db.get(EngineerScheduleEvent, event_id)
        if not assignment or assignment.schedule_event_id != event_id or not event:
            raise LookupError("Assignment not found")
        self.db.delete(assignment)
        self._log(event, "engineer_removed", {"assignment_id": assignment_id}, None, None)
        self.db.commit()

    def _log(self, event: EngineerScheduleEvent, change_type: str, old_values: Any, new_values: Any, reason: str | None):
        safe_old = json_safe(old_values)
        safe_new = json_safe(new_values)
        self.db.add(ScheduleChangeLog(schedule_event_id=event.id, change_type=change_type, changed_by_id=self.user_id, old_values=json.dumps(safe_old, default=str) if safe_old else None, new_values=json.dumps(safe_new, default=str) if safe_new else None, reason=reason))
        self.db.add(AuditEvent(event_type=change_type, entity_type="engineer_schedule_event", entity_id=str(event.id), user_id=self.user_id, source="schedule", old_values=safe_old, new_values=safe_new, event_metadata={"override_reason": reason} if reason else None))
