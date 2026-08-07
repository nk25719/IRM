from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.erp_models import Client
from ._legacy import mount_legacy_routes

router = APIRouter(tags=["CRM API"])


@router.get("/api/clients")
def list_clients(q: str = "", status: str = "", db: Session = Depends(get_db)):
    query = select(Client).order_by(Client.name)
    if q:
        query = query.where(Client.name.ilike(f"%{q.strip()}%"))
    if status:
        query = query.where(Client.status == status)
    return [
        {
            "id": client.id,
            "name": client.name,
            "location": client.location,
            "address": client.address,
            "status": client.status,
            "financial_status": client.financial_status,
        }
        for client in db.execute(query).scalars()
    ]

_PREFIXES = (
    "/api/crm",
    "/api/clients",
    "/api/departments",
    "/api/equipment",
    "/api/contracts",
    "/api/service-calls",
    "/api/cases",
    "/api/unified-case-entry",
)


mount_legacy_routes(
    router,
    lambda path: path.startswith(_PREFIXES) and not path.startswith("/api/equipment-bids"),
)
