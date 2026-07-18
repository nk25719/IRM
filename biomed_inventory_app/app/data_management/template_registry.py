from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TemplateField:
    name: str
    label: str
    data_type: str = "text"
    required: bool = False
    description: str = ""
    example: Any = ""
    validation_rule: str = ""
    sensitive: bool = False
    export_default: bool = True


@dataclass(frozen=True)
class DatasetDefinition:
    dataset_key: str
    display_name: str
    domain: str
    description: str
    version: str
    updated_at: str
    fields: tuple[TemplateField, ...]
    accepted_values: dict[str, tuple[str, ...]] = field(default_factory=dict)
    example_rows: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    permission: str = "data_management.view"
    import_supported: bool = False
    export_supported: bool = False
    export_table: str | None = None
    export_order_by: str | None = None

    @property
    def required_fields(self) -> list[str]:
        return [field.name for field in self.fields if field.required]

    @property
    def optional_fields(self) -> list[str]:
        return [field.name for field in self.fields if not field.required]

    @property
    def field_names(self) -> list[str]:
        return [field.name for field in self.fields]

    @property
    def export_fields(self) -> list[str]:
        return [field.name for field in self.fields if not field.sensitive]

    @property
    def default_export_fields(self) -> list[str]:
        return [field.name for field in self.fields if field.export_default and not field.sensitive]


REGISTRY_VERSION = "2026.07.17"
REGISTRY_UPDATED_AT = date(2026, 7, 17).isoformat()


def f(name: str, label: str, *, required: bool = False, data_type: str = "text", description: str = "", example: Any = "", validation_rule: str = "", sensitive: bool = False, export_default: bool = True) -> TemplateField:
    return TemplateField(name, label, data_type, required, description, example, validation_rule, sensitive, export_default)


