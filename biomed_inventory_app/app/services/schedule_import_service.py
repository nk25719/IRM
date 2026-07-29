from __future__ import annotations

import hashlib
import io
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app import erp_models as erp
from app.models.foundation import ImportBatch
from app.services.schedule_service import ScheduleService

DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


def parse_time(text: str) -> tuple[time | None, str | None]:
    match = TIME_RE.search(text or "")
    if not match:
        return None, "No confident time found."
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None, "Invalid time detected."
    return time(hour, minute), None


class ScheduleImportService:
    def __init__(self, db: Session, user_id: int | None = None, role: str = "viewer"):
        self.db = db
        self.user_id = user_id
        self.role = role

    def preview(self, content: bytes, filename: str) -> dict[str, Any]:
        workbook = load_workbook(io.BytesIO(content), data_only=True)
        sheet = self._find_sheet(workbook)
        week_of = self._find_week_of(sheet)
        headers = self._find_day_headers(sheet)
        rows = []
        warnings = []
        if not week_of:
            warnings.append("Missing Week of date. Set dates before confirming import.")
        for column, day_name in headers.items():
            day_index = DAY_NAMES.index(day_name)
            event_date = week_of + timedelta(days=day_index) if week_of else None
            for row_index in range(1, sheet.max_row + 1):
                raw = sheet.cell(row=row_index, column=column).value
                if not raw or str(raw).strip().lower() == day_name:
                    continue
                for part in self._split_cell(str(raw)):
                    start_time, warning = parse_time(part)
                    start_datetime = datetime.combine(event_date, start_time) if event_date and start_time else None
                    end_datetime = start_datetime + timedelta(hours=1) if start_datetime else None
                    client = self._match_client(part)
                    rows.append({
                        "row_number": len(rows) + 1,
                        "day": day_name.title(),
                        "date": event_date.isoformat() if event_date else None,
                        "title": self._clean_title(part),
                        "source_reference": part,
                        "event_type": self._guess_type(part),
                        "status": "scheduled",
                        "priority": "normal",
                        "start_datetime": start_datetime.isoformat() if start_datetime else None,
                        "end_datetime": end_datetime.isoformat() if end_datetime else None,
                        "all_day": not bool(start_datetime),
                        "client_id": client.id if client else None,
                        "client_name": client.name if client else None,
                        "warnings": [warning] if warning else [],
                        "assignments": [],
                    })
        return {
            "filename": filename,
            "checksum": hashlib.sha256(content).hexdigest(),
            "worksheet": sheet.title,
            "week_of": week_of.isoformat() if week_of else None,
            "warnings": warnings,
            "rows": rows,
        }

    def confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        checksum = payload.get("checksum")
        if checksum:
            duplicate = self.db.query(ImportBatch).filter_by(source_checksum=checksum, status="completed", source_type="engineer_schedule").first()
            if duplicate and not payload.get("allow_duplicate"):
                raise ValueError("This schedule file was already imported. Enable duplicate import to continue.")
        batch = ImportBatch(source_type="engineer_schedule", source_filename=payload.get("filename"), source_checksum=checksum, imported_by_id=self.user_id, status="processing", total_rows=len(payload.get("rows") or []))
        self.db.add(batch)
        self.db.flush()
        created = 0
        service = ScheduleService(self.db, self.user_id, self.role)
        for row in payload.get("rows") or []:
            if row.get("skip"):
                continue
            row["import_batch_id"] = batch.id
            row["source"] = "weekly_excel_import"
            service.create_event(dict(row))
            created += 1
        batch.status = "completed"
        batch.processed_rows = len(payload.get("rows") or [])
        batch.successful_rows = created
        batch.completed_at = datetime.now(UTC)
        self.db.commit()
        return {"import_batch_id": batch.id, "created": created}

    def _find_sheet(self, workbook):
        for sheet in workbook.worksheets:
            text = " ".join(str(cell.value or "") for row in sheet.iter_rows() for cell in row[:8]).lower()
            if "weekly schedule" in text or "week of" in text:
                return sheet
        return workbook.active

    def _find_week_of(self, sheet) -> date | None:
        for row in sheet.iter_rows():
            for index, cell in enumerate(row):
                if str(cell.value or "").strip().lower().startswith("week of"):
                    for candidate in row[index + 1:index + 4]:
                        if isinstance(candidate.value, datetime):
                            return candidate.value.date()
                        if isinstance(candidate.value, date):
                            return candidate.value
                        try:
                            return datetime.fromisoformat(str(candidate.value)).date()
                        except Exception:
                            pass
        return None

    def _find_day_headers(self, sheet) -> dict[int, str]:
        headers = {}
        for row in sheet.iter_rows():
            for cell in row:
                label = str(cell.value or "").strip().lower()
                if label in DAY_NAMES:
                    headers[cell.column] = label
            if headers:
                return headers
        return {}

    def _split_cell(self, value: str) -> list[str]:
        parts = re.split(r"(?:\n|;|\s{2,})+", value)
        return [part.strip(" -\t") for part in parts if part.strip(" -\t")]

    def _clean_title(self, value: str) -> str:
        return re.sub(TIME_RE, "", value).strip(" -")[:255] or "Imported schedule activity"

    def _guess_type(self, value: str) -> str:
        text = value.lower()
        if "training" in text:
            return "training"
        if "install" in text:
            return "installation"
        if "contract" in text:
            return "contract_work"
        if "delivery" in text:
            return "delivery"
        if "pm" in text or "preventive" in text:
            return "preventive_maintenance"
        return "other"

    def _match_client(self, value: str):
        text = value.lower()
        return self.db.query(erp.Client).filter(erp.Client.name.isnot(None)).all() and next((client for client in self.db.query(erp.Client).all() if client.name.lower() in text), None)
