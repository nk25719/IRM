from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class ServiceError(ValueError):
    pass


class DuplicateRecordError(ServiceError):
    pass


class NotFoundError(ServiceError):
    pass


class BaseCrudService(Generic[ModelT]):
    model: type[ModelT]
    immutable_fields = {"id", "created_at", "updated_at", "deleted_at", "is_deleted"}

    def __init__(self, db: Session):
        self.db = db

    def list(self, limit: int = 100, offset: int = 0, include_deleted: bool = False):
        query = self.db.query(self.model)
        if hasattr(self.model, "is_deleted") and not include_deleted:
            query = query.filter(self.model.is_deleted.is_(False))
        return query.order_by(self.model.id.desc()).offset(offset).limit(limit).all()

    def count(self, include_deleted: bool = False) -> int:
        query = self.db.query(self.model)
        if hasattr(self.model, "is_deleted") and not include_deleted:
            query = query.filter(self.model.is_deleted.is_(False))
        return query.count()

    def get_by_id(self, record_id: int, include_deleted: bool = False):
        query = self.db.query(self.model).filter(self.model.id == record_id)
        if hasattr(self.model, "is_deleted") and not include_deleted:
            query = query.filter(self.model.is_deleted.is_(False))
        record = query.first()
        if record is None:
            raise NotFoundError(f"{self.model.__name__} {record_id} not found")
        return record

    def create(self, values: dict[str, Any]):
        record = self.model(**values)
        self.db.add(record)
        return self._commit_refresh(record)

    def update(self, record_id: int, values: dict[str, Any]):
        record = self.get_by_id(record_id, include_deleted=True)
        values = {key: value for key, value in values.items() if key not in self.immutable_fields}
        for key, value in values.items():
            setattr(record, key, value)
        return self._commit_refresh(record)

    def soft_delete(self, record_id: int):
        record = self.get_by_id(record_id, include_deleted=True)
        if not hasattr(record, "is_deleted"):
            raise ServiceError(f"{self.model.__name__} does not support soft deletion")
        record.is_deleted = True
        record.deleted_at = datetime.now(timezone.utc)
        return self._commit_refresh(record)

    def restore(self, record_id: int):
        record = self.get_by_id(record_id, include_deleted=True)
        if not hasattr(record, "is_deleted"):
            raise ServiceError(f"{self.model.__name__} does not support restore")
        record.is_deleted = False
        record.deleted_at = None
        return self._commit_refresh(record)

    def _commit_refresh(self, record):
        try:
            self.db.commit()
            self.db.refresh(record)
            return record
        except IntegrityError as exc:
            self.db.rollback()
            raise DuplicateRecordError("record violates a unique or foreign-key constraint") from exc
        except Exception:
            self.db.rollback()
            raise
