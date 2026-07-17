from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from app.schemas.common import FoundationSchema, TimestampFields, normalized_name, validate_code, validate_country_code, validate_email


class ManufacturerCreate(FoundationSchema):
    code: str | None = None
    name: str
    legal_name: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    country_code: str | None = None
    status: str = "active"

    @field_validator("code")
    @classmethod
    def _code(cls, value):
        return validate_code(value)

    @field_validator("email")
    @classmethod
    def _email(cls, value):
        return validate_email(value)

    @field_validator("country_code")
    @classmethod
    def _country(cls, value):
        return validate_country_code(value)


class ManufacturerUpdate(FoundationSchema):
    code: str | None = None
    name: str | None = None
    legal_name: str | None = None
    website: str | None = None
    email: str | None = None
    phone: str | None = None
    country_code: str | None = None
    status: str | None = None

    _code = field_validator("code")(classmethod(lambda cls, value: validate_code(value)))
    _email = field_validator("email")(classmethod(lambda cls, value: validate_email(value)))
    _country = field_validator("country_code")(classmethod(lambda cls, value: validate_country_code(value)))


class ManufacturerRead(ManufacturerCreate, TimestampFields):
    id: int
    normalized_name: str
    deleted_at: datetime | None = None
    is_deleted: bool = False


class ManufacturerList(FoundationSchema):
    items: list[ManufacturerRead]
    total: int
    limit: int
    offset: int


class ManufacturerAliasCreate(FoundationSchema):
    manufacturer_id: int
    alias: str
    source: str | None = None
    is_verified: bool = False
    confidence: int = 0


class ManufacturerAliasUpdate(FoundationSchema):
    manufacturer_id: int | None = None
    alias: str | None = None
    source: str | None = None
    is_verified: bool | None = None
    confidence: int | None = None


class ManufacturerAliasRead(ManufacturerAliasCreate, TimestampFields):
    id: int
    normalized_alias: str
    deleted_at: datetime | None = None
    is_deleted: bool = False


class ManufacturerAliasList(FoundationSchema):
    items: list[ManufacturerAliasRead]
    total: int
    limit: int
    offset: int


class SupplierCreate(FoundationSchema):
    supplier_code: str
    name: str
    legal_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    tax_number: str | None = None
    country_code: str | None = None
    status: str = "active"

    @field_validator("supplier_code")
    @classmethod
    def _supplier_code(cls, value):
        return validate_code(value, "supplier_code")

    _email = field_validator("email")(classmethod(lambda cls, value: validate_email(value)))
    _country = field_validator("country_code")(classmethod(lambda cls, value: validate_country_code(value)))


class SupplierUpdate(FoundationSchema):
    supplier_code: str | None = None
    name: str | None = None
    legal_name: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    tax_number: str | None = None
    country_code: str | None = None
    status: str | None = None

    _supplier_code = field_validator("supplier_code")(classmethod(lambda cls, value: validate_code(value, "supplier_code")))
    _email = field_validator("email")(classmethod(lambda cls, value: validate_email(value)))
    _country = field_validator("country_code")(classmethod(lambda cls, value: validate_country_code(value)))


class SupplierRead(SupplierCreate, TimestampFields):
    id: int
    deleted_at: datetime | None = None
    is_deleted: bool = False


class SupplierList(FoundationSchema):
    items: list[SupplierRead]
    total: int
    limit: int
    offset: int


class ClientSiteCreate(FoundationSchema):
    client_id: int
    site_code: str
    name: str
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool = False
    status: str = "active"

    _site_code = field_validator("site_code")(classmethod(lambda cls, value: validate_code(value, "site_code")))
    _email = field_validator("email")(classmethod(lambda cls, value: validate_email(value)))
    _country = field_validator("country_code")(classmethod(lambda cls, value: validate_country_code(value)))


