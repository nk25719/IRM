import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from openpyxl import Workbook
from sqlalchemy.orm import sessionmaker

from app import schedule_models  # noqa: F401
from app.database import Base, build_engine
from app.erp_models import Client, Engineer, Equipment, PMTask, User
from app.schedule_models import EngineerAvailability
from app.services.schedule_conflict_service import ScheduleConflictService
from app.services.schedule_import_service import ScheduleImportService
from app.services.schedule_service import ScheduleService, week_bounds
from app.services.schedule_workload_service import ScheduleWorkloadService


class EngineerScheduleTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = build_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()
        self.user = User(username="admin", role="admin")
        self.client = Client(name="HDF")
        self.engineer_a = Engineer(engineer_name="Engineer A", active=True)
        self.engineer_b = Engineer(engineer_name="Engineer B", active=True)
        self.inactive = Engineer(engineer_name="Inactive Engineer", active=False)
        self.db.add_all([self.user, self.client, self.engineer_a, self.engineer_b, self.inactive])
        self.db.commit()
        for row in [self.user, self.client, self.engineer_a, self.engineer_b, self.inactive]:
            self.db.refresh(row)
        self.service = ScheduleService(self.db, self.user.id, "admin")
        self.base = datetime(2026, 7, 27, 9, 0)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def create_event(self, title, start, end, engineer_id=None, **extra):
        payload = {
            "title": title,
            "event_type": extra.pop("event_type", "training"),
            "status": extra.pop("status", "scheduled"),
            "start_datetime": start.isoformat(),
            "end_datetime": end.isoformat(),
            "client_id": self.client.id,
            "assignments": [{"engineer_id": engineer_id or self.engineer_a.id, "assignment_role": "lead"}],
            **extra,
        }
        return self.service.create_event(payload)

    def test_multiple_events_same_engineer_same_day_are_allowed(self):
        self.create_event("Morning training", self.base, self.base + timedelta(hours=1))
        second = self.create_event("Afternoon install", self.base + timedelta(hours=3), self.base + timedelta(hours=5))
        self.assertEqual(len(second["assignments"]), 1)
        self.assertFalse(second["has_conflict"])

    def test_several_engineers_can_be_assigned_to_one_event(self):
        event = self.service.create_event({
            "title": "Team PM",
            "event_type": "preventive_maintenance",
            "status": "scheduled",
            "start_datetime": self.base.isoformat(),
            "end_datetime": (self.base + timedelta(hours=2)).isoformat(),
            "assignments": [{"engineer_id": self.engineer_a.id, "assignment_role": "lead"}, {"engineer_id": self.engineer_b.id, "assignment_role": "support"}],
        })
        self.assertEqual({a["engineer_id"] for a in event["assignments"]}, {self.engineer_a.id, self.engineer_b.id})

    def test_overlap_cases_and_back_to_back(self):
        self.create_event("Existing", self.base, self.base + timedelta(hours=1))
        cases = [
            (self.base + timedelta(minutes=30), self.base + timedelta(hours=1, minutes=30), True),
            (self.base - timedelta(minutes=30), self.base + timedelta(minutes=30), True),
            (self.base, self.base + timedelta(hours=1), True),
            (self.base + timedelta(hours=1), self.base + timedelta(hours=2), False),
        ]
        for index, (start, end, expected) in enumerate(cases):
            transient = schedule_models.EngineerScheduleEvent(title=f"Case {index}", event_type="training", status="scheduled", start_datetime=start, end_datetime=end)
            conflicts = ScheduleConflictService(self.db).detect_for_event(transient, [self.engineer_a.id])
            self.assertEqual(any(c["conflict_type"] == "overlap" for c in conflicts), expected)

    def test_travel_buffer_conflict(self):
        self.create_event("Existing", self.base, self.base + timedelta(hours=1), travel_time_after_minutes=30)
        transient = schedule_models.EngineerScheduleEvent(title="Next", event_type="training", status="scheduled", start_datetime=self.base + timedelta(hours=1, minutes=15), end_datetime=self.base + timedelta(hours=2))
        conflicts = ScheduleConflictService(self.db).detect_for_event(transient, [self.engineer_a.id])
        self.assertTrue(any(c["conflict_type"] == "travel_buffer" for c in conflicts))

    def test_cancelled_events_are_excluded_from_conflicts(self):
        self.create_event("Cancelled", self.base, self.base + timedelta(hours=1), status="cancelled")
        transient = schedule_models.EngineerScheduleEvent(title="Next", event_type="training", status="scheduled", start_datetime=self.base, end_datetime=self.base + timedelta(hours=1))
        self.assertFalse(ScheduleConflictService(self.db).detect_for_event(transient, [self.engineer_a.id]))

    def test_all_day_and_unavailability_conflicts(self):
        unavailable = EngineerAvailability(engineer_id=self.engineer_a.id, availability_type="annual_leave", start_datetime=self.base, end_datetime=self.base + timedelta(days=1), is_available=False)
        self.db.add(unavailable)
        self.db.commit()
        event = self.service.create_event({"title": "All day", "event_type": "leave", "status": "scheduled", "all_day": True, "start_datetime": self.base.isoformat(), "end_datetime": (self.base + timedelta(days=1)).isoformat(), "assignments": [{"engineer_id": self.engineer_a.id}]})
        self.assertTrue(any(c["conflict_type"] == "unavailable" for c in event["conflicts"]))

    def test_inactive_engineer_warning(self):
        event = self.create_event("Inactive assignment", self.base, self.base + timedelta(hours=1), engineer_id=self.inactive.id)
        self.assertTrue(any(c["conflict_type"] == "inactive_engineer" for c in event["conflicts"]))

    def test_permission_enforcement(self):
        with self.assertRaises(PermissionError):
            ScheduleService(self.db, None, "viewer").create_event({"title": "Nope"})

    def test_create_event_from_pm_source_shape(self):
        equipment = Equipment(client_id=self.client.id, name="Monitor")
        self.db.add(equipment)
        self.db.commit()
        pm = PMTask(client_id=self.client.id, equipment_id=equipment.id, scheduled_date=self.base.date(), pm_label="Quarterly PM")
        self.db.add(pm)
        self.db.commit()
        event = self.service.create_event({"title": pm.pm_label, "event_type": "preventive_maintenance", "client_id": pm.client_id, "equipment_id": pm.equipment_id, "preventive_maintenance_id": pm.id, "start_datetime": self.base.isoformat(), "end_datetime": (self.base + timedelta(hours=2)).isoformat()})
        self.assertEqual(event["preventive_maintenance_id"], pm.id)

    def test_excel_preview_multiple_cells_missing_week_and_invalid_time(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
        ws.append(["Telemetry Training - HDF - 18:00\nBad time 29:00", "", "", "", "", ""])
        stream = io.BytesIO()
        wb.save(stream)
        preview = ScheduleImportService(self.db, self.user.id, "admin").preview(stream.getvalue(), "weekly.xlsx")
        self.assertIn("Missing Week of date", preview["warnings"][0])
        self.assertEqual(len(preview["rows"]), 2)
        self.assertTrue(preview["rows"][0]["all_day"])

    def test_import_confirmation_and_duplicate_guard(self):
        payload = {"filename": "weekly.xlsx", "checksum": "abc", "rows": [{"title": "Training", "event_type": "training", "status": "scheduled", "start_datetime": self.base.isoformat(), "end_datetime": (self.base + timedelta(hours=1)).isoformat(), "assignments": [{"engineer_id": self.engineer_a.id}]}]}
        result = ScheduleImportService(self.db, self.user.id, "admin").confirm(dict(payload))
        self.assertEqual(result["created"], 1)
        with self.assertRaises(ValueError):
            ScheduleImportService(self.db, self.user.id, "admin").confirm(dict(payload))

    def test_import_preview_supports_engineer_assignment_report(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "engineer-assignments"
        ws.append(["assigned_to", "task_name", "status", "due_date", "completed_date", "asset_tag", "hospital", "department", "model"])
        ws.append(["Engineer A", "Telemetry Training", "scheduled", self.base.date(), None, "EQ-1", "HDF", "ICU", "Monitor"])
        stream = io.BytesIO()
        wb.save(stream)

        service = ScheduleImportService(self.db, self.user.id, "admin")
        preview = service.preview(stream.getvalue(), "engineer_assignment_report.xlsx")

        self.assertEqual(len(preview["rows"]), 1)
        row = preview["rows"][0]
        self.assertEqual(row["title"], "Telemetry Training")
        self.assertEqual(row["event_type"], "training")
        self.assertEqual(row["client_id"], self.client.id)
        self.assertEqual(row["assignments"], [{"engineer_id": self.engineer_a.id, "assignment_role": "lead"}])
        self.assertEqual(row["start_datetime"], self.base.replace(hour=9).isoformat())

        result = service.confirm({**preview, "checksum": "assignment-report"})
        self.assertEqual(result["created"], 1)
        events = self.service.list_events({"engineer_id": self.engineer_a.id, "start": self.base.isoformat(), "end": (self.base + timedelta(days=1)).isoformat()})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["assignments"][0]["engineer_id"], self.engineer_a.id)

    def test_workload_calculation(self):
        self.create_event("PM", self.base, self.base + timedelta(hours=2), event_type="preventive_maintenance", travel_time_before_minutes=30, travel_time_after_minutes=30)
        start, end = week_bounds(self.base.date())
        rows = ScheduleWorkloadService(self.db).weekly(start, end)
        engineer = next(row for row in rows if row["engineer_id"] == self.engineer_a.id)
        self.assertEqual(engineer["assignment_count"], 1)
        self.assertEqual(engineer["pm_count"], 1)
        self.assertEqual(engineer["total_scheduled_hours"], 2)
        self.assertEqual(engineer["travel_time_hours"], 1)


if __name__ == "__main__":
    unittest.main()
