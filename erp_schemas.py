from pydantic import BaseModel

class ERPBase(BaseModel):
    class Config:
        orm_mode = True

class MDManserCalendarEventIn(ERPBase):
    title: str
    start_date: datetime.datetime
    end_date: datetime.datetime

class SaleIn(ERPBase):
    client_id: int
    amount: float
    date: datetime.datetime
    status: str

class ProcurementIn(ERPBase):
    supplier_id: int
    item_id: int
    quantity: int
    date: datetime.datetime
    status: str

class WarehouseIn(ERPBase):
    location: str
    capacity: int
    current_stock: int

class AftersalesIn(ERPBase):
    case_id: int
    issue_description: str
    resolution_date: datetime.datetime
    status: str

class CRMIn(ERPBase):
    client_id: int
    contact_id: int
    activity_date: datetime.datetime
    description: str

class DashboardIn(ERPBase):
    user_id: int
    widget_type: str
    data: str
