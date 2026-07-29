from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Iterable

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app import erp_models as erp
from app.schedule_models import EngineerAvailability, EngineerScheduleAssignment, EngineerScheduleEvent

CANCELLED_STATUSES = {"cancelled"}


@dataclass
class Conflict:
    conflict_type: str
    severity: str
    message: str
    engineer_id: int | None = None
    event_id: int | None = None

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def buffered_start(event: EngineerScheduleEvent) -> datetime | None:
    if not event.start_datetime:
        return None
    return event.start_datetime - timedelta(minutes=event.travel_time_before_minutes or 0)


def buffered_end(event: EngineerScheduleEvent) -> datetime | None:
    if not event.end_datetime:
        return None
    return event.end_datetime + timedelta(minutes=event.travel_time_after_minutes or 0)


def overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and end_a > start_b


class ScheduleConflictService:
    def __init__(self, db: Session):
        self.db = db

    def detect_for_event(self, event: EngineerScheduleEvent, engineer_ids: Iterable[int] | None = None) -> list[dict]:
        conflicts: list[Conflict] = []
        assigned_ids = list(engineer_ids or [a.engineer_id for a in self.db.query(EngineerScheduleAssignment).filter_by(schedule_event_id=event.id).all()])
        if not assigned_ids:
            conflicts.append(Conflict("missing_engineer", "warning", "No engineer is assigned to this activity."))
            return [c.as_dict() for c in conflicts]
        if not event.start_datetime or not event.end_datetime:
            conflicts.append(Conflict("missing_time", "warning", "Start and end time are required for conflict detection."))
            return [c.as_dict() for c in conflicts]
        if event.end_datetime <= event.start_datetime:
            conflicts.append(Conflict("invalid_time", "error", "End time must be after start time."))
            return [c.as_dict() for c in conflicts]

        start = buffered_start(event) or event.start_datetime
        end = buffered_end(event) or event.end_datetime
        for engineer_id in assigned_ids:
            engineer = self.db.get(erp.Engineer, engineer_id)
            if engineer and not engineer.active:
                conflicts.append(Conflict("inactive_engineer", "warning", f"{engineer.engineer_name} is inactive.", engineer_id))
            query_start = start - timedelta(hours=8)
            query_end = end + timedelta(hours=8)
            query = (
                self.db.query(EngineerScheduleEvent)
                .join(EngineerScheduleAssignment, EngineerScheduleAssignment.schedule_event_id == EngineerScheduleEvent.id)
                .filter(EngineerScheduleAssignment.engineer_id == engineer_id)
                .filter(EngineerScheduleEvent.status.notin_(CANCELLED_STATUSES))
                .filter(EngineerScheduleEvent.id != (event.id or 0))
                .filter(EngineerScheduleEvent.start_datetime.isnot(None), EngineerScheduleEvent.end_datetime.isnot(None))
                .filter(and_(EngineerScheduleEvent.start_datetime < query_end, EngineerScheduleEvent.end_datetime > query_start))
            )
            for existing in query.all():
                direct = overlaps(event.start_datetime, event.end_datetime, existing.start_datetime, existing.end_datetime)
                travel = not direct and overlaps(start, end, buffered_start(existing) or existing.start_datetime, buffered_end(existing) or existing.end_datetime)
                if direct or travel:
                    conflicts.append(
                        Conflict(
                            "overlap" if direct else "travel_buffer",
                            "warning",
                            f"Overlaps with {existing.title}." if direct else f"Travel buffer conflicts with {existing.title}.",
                            engineer_id,
                            existing.id,
                        )
                    )
            availability = (
                self.db.query(EngineerAvailability)
                .filter(EngineerAvailability.engineer_id == engineer_id)
                .filter(EngineerAvailability.is_available.is_(False))
                .filter(and_(EngineerAvailability.start_datetime < event.end_datetime, EngineerAvailability.end_datetime > event.start_datetime))
                .all()
            )
            for item in availability:
                conflicts.append(Conflict("unavailable", "warning", f"Engineer is unavailable: {item.availability_type}.", engineer_id, item.id))
            if not event.all_day and (event.start_datetime.time() < time(8, 0) or event.end_datetime.time() > time(18, 0)):
                conflicts.append(Conflict("outside_working_hours", "warning", "Activity is outside standard working hours.", engineer_id))
        return [c.as_dict() for c in conflicts]
