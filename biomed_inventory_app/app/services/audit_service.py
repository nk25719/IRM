from app.models.foundation import AuditEvent, StatusHistory
from app.services.base import BaseCrudService, ServiceError


class AuditEventService(BaseCrudService[AuditEvent]):
    model = AuditEvent

    def update(self, record_id: int, values: dict):
        raise ServiceError("audit events are append-only")

    def soft_delete(self, record_id: int):
        raise ServiceError("audit events are append-only")

    def restore(self, record_id: int):
        raise ServiceError("audit events are append-only")


class StatusHistoryService(BaseCrudService[StatusHistory]):
    model = StatusHistory

    def create(self, values: dict):
        if values.get("previous_status") and values["previous_status"] == values.get("new_status"):
            raise ServiceError("previous_status and new_status must differ")
        return super().create(values)

    def update(self, record_id: int, values: dict):
        raise ServiceError("status history is append-only")

    def soft_delete(self, record_id: int):
        raise ServiceError("status history is append-only")

    def restore(self, record_id: int):
        raise ServiceError("status history is append-only")