DATASETS: tuple[DatasetDefinition, ...] = (
    DatasetDefinition(
        "clients",
        "Clients",
        "Master data",
        "Customer organizations and hospitals.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("client_code", "Client Code", description="Stable customer code.", example="CLIENT-001"),
            f("client_name", "Client Name", required=True, description="Customer or hospital display name.", example="Example Hospital"),
            f("city", "City", example="Beirut"),
            f("address", "Address"),
            f("main_contact", "Main Contact"),
            f("contact_email", "Contact Email", data_type="email"),
            f("phone", "Phone"),
            f("status", "Status", example="active", validation_rule="active, inactive, archived"),
            f("notes", "Notes"),
        ),
        {"status": ("active", "inactive", "archived")},
        ({"client_code": "CLIENT-001", "client_name": "Example Hospital", "city": "Beirut", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="clients",
        export_order_by="name",
    ),
    DatasetDefinition(
        "departments",
        "Departments",
        "Master data",
        "Customer departments linked to clients.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("client_code", "Client Code", example="CLIENT-001"),
            f("client_name", "Client Name", required=True, example="Example Hospital"),
            f("department_code", "Department Code", example="ICU"),
            f("department_name", "Department Name", required=True, example="ICU"),
            f("floor_location", "Floor / Location"),
            f("main_contact_name", "Main Contact"),
            f("phone", "Phone"),
            f("email", "Email", data_type="email"),
            f("notes", "Notes"),
        ),
        example_rows=({"client_code": "CLIENT-001", "department_code": "ICU", "department_name": "ICU"},),
        import_supported=True,
        export_supported=True,
        export_table="departments",
        export_order_by="department_name",
    ),
    DatasetDefinition(
        "contacts",
        "Contacts",
        "Master data",
        "People at clients or departments.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("client_code", "Client Code"),
            f("client_name", "Client Name", required=True),
            f("department_name", "Department Name"),
            f("contact_name", "Contact Name", required=True, example="Jane Example"),
            f("role", "Role", example="Biomedical Engineer"),
            f("email", "Email", data_type="email"),
            f("phone", "Phone"),
            f("notes", "Notes"),
        ),
        example_rows=({"client_code": "CLIENT-001", "contact_name": "Jane Example", "role": "Biomedical Engineer"},),
        import_supported=True,
        export_supported=True,
        export_table="contacts",
        export_order_by="name",
    ),
    DatasetDefinition(
        "manufacturers",
        "Manufacturers",
        "Master data",
        "Canonical equipment manufacturers.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("code", "Manufacturer Code", example="GE"),
            f("name", "Manufacturer Name", required=True, example="GE HealthCare"),
            f("legal_name", "Legal Name"),
            f("website", "Website"),
            f("email", "Email", data_type="email"),
            f("phone", "Phone"),
            f("country_code", "Country Code", validation_rule="ISO 3166-1 alpha-2"),
            f("status", "Status", example="active", validation_rule="active, inactive"),
        ),
        {"status": ("active", "inactive")},
        ({"code": "GE", "name": "GE HealthCare", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="manufacturers",
        export_order_by="name",
    ),
    DatasetDefinition(
        "suppliers",
        "Suppliers",
        "Master data",
        "Supplier master records.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("supplier_code", "Supplier Code", required=True, example="SUP-001"),
            f("name", "Supplier Name", required=True, example="Example Supplier"),
            f("legal_name", "Legal Name"),
            f("email", "Email", data_type="email"),
            f("phone", "Phone"),
            f("website", "Website"),
            f("tax_number", "Tax Number"),
            f("country_code", "Country Code"),
            f("status", "Status", example="active", validation_rule="active, inactive"),
        ),
        {"status": ("active", "inactive")},
        ({"supplier_code": "SUP-001", "name": "Example Supplier", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="suppliers",
        export_order_by="name",
    ),
    DatasetDefinition(
        "equipment_categories",
        "Equipment Categories",
        "Master data",
        "Biomedical equipment category taxonomy.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("code", "Category Code", required=True, example="PATIENT_MONITORING"),
            f("name", "Category Name", required=True, example="Patient Monitoring"),
            f("parent_code", "Parent Category Code"),
            f("description", "Description"),
            f("status", "Status", example="active", validation_rule="active, inactive"),
        ),
        {"status": ("active", "inactive")},
        ({"code": "PATIENT_MONITORING", "name": "Patient Monitoring", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="equipment_categories",
        export_order_by="code",
    ),
    DatasetDefinition(
        "equipment_models",
        "Equipment Models",
        "Master data",
        "Manufacturer model names linked to manufacturer and category references.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("manufacturer_code", "Manufacturer Code"),
            f("manufacturer", "Manufacturer", example="GE HealthCare"),
            f("equipment_category_code", "Equipment Category Code"),
            f("equipment_category", "Equipment Category", example="Patient Monitoring"),
            f("model", "Model", required=True, example="Dash 4000"),
            f("description", "Description"),
            f("status", "Status", example="active"),
        ),
        {"status": ("active", "inactive")},
        ({"manufacturer": "GE HealthCare", "equipment_category": "Patient Monitoring", "model": "Dash 4000", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="equipment_models",
        export_order_by="model",
    ),
    DatasetDefinition(
        "equipment",
        "Equipment",
        "Operations",
        "Installed equipment records.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("client_code", "Client Code", example="CLIENT-001"),
            f("client_name", "Client Name", required=True, example="Example Hospital"),
            f("site_code", "Site Code"),
            f("department_name", "Department Name"),
            f("equipment_category", "Equipment Category"),
            f("manufacturer", "Manufacturer"),
            f("model", "Model"),
            f("serial_number", "Serial Number", required=True, example="SN-001"),
            f("asset_number", "Asset Number"),
            f("installation_date", "Installation Date", data_type="date"),
            f("warranty_start_date", "Warranty Start Date", data_type="date"),
            f("warranty_end_date", "Warranty End Date", data_type="date"),
            f("status", "Status", example="active"),
            f("location", "Location"),
            f("notes", "Notes"),
        ),
        {"status": ("active", "inactive", "under_service", "retired")},
        ({"client_code": "CLIENT-001", "equipment_category": "Patient Monitoring", "manufacturer": "GE HealthCare", "model": "Dash 4000", "serial_number": "SN-001", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="equipment",
        export_order_by="serial_number",
    ),
    DatasetDefinition(
        "inventory_items",
        "Inventory Items",
        "Commercial and warehouse",
        "Warehouse item master.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("pn", "Part Number", required=True, example="PN-001"),
            f("item_code", "Item Code"),
            f("description", "Description", required=True, example="ECG Cable"),
            f("item_category", "Item Category", example="spare_parts"),
            f("device_family", "Device Family"),
            f("barcode", "Barcode"),
            f("status", "Status", example="active"),
        ),
        {"status": ("active", "inactive")},
        ({"pn": "PN-001", "description": "ECG Cable", "item_category": "spare_parts", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="inventory_items",
        export_order_by="pn",
    ),
    DatasetDefinition("service_cases", "Service Cases", "Operations", "Case-level service records.", REGISTRY_VERSION, REGISTRY_UPDATED_AT, (f("case_no", "Case Number", required=True), f("client_name", "Client Name", required=True), f("status", "Status")), import_supported=False, export_supported=False),
    DatasetDefinition("service_calls", "Service Calls", "Operations", "After-Sales service calls.", REGISTRY_VERSION, REGISTRY_UPDATED_AT, (f("client_name", "Client Name", required=True), f("call_no", "Call Number", required=True), f("issue", "Issue"), f("status", "Status")), example_rows=({"client_name": "Example Hospital", "call_no": "SC-001", "issue": "No display", "status": "open"},), import_supported=True, export_supported=False),
    DatasetDefinition("preventive_maintenance", "Preventive Maintenance", "Operations", "Preventive maintenance tasks.", REGISTRY_VERSION, REGISTRY_UPDATED_AT, (f("equipment_serial", "Equipment Serial"), f("task_name", "Task Name", required=True), f("due_date", "Due Date", data_type="date"), f("status", "Status")), import_supported=False, export_supported=False),
    DatasetDefinition("contracts", "Contracts", "Operations", "Service and commercial contracts.", REGISTRY_VERSION, REGISTRY_UPDATED_AT, (f("client_code", "Client Code", required=True), f("contract_number", "Contract Number", required=True), f("contract_type", "Contract Type"), f("start_date", "Start Date", data_type="date"), f("end_date", "End Date", data_type="date"), f("status", "Status")), import_supported=False, export_supported=False),
    DatasetDefinition("quotations", "Quotations", "Commercial and warehouse", "Quotation headers.", REGISTRY_VERSION, REGISTRY_UPDATED_AT, (f("client_code", "Client Code", required=True), f("quotation_number", "Quotation Number", required=True), f("quotation_date", "Quotation Date", data_type="date"), f("status", "Status"), f("currency", "Currency")), import_supported=False, export_supported=False),
    DatasetDefinition("quotation_items", "Quotation Items", "Commercial and warehouse", "Quotation line items.", REGISTRY_VERSION, REGISTRY_UPDATED_AT, (f("quotation_number", "Quotation Number", required=True), f("item_code", "Item Code"), f("description", "Description", required=True), f("quantity", "Quantity", data_type="number"), f("unit_price", "Unit Price", data_type="money", sensitive=True)), import_supported=False, export_supported=False),
)


def all_datasets() -> list[DatasetDefinition]:
    validate_registry()
    return list(DATASETS)


def get_dataset(dataset_key: str) -> DatasetDefinition:
    validate_registry()
    for dataset in DATASETS:
        if dataset.dataset_key == dataset_key:
            return dataset
    raise KeyError(dataset_key)


def validate_registry() -> None:
    keys = set()
    for dataset in DATASETS:
        if dataset.dataset_key in keys:
            raise ValueError(f"duplicate dataset key: {dataset.dataset_key}")
        keys.add(dataset.dataset_key)
        field_names = dataset.field_names
        if len(field_names) != len(set(field_names)):
            raise ValueError(f"duplicate field names in {dataset.dataset_key}")
        missing = set(dataset.required_fields) - set(field_names)
        if missing:
            raise ValueError(f"required fields missing from {dataset.dataset_key}: {sorted(missing)}")
