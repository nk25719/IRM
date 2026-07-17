from app.models.foundation import ClientSite
from app.services.base import BaseCrudService, DuplicateRecordError


class ClientSiteService(BaseCrudService[ClientSite]):
    model = ClientSite

    def create(self, values: dict):
        self._reject_duplicates(values["client_id"], values["site_code"])
        self._reject_multiple_primary(values["client_id"], values.get("is_primary"))
        return super().create(values)

    def update(self, record_id: int, values: dict):
        record = self.get_by_id(record_id, include_deleted=True)
        client_id = values.get("client_id", record.client_id)
        site_code = values.get("site_code", record.site_code)
        self._reject_duplicates(client_id, site_code, record_id)
        self._reject_multiple_primary(client_id, values.get("is_primary"), record_id)
        return super().update(record_id, values)

    def _reject_duplicates(self, client_id: int, site_code: str, record_id: int | None = None):
        query = self.db.query(ClientSite).filter(ClientSite.client_id == client_id, ClientSite.site_code == site_code)
        if record_id is not None:
            query = query.filter(ClientSite.id != record_id)
        if query.first():
            raise DuplicateRecordError("client site code already exists for this client")

    def _reject_multiple_primary(self, client_id: int, is_primary: bool | None, record_id: int | None = None):
        if not is_primary:
            return
        query = self.db.query(ClientSite).filter(
            ClientSite.client_id == client_id,
            ClientSite.is_primary.is_(True),
            ClientSite.is_deleted.is_(False),
        )
        if record_id is not None:
            query = query.filter(ClientSite.id != record_id)
        if query.first():
            raise DuplicateRecordError("client already has a primary site")
