from app.models.foundation import Manufacturer, ManufacturerAlias
from app.schemas.common import normalized_name
from app.services.base import BaseCrudService, DuplicateRecordError, ServiceError


class ManufacturerService(BaseCrudService[Manufacturer]):
    model = Manufacturer

    def create(self, values: dict):
        values = dict(values)
        values["normalized_name"] = normalized_name(values["name"])
        self._reject_duplicates(values.get("code"), values["normalized_name"])
        return super().create(values)

    def update(self, record_id: int, values: dict):
        values = dict(values)
        if values.get("name"):
            values["normalized_name"] = normalized_name(values["name"])
        self._reject_duplicates(values.get("code"), values.get("normalized_name"), record_id)
        return super().update(record_id, values)

    def _reject_duplicates(self, code: str | None, name: str | None, record_id: int | None = None):
        query = self.db.query(Manufacturer)
        if record_id is not None:
            query = query.filter(Manufacturer.id != record_id)
        if code and query.filter(Manufacturer.code == code).first():
            raise DuplicateRecordError("manufacturer code already exists")
        if name and query.filter(Manufacturer.normalized_name == name).first():
            raise DuplicateRecordError("manufacturer name already exists")


class ManufacturerAliasService(BaseCrudService[ManufacturerAlias]):
    model = ManufacturerAlias

    def create(self, values: dict):
        values = dict(values)
        values["normalized_alias"] = normalized_name(values["alias"])
        self._reject_duplicate(values["normalized_alias"])
        return super().create(values)

    def update(self, record_id: int, values: dict):
        values = dict(values)
        if values.get("alias"):
            values["normalized_alias"] = normalized_name(values["alias"])
        if values.get("normalized_alias"):
            self._reject_duplicate(values["normalized_alias"], record_id)
        return super().update(record_id, values)

    def soft_delete(self, record_id: int):
        record = self.get_by_id(record_id, include_deleted=True)
        if record.is_verified:
            raise ServiceError("verified manufacturer aliases cannot be soft-deleted through normal operations")
        return super().soft_delete(record_id)

    def find_verified(self, raw_value: str):
        normalized = normalized_name(raw_value)
        return (
            self.db.query(ManufacturerAlias)
            .filter(
                ManufacturerAlias.normalized_alias == normalized,
                ManufacturerAlias.is_verified.is_(True),
                ManufacturerAlias.is_deleted.is_(False),
            )
            .first()
        )

    def _reject_duplicate(self, normalized_alias: str, record_id: int | None = None):
        query = self.db.query(ManufacturerAlias).filter(ManufacturerAlias.normalized_alias == normalized_alias)
        if record_id is not None:
            query = query.filter(ManufacturerAlias.id != record_id)
        if query.first():
            raise DuplicateRecordError("manufacturer alias already exists")
