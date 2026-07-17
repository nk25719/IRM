from app.models.foundation import EquipmentCategory, EquipmentCategoryAlias, Location
from app.schemas.common import normalized_name
from app.services.base import BaseCrudService, DuplicateRecordError, ServiceError


class LocationService(BaseCrudService[Location]):
    model = Location

    def create(self, values: dict):
        self._reject_duplicates(values.get("site_id"), values["location_code"])
        return super().create(values)

    def update(self, record_id: int, values: dict):
        record = self.get_by_id(record_id, include_deleted=True)
        site_id = values.get("site_id", record.site_id)
        code = values.get("location_code", record.location_code)
        if values.get("parent_location_id") == record_id:
            raise ServiceError("location cannot be its own parent")
        self._reject_duplicates(site_id, code, record_id)
        return super().update(record_id, values)

    def _reject_duplicates(self, site_id: int | None, code: str, record_id: int | None = None):
        if site_id is None:
            return
        query = self.db.query(Location).filter(Location.site_id == site_id, Location.location_code == code)
        if record_id is not None:
            query = query.filter(Location.id != record_id)
        if query.first():
            raise DuplicateRecordError("location code already exists for this site")


class EquipmentCategoryService(BaseCrudService[EquipmentCategory]):
    model = EquipmentCategory

    def create(self, values: dict):
        values = dict(values)
        values["normalized_name"] = normalized_name(values["name"])
        self._reject_duplicates(values["code"], values.get("parent_category_id"), values["normalized_name"])
        return super().create(values)

    def update(self, record_id: int, values: dict):
        values = dict(values)
        record = self.get_by_id(record_id, include_deleted=True)
        if values.get("parent_category_id") == record_id:
            raise ServiceError("equipment category cannot be its own parent")
        if values.get("name"):
            values["normalized_name"] = normalized_name(values["name"])
        code = values.get("code", record.code)
        parent_id = values.get("parent_category_id", record.parent_category_id)
        name = values.get("normalized_name", record.normalized_name)
        self._reject_duplicates(code, parent_id, name, record_id)
        return super().update(record_id, values)

    def _reject_duplicates(self, code: str, parent_id: int | None, name: str, record_id: int | None = None):
        code_query = self.db.query(EquipmentCategory).filter(EquipmentCategory.code == code)
        name_query = self.db.query(EquipmentCategory).filter(
            EquipmentCategory.parent_category_id == parent_id,
            EquipmentCategory.normalized_name == name,
        )
        if record_id is not None:
            code_query = code_query.filter(EquipmentCategory.id != record_id)
            name_query = name_query.filter(EquipmentCategory.id != record_id)
        if code_query.first():
            raise DuplicateRecordError("equipment category code already exists")
        if name_query.first():
            raise DuplicateRecordError("equipment category name already exists under this parent")


class EquipmentCategoryAliasService(BaseCrudService[EquipmentCategoryAlias]):
    model = EquipmentCategoryAlias

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
            raise ServiceError("verified equipment category aliases cannot be soft-deleted through normal operations")
        return super().soft_delete(record_id)

    def find_verified(self, raw_value: str):
        normalized = normalized_name(raw_value)
        return (
            self.db.query(EquipmentCategoryAlias)
            .filter(
                EquipmentCategoryAlias.normalized_alias == normalized,
                EquipmentCategoryAlias.is_verified.is_(True),
                EquipmentCategoryAlias.is_deleted.is_(False),
            )
            .first()
        )

    def _reject_duplicate(self, normalized_alias: str, record_id: int | None = None):
        query = self.db.query(EquipmentCategoryAlias).filter(EquipmentCategoryAlias.normalized_alias == normalized_alias)
        if record_id is not None:
            query = query.filter(EquipmentCategoryAlias.id != record_id)
        if query.first():
            raise DuplicateRecordError("equipment category alias already exists")
