from app.models.foundation import Supplier
from app.services.base import BaseCrudService, DuplicateRecordError


class SupplierService(BaseCrudService[Supplier]):
    model = Supplier

    def create(self, values: dict):
        self._reject_duplicates(values.get("supplier_code"))
        return super().create(values)

    def update(self, record_id: int, values: dict):
        self._reject_duplicates(values.get("supplier_code"), record_id)
        return super().update(record_id, values)

    def _reject_duplicates(self, supplier_code: str | None, record_id: int | None = None):
        if not supplier_code:
            return
        query = self.db.query(Supplier).filter(Supplier.supplier_code == supplier_code)
        if record_id is not None:
            query = query.filter(Supplier.id != record_id)
        if query.first():
            raise DuplicateRecordError("supplier code already exists")
