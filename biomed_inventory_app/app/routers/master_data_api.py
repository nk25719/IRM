from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import master_data as s
from app.services.base import DuplicateRecordError, NotFoundError, ServiceError
from app.services.client_site_service import ClientSiteService
from app.services.location_service import EquipmentCategoryAliasService, EquipmentCategoryService, LocationService
from app.services.manufacturer_service import ManufacturerAliasService, ManufacturerService
from app.services.supplier_service import SupplierService

router = APIRouter(prefix="/api/master-data", tags=["master-data"])


def _limit(value: int = Query(100, ge=1, le=500)) -> int:
    return value


def _handle_error(exc: Exception):
    if isinstance(exc, DuplicateRecordError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ServiceError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.post("/manufacturers", response_model=s.ManufacturerRead, status_code=201)
def create_manufacturer(payload: s.ManufacturerCreate, db: Session = Depends(get_db)):
    try:
        return ManufacturerService(db).create(s.manufacturer_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.get("/manufacturers", response_model=s.ManufacturerList)
def list_manufacturers(
    limit: int = Depends(_limit),
    offset: int = Query(0, ge=0),
    include_deleted: bool = False,
    db: Session = Depends(get_db),
):
    service = ManufacturerService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/manufacturers/{record_id}", response_model=s.ManufacturerRead)
def get_manufacturer(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return ManufacturerService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/manufacturers/{record_id}", response_model=s.ManufacturerRead)
def update_manufacturer(record_id: int, payload: s.ManufacturerUpdate, db: Session = Depends(get_db)):
    try:
        return ManufacturerService(db).update(record_id, s.manufacturer_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/manufacturers/{record_id}", response_model=s.ManufacturerRead)
def delete_manufacturer(record_id: int, db: Session = Depends(get_db)):
    try:
        return ManufacturerService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/manufacturers/{record_id}/restore", response_model=s.ManufacturerRead)
def restore_manufacturer(record_id: int, db: Session = Depends(get_db)):
    try:
        return ManufacturerService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/manufacturer-aliases", response_model=s.ManufacturerAliasRead, status_code=201)
def create_manufacturer_alias(payload: s.ManufacturerAliasCreate, db: Session = Depends(get_db)):
    try:
        return ManufacturerAliasService(db).create(s.manufacturer_alias_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.get("/manufacturer-aliases", response_model=s.ManufacturerAliasList)
def list_manufacturer_aliases(limit: int = Depends(_limit), offset: int = Query(0, ge=0), include_deleted: bool = False, db: Session = Depends(get_db)):
    service = ManufacturerAliasService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/manufacturer-aliases/{record_id}", response_model=s.ManufacturerAliasRead)
def get_manufacturer_alias(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return ManufacturerAliasService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/manufacturer-aliases/{record_id}", response_model=s.ManufacturerAliasRead)
def update_manufacturer_alias(record_id: int, payload: s.ManufacturerAliasUpdate, db: Session = Depends(get_db)):
    try:
        return ManufacturerAliasService(db).update(record_id, s.manufacturer_alias_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/manufacturer-aliases/{record_id}", response_model=s.ManufacturerAliasRead)
def delete_manufacturer_alias(record_id: int, db: Session = Depends(get_db)):
    try:
        return ManufacturerAliasService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/manufacturer-aliases/{record_id}/restore", response_model=s.ManufacturerAliasRead)
def restore_manufacturer_alias(record_id: int, db: Session = Depends(get_db)):
    try:
        return ManufacturerAliasService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/suppliers", response_model=s.SupplierRead, status_code=201)
def create_supplier(payload: s.SupplierCreate, db: Session = Depends(get_db)):
    try:
        return SupplierService(db).create(payload.model_dump())
    except Exception as exc:
        _handle_error(exc)


@router.get("/suppliers", response_model=s.SupplierList)
def list_suppliers(limit: int = Depends(_limit), offset: int = Query(0, ge=0), include_deleted: bool = False, db: Session = Depends(get_db)):
    service = SupplierService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/suppliers/{record_id}", response_model=s.SupplierRead)
def get_supplier(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return SupplierService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/suppliers/{record_id}", response_model=s.SupplierRead)
def update_supplier(record_id: int, payload: s.SupplierUpdate, db: Session = Depends(get_db)):
    try:
        return SupplierService(db).update(record_id, payload.model_dump(exclude_unset=True))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/suppliers/{record_id}", response_model=s.SupplierRead)
def delete_supplier(record_id: int, db: Session = Depends(get_db)):
    try:
        return SupplierService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/suppliers/{record_id}/restore", response_model=s.SupplierRead)
def restore_supplier(record_id: int, db: Session = Depends(get_db)):
    try:
        return SupplierService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/client-sites", response_model=s.ClientSiteRead, status_code=201)
def create_client_site(payload: s.ClientSiteCreate, db: Session = Depends(get_db)):
    try:
        return ClientSiteService(db).create(payload.model_dump())
    except Exception as exc:
        _handle_error(exc)


@router.get("/client-sites", response_model=s.ClientSiteList)
def list_client_sites(limit: int = Depends(_limit), offset: int = Query(0, ge=0), include_deleted: bool = False, db: Session = Depends(get_db)):
    service = ClientSiteService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/client-sites/{record_id}", response_model=s.ClientSiteRead)
def get_client_site(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return ClientSiteService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/client-sites/{record_id}", response_model=s.ClientSiteRead)
def update_client_site(record_id: int, payload: s.ClientSiteUpdate, db: Session = Depends(get_db)):
    try:
        return ClientSiteService(db).update(record_id, payload.model_dump(exclude_unset=True))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/client-sites/{record_id}", response_model=s.ClientSiteRead)
def delete_client_site(record_id: int, db: Session = Depends(get_db)):
    try:
        return ClientSiteService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/client-sites/{record_id}/restore", response_model=s.ClientSiteRead)
def restore_client_site(record_id: int, db: Session = Depends(get_db)):
    try:
        return ClientSiteService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/locations", response_model=s.LocationRead, status_code=201)
def create_location(payload: s.LocationCreate, db: Session = Depends(get_db)):
    try:
        return LocationService(db).create(payload.model_dump())
    except Exception as exc:
        _handle_error(exc)


@router.get("/locations", response_model=s.LocationList)
def list_locations(limit: int = Depends(_limit), offset: int = Query(0, ge=0), include_deleted: bool = False, db: Session = Depends(get_db)):
    service = LocationService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/locations/{record_id}", response_model=s.LocationRead)
def get_location(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return LocationService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/locations/{record_id}", response_model=s.LocationRead)
def update_location(record_id: int, payload: s.LocationUpdate, db: Session = Depends(get_db)):
    try:
        return LocationService(db).update(record_id, payload.model_dump(exclude_unset=True))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/locations/{record_id}", response_model=s.LocationRead)
def delete_location(record_id: int, db: Session = Depends(get_db)):
    try:
        return LocationService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/locations/{record_id}/restore", response_model=s.LocationRead)
def restore_location(record_id: int, db: Session = Depends(get_db)):
    try:
        return LocationService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/equipment-categories", response_model=s.EquipmentCategoryRead, status_code=201)
def create_equipment_category(payload: s.EquipmentCategoryCreate, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryService(db).create(s.category_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.get("/equipment-categories", response_model=s.EquipmentCategoryList)
def list_equipment_categories(limit: int = Depends(_limit), offset: int = Query(0, ge=0), include_deleted: bool = False, db: Session = Depends(get_db)):
    service = EquipmentCategoryService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/equipment-categories/{record_id}", response_model=s.EquipmentCategoryRead)
def get_equipment_category(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/equipment-categories/{record_id}", response_model=s.EquipmentCategoryRead)
def update_equipment_category(record_id: int, payload: s.EquipmentCategoryUpdate, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryService(db).update(record_id, s.category_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/equipment-categories/{record_id}", response_model=s.EquipmentCategoryRead)
def delete_equipment_category(record_id: int, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/equipment-categories/{record_id}/restore", response_model=s.EquipmentCategoryRead)
def restore_equipment_category(record_id: int, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/equipment-category-aliases", response_model=s.EquipmentCategoryAliasRead, status_code=201)
def create_equipment_category_alias(payload: s.EquipmentCategoryAliasCreate, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryAliasService(db).create(s.equipment_category_alias_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.get("/equipment-category-aliases", response_model=s.EquipmentCategoryAliasList)
def list_equipment_category_aliases(limit: int = Depends(_limit), offset: int = Query(0, ge=0), include_deleted: bool = False, db: Session = Depends(get_db)):
    service = EquipmentCategoryAliasService(db)
    return {"items": service.list(limit, offset, include_deleted), "total": service.count(include_deleted), "limit": limit, "offset": offset}


@router.get("/equipment-category-aliases/{record_id}", response_model=s.EquipmentCategoryAliasRead)
def get_equipment_category_alias(record_id: int, include_deleted: bool = False, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryAliasService(db).get_by_id(record_id, include_deleted)
    except Exception as exc:
        _handle_error(exc)


@router.patch("/equipment-category-aliases/{record_id}", response_model=s.EquipmentCategoryAliasRead)
def update_equipment_category_alias(record_id: int, payload: s.EquipmentCategoryAliasUpdate, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryAliasService(db).update(record_id, s.equipment_category_alias_values(payload))
    except Exception as exc:
        _handle_error(exc)


@router.delete("/equipment-category-aliases/{record_id}", response_model=s.EquipmentCategoryAliasRead)
def delete_equipment_category_alias(record_id: int, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryAliasService(db).soft_delete(record_id)
    except Exception as exc:
        _handle_error(exc)


@router.post("/equipment-category-aliases/{record_id}/restore", response_model=s.EquipmentCategoryAliasRead)
def restore_equipment_category_alias(record_id: int, db: Session = Depends(get_db)):
    try:
        return EquipmentCategoryAliasService(db).restore(record_id)
    except Exception as exc:
        _handle_error(exc)
