from __future__ import annotations

import io
from collections import defaultdict

from openpyxl import Workbook


def export_schedule_workbook(events: list[dict], grid: bool = False) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Weekly Grid" if grid else "Engineer Schedule"
    if grid:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        sheet.append(["Engineer", *days])
        grouped = defaultdict(lambda: defaultdict(list))
        for event in events:
            for assignment in event.get("assignments") or [{"engineer_name": "Unassigned"}]:
                day = event["start_datetime"].strftime("%A") if event.get("start_datetime") else "Unscheduled"
                grouped[assignment.get("engineer_name") or "Unassigned"][day].append(_cell_label(event))
        for engineer, by_day in grouped.items():
            sheet.append([engineer, *["\n".join(by_day.get(day, [])) for day in days]])
    else:
        headers = ["Date", "Day", "Start Time", "End Time", "Engineer", "Additional Engineers", "Assignment Role", "Event Type", "Title", "Client", "Site", "Location", "Status", "Priority", "Conflict", "Linked Record Type", "Linked Record ID", "Notes"]
        sheet.append(headers)
        for event in events:
            assignments = event.get("assignments") or [{"engineer_name": "Unassigned", "assignment_role": ""}]
            primary = assignments[0]
            start = event.get("start_datetime")
            end = event.get("end_datetime")
            linked_type, linked_id = _linked_record(event)
            sheet.append([start.date().isoformat() if start else "", start.strftime("%A") if start else "", start.strftime("%H:%M") if start else "", end.strftime("%H:%M") if end else "", primary.get("engineer_name"), ", ".join(a.get("engineer_name") for a in assignments[1:]), primary.get("assignment_role"), event.get("event_type"), event.get("title"), event.get("client_name"), event.get("site_name"), event.get("location_text"), event.get("status"), event.get("priority"), "Yes" if event.get("has_conflict") else "No", linked_type, linked_id, event.get("description")])
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _cell_label(event: dict) -> str:
    start = event.get("start_datetime")
    label = f"{start.strftime('%H:%M')} " if start else ""
    return f"{label}{event.get('title') or ''} - {event.get('client_name') or ''}".strip(" -")


def _linked_record(event: dict) -> tuple[str, str]:
    for field, label in [("service_case_id", "service_case"), ("service_call_id", "service_call"), ("preventive_maintenance_id", "pm_task"), ("contract_id", "contract"), ("customer_service_contract_id", "customer_service_contract"), ("equipment_id", "equipment")]:
        if event.get(field):
            return label, str(event[field])
    return "", ""
