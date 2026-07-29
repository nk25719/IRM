from __future__ import annotations

from datetime import date, datetime, time

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import erp_models as erp
from app import schedule_models as schedule_models
from app.database import Base, engine, get_db
from app.schedule_models import EngineerAvailability, EngineerScheduleAssignment, EngineerScheduleEvent
from app.services.schedule_export_service import export_schedule_workbook
from app.services.schedule_import_service import ScheduleImportService
from app.services.schedule_service import ScheduleService, parse_dt, serialize_event, week_bounds
from app.services.schedule_workload_service import ScheduleWorkloadService

router = APIRouter(prefix="/api/schedule", tags=["Engineer Schedule"])


def ensure_schedule_tables():
    Base.metadata.create_all(bind=engine, tables=[
        EngineerScheduleEvent.__table__,
        EngineerScheduleAssignment.__table__,
        EngineerAvailability.__table__,
        schedule_models.ScheduleChangeLog.__table__,
    ])


def _role(request: Request) -> str:
    return request.session.get("role") or "viewer"


def _user_id(request: Request, db: Session) -> int | None:
    username = request.session.get("username")
    if not username:
        return None
    user = db.query(erp.User).filter(erp.User.username == username).first()
    return user.id if user else None


def _service(request: Request, db: Session) -> ScheduleService:
    return ScheduleService(db, _user_id(request, db), _role(request))


def _handle_error(exc: Exception):
    if isinstance(exc, PermissionError):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


@router.get("/events")
def list_events(request: Request, db: Session = Depends(get_db), start: str | None = None, end: str | None = None, engineer_id: int | None = None, event_type: str | None = None, status: str | None = None, client_id: int | None = None, client_site_id: int | None = None, priority: str | None = None, conflict_status: str | None = None, limit: int = Query(500, ge=1, le=1000)):
    return _service(request, db).list_events(locals())


