from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
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

router = APIRouter(prefix="/api/erp/mdmanser", tags=["MDManser Connector"])


class MDManserEditCasePayload(BaseModel):
    new_id: str
    visit_date: str
    engineer_id: str
    note: str
    followup_date: str
    followup_time: str
    status_id: str
    priority_id: str
    confirm: bool = False


def _raise_connector_error(exc: Exception) -> None:
    if isinstance(exc, MDManserAuthenticationError):
        raise HTTPException(status_code=401, detail="MDManser authentication required or session expired") from exc
    if isinstance(exc, MDManserConfigurationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, MDManserRequestError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=502, detail="MDManser connector request failed") from exc


def _log_sync(db: Session, *, sync_type: str, direction: str, endpoint: str, status: str, status_code: int | None, request_summary: dict, response_summary: str):
    db.add(
        m.MDManserSyncLog(
            sync_type=sync_type,
            direction=direction,
            endpoint=endpoint,
            status=status,
            status_code=status_code,
            request_summary=json.dumps(request_summary, sort_keys=True),
            response_summary=(response_summary or "")[:2000],
        )
    )
    db.commit()


@router.get("/status")
def mdmanser_status():
    return {
        "mdmanser_base_url": mdmanser_base_url(),
        "base_url_configured": True,
        "php_session_configured": mdmanser_session_configured(),
    }


@router.get("/calendar/raw")
def mdmanser_calendar_raw(month: int = Query(..., ge=1, le=12), year: int = Query(..., ge=2000, le=2100)):
    try:
        client = MDManserClient()
        html = client.get_calendar_html(month=month, year=year)
    except Exception as exc:
        _raise_connector_error(exc)
    return {
        "status": "ok",
        "html_length": len(html),
        "contains_calendar": "calendar" in html.lower(),
        "contains_service_contract": "serviceContract" in html,
        "contains_engineer": "engineer" in html.lower(),
        "auth_ok": True,
    }


@router.post("/cases/{case_id}/write")
def mdmanser_write_case(case_id: str, payload: MDManserEditCasePayload, db: Session = Depends(get_db)):
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required for MDManser writes")
    request_summary = {
        "case_id": case_id,
        "new_id": payload.new_id,
        "visit_date": payload.visit_date,
        "engineer_id": payload.engineer_id,
        "followup_date": payload.followup_date,
        "followup_time": payload.followup_time,
        "status_id": payload.status_id,
        "priority_id": payload.priority_id,
        "note_length": len(payload.note or ""),
        "confirm": payload.confirm,
    }
    try:
        result = MDManserClient().edit_case(
            case_id=case_id,
            new_id=payload.new_id,
            visit_date=payload.visit_date,
            engineer_id=payload.engineer_id,
            note=payload.note,
            followup_date=payload.followup_date,
            followup_time=payload.followup_time,
            status_id=payload.status_id,
            priority_id=payload.priority_id,
        )
        _log_sync(
            db,
            sync_type="editCase",
            direction="write",
            endpoint=result["endpoint"],
            status="ok" if result["ok"] else "failed",
            status_code=result["status_code"],
            request_summary=request_summary,
            response_summary=result.get("response_text", ""),
        )
        return result
    except Exception as exc:
        _log_sync(
            db,
            sync_type="editCase",
            direction="write",
            endpoint="/process/other/ajax.php?f=editCase",
            status="error",
            status_code=getattr(exc, "status_code", None),
            request_summary=request_summary,
            response_summary=str(exc),
        )
        _raise_connector_error(exc)
