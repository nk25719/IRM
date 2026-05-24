from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import erp_models as m
from .database import get_db
from .mdmanser_client import (
    MDManserAuthenticationError,
    MDManserClient,
    MDManserConfigurationError,
    MDManserRequestError,
    mdmanser_base_url,
    mdmanser_session_configured,
)
from .mdmanser_parser import parse_mdmanser_calendar_html

router = APIRouter(prefix="/api/erp/mdmanser", tags=["MDManser"])


def _raise_connector_error(exc: Exception) -> None:
    if isinstance(exc, MDManserAuthenticationError):
        raise HTTPException(status_code=401, detail="MDManser authentication required or session expired") from exc
    if isinstance(exc, MDManserConfigurationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, MDManserRequestError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=502, detail="MDManser connector request failed") from exc


def _event_dict(row: m.MDManserCalendarEvent) -> dict:
    return {
        "id": row.id,
        "source": row.source,
        "source_event_key": row.source_event_key,
        "event_type": row.event_type,
        "title": row.title,
        "engineer_name": row.engineer_name,
        "call_reasons": row.call_reasons,
        "contract_reference": row.contract_reference,
        "client_name": row.client_name,
        "equipment_name": row.equipment_name,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "raw_payload": row.raw_payload,
        "mapped_client_id": row.mapped_client_id,
        "mapped_equipment_id": row.mapped_equipment_id,
        "mapped_case_id": row.mapped_case_id,
        "imported_at": row.imported_at.isoformat() if row.imported_at else None,
    }


@router.get("/status")
def mdmanser_status():
    return {
        "configured": MDManserClient.configured(),
        "base_url": mdmanser_base_url(),
        "has_session": mdmanser_session_configured(),
    }


@router.get("/calendar/raw")
def mdmanser_calendar_raw(month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=2000, le=2100)):
    try:
        return MDManserClient().check_calendar_read(month=month, year=year)
    except Exception as exc:
        _raise_connector_error(exc)


@router.post("/calendar/import")
def mdmanser_calendar_import(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    db: Session = Depends(get_db),
):
    try:
        html = MDManserClient().get_calendar_html(month=month, year=year)
    except Exception as exc:
        _raise_connector_error(exc)
    events = parse_mdmanser_calendar_html(html)
    inserted = updated = 0
    for event in events:
        row = db.query(m.MDManserCalendarEvent).filter_by(source_event_key=event["source_event_key"]).first()
        if row:
            for key, value in event.items():
                setattr(row, key, value)
            updated += 1
        else:
            db.add(m.MDManserCalendarEvent(**event))
            inserted += 1
    db.commit()
    return {"parsed": len(events), "inserted": inserted, "updated": updated}


@router.get("/calendar/events")
def mdmanser_calendar_events(
    limit: int = Query(100, ge=1, le=1000),
    engineer_name: str | None = None,
    start: date | None = None,
    end: date | None = None,
    event_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(m.MDManserCalendarEvent)
    if engineer_name:
        query = query.filter(m.MDManserCalendarEvent.engineer_name.ilike(f"%{engineer_name}%"))
    if start:
        query = query.filter(m.MDManserCalendarEvent.start_date >= start)
    if end:
        query = query.filter(m.MDManserCalendarEvent.start_date <= end)
    if event_type:
        query = query.filter(m.MDManserCalendarEvent.event_type == event_type)
    rows = query.order_by(m.MDManserCalendarEvent.start_date.desc(), m.MDManserCalendarEvent.id.desc()).limit(limit).all()
    return [_event_dict(row) for row in rows]


@router.get("/calendar/events/{event_id}")
def mdmanser_calendar_event(event_id: int, db: Session = Depends(get_db)):
    row = db.get(m.MDManserCalendarEvent, event_id)
    if not row:
        raise HTTPException(status_code=404, detail="MDManser calendar event not found")
    return _event_dict(row)