@router.post("/events", status_code=201)
def create_event(payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        return _service(request, db).create_event(payload)
    except Exception as exc:
        _handle_error(exc)


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(EngineerScheduleEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Schedule event not found")
    return serialize_event(db, event)


@router.patch("/events/{event_id}")
def update_event(event_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        return _service(request, db).update_event(event_id, payload)
    except Exception as exc:
        _handle_error(exc)


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        _service(request, db).delete_event(event_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/events/{event_id}/assignments")
def add_assignment(event_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    try:
        return _service(request, db).add_assignment(event_id, payload)
    except Exception as exc:
        _handle_error(exc)


@router.delete("/events/{event_id}/assignments/{assignment_id}", status_code=204)
def remove_assignment(event_id: int, assignment_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        _service(request, db).remove_assignment(event_id, assignment_id)
    except Exception as exc:
        _handle_error(exc)


@router.get("/integrated")
def integrated(request: Request, db: Session = Depends(get_db), week: date | None = None):
    start, end = week_bounds(week)
    return {"start": start.date(), "end": end.date(), "events": _service(request, db).list_events({"start": start.isoformat(), "end": end.isoformat(), "limit": 1000})}


@router.get("/engineers/{engineer_id}")
def engineer_schedule(engineer_id: int, request: Request, db: Session = Depends(get_db), week: date | None = None):
    start, end = week_bounds(week)
    events = _service(request, db).list_events({"start": start.isoformat(), "end": end.isoformat(), "engineer_id": engineer_id, "limit": 1000})
    availability = db.query(EngineerAvailability).filter(EngineerAvailability.engineer_id == engineer_id, EngineerAvailability.start_datetime < end, EngineerAvailability.end_datetime > start).all()
    return {"engineer_id": engineer_id, "events": events, "availability": [{c.name: getattr(item, c.name) for c in item.__table__.columns} for item in availability]}


@router.get("/conflicts")
def conflicts(request: Request, db: Session = Depends(get_db), start: str | None = None, end: str | None = None):
    rows = _service(request, db).list_events({"start": start, "end": end, "conflict_status": "conflict", "limit": 1000})
    return rows


@router.get("/unassigned")
def unassigned(request: Request, db: Session = Depends(get_db), start: str | None = None, end: str | None = None):
    return [row for row in _service(request, db).list_events({"start": start, "end": end, "limit": 1000}) if not row["assignments"]]


@router.get("/workload")
def workload(start: str | None = None, end: str | None = None, db: Session = Depends(get_db)):
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)
    if not start_dt or not end_dt:
        start_dt, end_dt = week_bounds()
    return ScheduleWorkloadService(db).weekly(start_dt, end_dt)


@router.post("/availability", status_code=201)
def create_availability(payload: dict, request: Request, db: Session = Depends(get_db)):
    service = _service(request, db)
    try:
        service.require_write()
        for field in ("start_datetime", "end_datetime"):
            payload[field] = parse_dt(payload[field])
        row = EngineerAvailability(created_by_id=service.user_id, **payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return {c.name: getattr(row, c.name) for c in row.__table__.columns}
    except Exception as exc:
        _handle_error(exc)


@router.post("/import/preview")
async def import_preview(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    service = _service(request, db)
    try:
        service.require_write()
        content = await file.read()
        return ScheduleImportService(db, service.user_id, service.role).preview(content, file.filename or "schedule.xlsx")
    except Exception as exc:
        _handle_error(exc)


@router.post("/import/confirm")
def import_confirm(payload: dict, request: Request, db: Session = Depends(get_db)):
    service = _service(request, db)
    try:
        service.require_write()
        return ScheduleImportService(db, service.user_id, service.role).confirm(payload)
    except Exception as exc:
        _handle_error(exc)


@router.get("/export")
def export(request: Request, db: Session = Depends(get_db), start: str | None = None, end: str | None = None, grid: bool = False):
    events = _service(request, db).list_events({"start": start, "end": end, "limit": 1000})
    content = export_schedule_workbook(events, grid)
    filename = "engineer_schedule_grid.xlsx" if grid else "engineer_schedule.xlsx"
    return StreamingResponse(iter([content]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/lookups")
def lookups(db: Session = Depends(get_db)):
    return {
        "engineers": [{"id": item.id, "name": item.engineer_name, "active": item.active} for item in db.query(erp.Engineer).order_by(erp.Engineer.engineer_name).all()],
        "clients": [{"id": item.id, "name": item.name} for item in db.query(erp.Client).order_by(erp.Client.name).limit(500).all()],
        "equipment": [{"id": item.id, "name": item.name, "serial_number": item.serial_number, "client_id": item.client_id} for item in db.query(erp.Equipment).order_by(erp.Equipment.name).limit(500).all()],
    }


@router.post("/from/{source_type}/{source_id}", status_code=201)
def create_from_source(source_type: str, source_id: int, payload: dict, request: Request, db: Session = Depends(get_db)):
    event = dict(payload)
    if source_type in {"service_case", "case"}:
        row = db.get(erp.Case, source_id)
        if not row:
            raise HTTPException(status_code=404, detail="Service case not found")
        event.update({"title": event.get("title") or row.title, "description": event.get("description") or row.description, "client_id": row.client_id, "equipment_id": row.equipment_id, "service_case_id": row.id, "event_type": event.get("event_type") or "corrective_maintenance"})
    elif source_type in {"pm", "preventive_maintenance"}:
        row = db.get(erp.PMTask, source_id)
        if not row:
            raise HTTPException(status_code=404, detail="PM task not found")
        start = datetime.combine(row.scheduled_date, time(9, 0)).isoformat() if row.scheduled_date else event.get("start_datetime")
        event.update({"title": event.get("title") or row.pm_label or "Preventive maintenance", "client_id": row.client_id, "equipment_id": row.equipment_id, "preventive_maintenance_id": row.id, "start_datetime": start, "event_type": event.get("event_type") or "preventive_maintenance"})
    elif source_type in {"contract", "customer_contract"}:
        event.update({"title": event.get("title") or "Contract work", "customer_service_contract_id": source_id if source_type == "customer_contract" else None, "contract_id": source_id if source_type == "contract" else None, "event_type": event.get("event_type") or "contract_work"})
    else:
        raise HTTPException(status_code=400, detail="Unsupported schedule source")
    try:
        return _service(request, db).create_event(event)
    except Exception as exc:
        _handle_error(exc)
