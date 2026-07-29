from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app import erp_models as erp
from app.schedule_models import EngineerAvailability, EngineerScheduleAssignment, EngineerScheduleEvent
from app.services.schedule_conflict_service import ScheduleConflictService


class ScheduleWorkloadService:
    def __init__(self, db: Session):
        self.db = db

    def weekly(self, start: datetime, end: datetime) -> list[dict]:
        summary = defaultdict(lambda: {"total_scheduled_hours": 0.0, "assignment_count": 0, "corrective_maintenance_count": 0, "pm_count": 0, "installation_count": 0, "delivery_count": 0, "training_count": 0, "travel_time_hours": 0.0, "unavailable_hours": 0.0, "conflict_count": 0, "unassigned_activity_count": 0})
        engineers = {e.id: e for e in self.db.query(erp.Engineer).order_by(erp.Engineer.engineer_name).all()}
        for engineer_id, engineer in engineers.items():
            summary[engineer_id]["engineer_id"] = engineer_id
            summary[engineer_id]["engineer_name"] = engineer.engineer_name
        rows = (
            self.db.query(EngineerScheduleEvent)
            .filter(EngineerScheduleEvent.status != "cancelled")
            .filter(EngineerScheduleEvent.start_datetime < end, EngineerScheduleEvent.end_datetime > start)
            .all()
        )
        conflict_service = ScheduleConflictService(self.db)
        for event in rows:
            assignments = self.db.query(EngineerScheduleAssignment).filter_by(schedule_event_id=event.id).all()
            if not assignments:
                summary[0]["engineer_id"] = None
                summary[0]["engineer_name"] = "Unassigned"
                summary[0]["unassigned_activity_count"] += 1
            duration = max(0.0, ((event.end_datetime - event.start_datetime).total_seconds() / 3600.0) if event.start_datetime and event.end_datetime else 0.0)
            travel = ((event.travel_time_before_minutes or 0) + (event.travel_time_after_minutes or 0)) / 60.0
            conflicts = len(conflict_service.detect_for_event(event))
            for assignment in assignments:
                item = summary[assignment.engineer_id]
                item["assignment_count"] += 1
                item["total_scheduled_hours"] += duration
                item["travel_time_hours"] += travel
                item["conflict_count"] += conflicts
                if event.event_type == "corrective_maintenance":
                    item["corrective_maintenance_count"] += 1
                elif event.event_type == "preventive_maintenance":
                    item["pm_count"] += 1
                elif event.event_type == "installation":
                    item["installation_count"] += 1
                elif event.event_type == "delivery":
                    item["delivery_count"] += 1
                elif event.event_type == "training":
                    item["training_count"] += 1
        for item in self.db.query(EngineerAvailability).filter(EngineerAvailability.is_available.is_(False), EngineerAvailability.start_datetime < end, EngineerAvailability.end_datetime > start):
            summary[item.engineer_id]["unavailable_hours"] += max(0.0, (min(item.end_datetime, end) - max(item.start_datetime, start)).total_seconds() / 3600.0)
        return list(summary.values())
