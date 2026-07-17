from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import imports as s
from app.services.base import DuplicateRecordError, NotFoundError
from app.services.import_service import ImportBatchService

router = APIRouter(prefix="/api/imports", tags=["imports"])


def _raise(exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, DuplicateRecordError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise exc


@router.post("/batches", response_model=s.ImportBatchRead, status_code=201)
def create_import_batch(payload: s.ImportBatchCreate, db: Session = Depends(get_db)):
    try:
        return ImportBatchService(db).create(payload.model_dump())
    except Exception as exc:
        _raise(exc)


@router.get("/batches", response_model=s.ImportBatchList)
def list_import_batches(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    service = ImportBatchService(db)
    return {"items": service.list(limit, offset), "total": service.count(), "limit": limit, "offset": offset}


@router.get("/batches/{record_id}", response_model=s.ImportBatchRead)
def get_import_batch(record_id: int, db: Session = Depends(get_db)):
    try:
        return ImportBatchService(db).get_by_id(record_id)
    except Exception as exc:
        _raise(exc)


@router.patch("/batches/{record_id}", response_model=s.ImportBatchRead)
def update_import_batch(record_id: int, payload: s.ImportBatchUpdate, db: Session = Depends(get_db)):
    try:
        return ImportBatchService(db).update(record_id, payload.model_dump(exclude_unset=True))
    except Exception as exc:
        _raise(exc)