class ClientSiteUpdate(FoundationSchema):
    site_code: str | None = None
    name: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country_code: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool | None = None
    status: str | None = None

    _site_code = field_validator("site_code")(classmethod(lambda cls, value: validate_code(value, "site_code")))
    _email = field_validator("email")(classmethod(lambda cls, value: validate_email(value)))
    _country = field_validator("country_code")(classmethod(lambda cls, value: validate_country_code(value)))


class ClientSiteRead(ClientSiteCreate, TimestampFields):
    id: int
    deleted_at: datetime | None = None
    is_deleted: bool = False


class ClientSiteList(FoundationSchema):
    items: list[ClientSiteRead]
    total: int
    limit: int
    offset: int


class LocationCreate(FoundationSchema):
    client_id: int | None = None
    site_id: int | None = None
    department_id: int | None = None
    parent_location_id: int | None = None
    location_code: str
    name: str
    location_type: str = "site_area"
    floor: str | None = None
    room: str | None = None
    description: str | None = None
    status: str = "active"

    _location_code = field_validator("location_code")(classmethod(lambda cls, value: validate_code(value, "location_code")))


class LocationUpdate(FoundationSchema):
    client_id: int | None = None
    site_id: int | None = None
    department_id: int | None = None
    parent_location_id: int | None = None
    location_code: str | None = None
    name: str | None = None
    location_type: str | None = None
    floor: str | None = None
    room: str | None = None
    description: str | None = None
    status: str | None = None

    _location_code = field_validator("location_code")(classmethod(lambda cls, value: validate_code(value, "location_code")))


class LocationRead(LocationCreate, TimestampFields):
    id: int
    deleted_at: datetime | None = None
    is_deleted: bool = False


class LocationList(FoundationSchema):
    items: list[LocationRead]
    total: int
    limit: int
    offset: int


class EquipmentCategoryCreate(FoundationSchema):
    code: str
    name: str
    description: str | None = None
    parent_category_id: int | None = None
    status: str = "active"

    _code = field_validator("code")(classmethod(lambda cls, value: validate_code(value)))


class EquipmentCategoryUpdate(FoundationSchema):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    parent_category_id: int | None = None
    status: str | None = None

    _code = field_validator("code")(classmethod(lambda cls, value: validate_code(value)))


class EquipmentCategoryRead(EquipmentCategoryCreate, TimestampFields):
    id: int
    normalized_name: str
    deleted_at: datetime | None = None
    is_deleted: bool = False


class EquipmentCategoryList(FoundationSchema):
    items: list[EquipmentCategoryRead]
    total: int
    limit: int
    offset: int


class EquipmentCategoryAliasCreate(FoundationSchema):
    equipment_category_id: int
    alias: str
    source: str | None = None
    is_verified: bool = False
    confidence: int = 0


class EquipmentCategoryAliasUpdate(FoundationSchema):
    equipment_category_id: int | None = None
    alias: str | None = None
    source: str | None = None
    is_verified: bool | None = None
    confidence: int | None = None


class EquipmentCategoryAliasRead(EquipmentCategoryAliasCreate, TimestampFields):
    id: int
    normalized_alias: str
    deleted_at: datetime | None = None
    is_deleted: bool = False


class EquipmentCategoryAliasList(FoundationSchema):
    items: list[EquipmentCategoryAliasRead]
    total: int
    limit: int
    offset: int


def manufacturer_values(payload: ManufacturerCreate | ManufacturerUpdate) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if values.get("name"):
        values["normalized_name"] = normalized_name(values["name"])
    return values


def category_values(payload: EquipmentCategoryCreate | EquipmentCategoryUpdate) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if values.get("name"):
        values["normalized_name"] = normalized_name(values["name"])
    return values


def manufacturer_alias_values(payload: ManufacturerAliasCreate | ManufacturerAliasUpdate) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if values.get("alias"):
        values["normalized_alias"] = normalized_name(values["alias"])
    return values


def equipment_category_alias_values(payload: EquipmentCategoryAliasCreate | EquipmentCategoryAliasUpdate) -> dict:
    values = payload.model_dump(exclude_unset=True)
    if values.get("alias"):
        values["normalized_alias"] = normalized_name(values["alias"])
    return values
