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
    template_filename: str | None = None

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


REGISTRY_VERSION = "2026.07.23"
REGISTRY_UPDATED_AT = date(2026, 7, 23).isoformat()


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
        "client_sites",
        "Client Sites",
        "Master data",
        "Physical client sites, branches, laboratories, or hospital campuses.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("client_code", "Client Code"),
            f("client_name", "Client Name", required=True, example="Example Hospital"),
            f("site_code", "Site Code", required=True, example="MAIN"),
            f("site_name", "Site Name", required=True, example="Main Campus"),
            f("address_line_1", "Address Line 1"),
            f("address_line_2", "Address Line 2"),
            f("city", "City"),
            f("region", "Region"),
            f("country_code", "Country Code"),
            f("phone", "Phone"),
            f("email", "Email", data_type="email"),
            f("is_primary", "Is Primary", validation_rule="YES/NO, TRUE/FALSE, 1/0"),
            f("status", "Status", validation_rule="active, inactive"),
        ),
        {"status": ("active", "inactive"), "is_primary": ("YES", "NO", "TRUE", "FALSE", "1", "0")},
        ({"client_name": "Example Hospital", "site_code": "MAIN", "site_name": "Main Campus", "is_primary": "YES", "status": "active"},),
        import_supported=True,
        export_supported=True,
        export_table="client_sites",
        export_order_by="site_code",
        template_filename="client_sites_import_template.xlsx",
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
    DatasetDefinition(
        "service_intelligence_installed_equipment",
        "MDmanser Installed Base",
        "Contract Intelligence / Manufacturer Coverage",
        "Installed equipment base used to compare manufacturer agreement coverage. Does not create customer contract coverage.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("external_equipment_id", "External Equipment ID", description="Equipment ID from the source system."),
            f("client_name", "Client Name", required=True, description="Customer or institution name.", example="Hotel Dieu"),
            f("client_code", "Client Code", description="Existing customer code."),
            f("site_name", "Site Name", required=True, description="Hospital branch, laboratory, or physical site.", example="Main Campus"),
            f("department_name", "Department Name", description="Department where equipment is installed."),
            f("manufacturer", "Manufacturer", required=True, description="Equipment manufacturer.", example="GE HealthCare"),
            f("equipment_category", "Equipment Category", description="Modality or category."),
            f("equipment_description", "Equipment Description", required=True, description="General equipment description.", example="Anesthesia workstation"),
            f("model", "Model", required=True, description="Equipment model.", example="CARESCAPE B850"),
            f("serial_number", "Serial Number", required=True, description="Manufacturer serial number.", example="SN-001"),
            f("asset_number", "Asset Number", description="Internal customer asset number."),
            f("system_id", "System ID", description="Manufacturer or source system ID."),
            f("global_order_number", "Global Order Number", description="Manufacturer order number."),
            f("installation_date", "Installation Date", data_type="date", validation_rule="YYYY-MM-DD"),
            f("acceptance_date", "Acceptance Date", data_type="date", validation_rule="YYYY-MM-DD"),
            f("equipment_status", "Equipment Status", validation_rule="ACTIVE, INACTIVE, DISPOSED, TRANSFERRED, UNKNOWN", example="ACTIVE"),
            f("location", "Location", description="Room, floor, department, or location details."),
            f("source", "Source", description="Source file or system."),
            f("notes", "Notes"),
        ),
        {"equipment_status": ("ACTIVE", "INACTIVE", "DISPOSED", "TRANSFERRED", "UNKNOWN")},
        ({"client_name": "Hotel Dieu", "site_name": "Main Campus", "manufacturer": "GE HealthCare", "equipment_description": "Anesthesia workstation", "model": "CARESCAPE B850", "serial_number": "SN-001", "installation_date": "2026-01-15", "equipment_status": "ACTIVE"},),
        import_supported=True,
        export_supported=True,
        export_table="equipment",
        export_order_by="serial_number",
        template_filename="installed_equipment_import_template.xlsx",
    ),
    DatasetDefinition(
        "service_intelligence_equipment_warranty",
        "Manufacturer Warranty",
        "Contract Intelligence / Manufacturer Coverage",
        "Manufacturer warranty periods linked to installed equipment. Does not create customer contract coverage.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("serial_number", "Serial Number", required=True, description="Equipment serial number used for matching."),
            f("manufacturer", "Manufacturer", description="Recommended when duplicate serial numbers exist."),
            f("client_name", "Client Name", description="Secondary validation field."),
            f("site_name", "Site Name", description="Secondary validation field."),
            f("warranty_start_date", "Warranty Start Date", data_type="date", validation_rule="YYYY-MM-DD"),
            f("warranty_end_date", "Warranty End Date", required=True, data_type="date", validation_rule="YYYY-MM-DD; cannot be before warranty_start_date"),
            f("warranty_type", "Warranty Type", validation_rule="STANDARD, EXTENDED, PARTS_ONLY, LABOR_ONLY, FULL, OTHER, UNKNOWN"),
            f("warranty_provider", "Warranty Provider"),
            f("warranty_reference", "Warranty Reference"),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        {"warranty_type": ("STANDARD", "EXTENDED", "PARTS_ONLY", "LABOR_ONLY", "FULL", "OTHER", "UNKNOWN")},
        ({"serial_number": "SN-001", "manufacturer": "GE HealthCare", "warranty_start_date": "2026-01-15", "warranty_end_date": "2027-01-14", "warranty_type": "STANDARD"},),
        import_supported=True,
        export_supported=True,
        export_table="equipment",
        export_order_by="serial_number",
        template_filename="equipment_warranty_import_template.xlsx",
    ),
    DatasetDefinition(
        "manufacturer_agreements",
        "Manufacturer Agreements",
        "Contract Intelligence / Manufacturer Coverage",
        "Agreement headers between the manufacturer and our company as distributor.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("agreement_number", "Agreement Number", required=True),
            f("manufacturer", "Manufacturer", required=True),
            f("agreement_name", "Agreement Name"),
            f("agreement_status", "Agreement Status", required=True, validation_rule="DRAFT, PENDING, ACTIVE, EXPIRED, SUSPENDED, CANCELLED, RENEWED"),
            f("agreement_start_date", "Agreement Start Date", data_type="date"),
            f("agreement_end_date", "Agreement End Date", data_type="date"),
            f("last_covered_date", "Last Covered Date", data_type="date"),
            f("currency", "Currency"),
            f("restricted_manufacturer_value", "Restricted Manufacturer Value", data_type="money", sensitive=True),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        {"agreement_status": ("DRAFT", "PENDING", "ACTIVE", "EXPIRED", "SUSPENDED", "CANCELLED", "RENEWED")},
        ({"agreement_number": "GE-ANNEXURE-2026", "manufacturer": "GE HealthCare", "agreement_status": "ACTIVE", "agreement_start_date": "2026-01-01", "agreement_end_date": "2026-12-31"},),
        import_supported=True,
        export_supported=True,
        export_table="manufacturer_agreements",
        export_order_by="agreement_number",
        template_filename="manufacturer_agreements_import_template.xlsx",
    ),
    DatasetDefinition(
        "manufacturer_covered_equipment",
        "Manufacturer-Covered Equipment",
        "Contract Intelligence / Manufacturer Coverage",
        "GE ANNEXURE equipment rows. Coverage here never implies customer service contract coverage.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("agreement_number", "Agreement Number", required=True),
            f("system_id", "System ID"),
            f("serial_number", "Serial Number", required=True),
            f("global_order_number", "Global Order Number"),
            f("equipment_description", "Equipment Description"),
            f("client_site", "Client Site"),
            f("restricted_manufacturer_value", "Restricted Manufacturer Value", data_type="money", sensitive=True),
            f("last_covered_date", "Last Covered Date", data_type="date"),
            f("manufacturer_coverage_start_date", "Manufacturer Coverage Start Date", data_type="date"),
            f("manufacturer_coverage_end_date", "Manufacturer Coverage End Date", data_type="date"),
            f("coverage_status", "Coverage Status", validation_rule="ACTIVE, EXCLUDED, SUSPENDED, EXPIRED, PENDING"),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        {"coverage_status": ("ACTIVE", "EXCLUDED", "SUSPENDED", "EXPIRED", "PENDING")},
        ({"agreement_number": "GE-ANNEXURE-2026", "system_id": "SYS-001", "serial_number": "SN-001", "global_order_number": "GO-001", "manufacturer_coverage_start_date": "2026-01-01", "manufacturer_coverage_end_date": "2026-12-31", "coverage_status": "ACTIVE"},),
        import_supported=True,
        export_supported=True,
        export_table="manufacturer_agreement_equipment",
        export_order_by="serial_number",
        template_filename="manufacturer_covered_equipment_import_template.xlsx",
    ),
    DatasetDefinition(
        "manufacturer_eosl_data",
        "Manufacturer EOSL Data",
        "Contract Intelligence / Manufacturer Coverage",
        "Manufacturer end-of-service-life dates used for EOSL review opportunities.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("serial_number", "Serial Number", required=True),
            f("manufacturer", "Manufacturer", required=True),
            f("system_id", "System ID"),
            f("model", "Model"),
            f("eosl_date", "EOSL Date", required=True, data_type="date"),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        example_rows=({"serial_number": "SN-001", "manufacturer": "GE HealthCare", "eosl_date": "2030-12-31"},),
        import_supported=True,
        export_supported=True,
        export_table="manufacturer_agreement_equipment",
        export_order_by="serial_number",
        template_filename="manufacturer_eosl_import_template.xlsx",
    ),
    DatasetDefinition(
        "service_intelligence_service_contracts",
        "Customer Service Contracts",
        "Contract Intelligence / Customer Contracts",
        "Customer service contract headers and coverage terms between our company and the end user.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("contract_number", "Contract Number", required=True, description="Unique contract reference."),
            f("client_name", "Client Name", required=True, description="Contract customer."),
            f("client_code", "Client Code"),
            f("site_name", "Site Name"),
            f("contract_name", "Contract Name"),
            f("contract_type", "Contract Type", required=True, validation_rule="FULL_SERVICE, PREVENTIVE_MAINTENANCE, LABOR_ONLY, PARTS_ONLY, CALIBRATION, EXTENDED_WARRANTY, ON_CALL, OTHER"),
            f("contract_status", "Contract Status", required=True, validation_rule="DRAFT, PENDING, ACTIVE, EXPIRED, SUSPENDED, CANCELLED, RENEWED"),
            f("contract_start_date", "Contract Start Date", required=True, data_type="date", validation_rule="YYYY-MM-DD"),
            f("contract_end_date", "Contract End Date", required=True, data_type="date", validation_rule="YYYY-MM-DD; cannot be before contract_start_date"),
            f("provider", "Provider"),
            f("currency", "Currency"),
            f("contract_value", "Contract Value", data_type="money", sensitive=True),
            f("response_time", "Response Time"),
            f("pm_visits_per_year", "PM Visits Per Year", data_type="number"),
            f("labor_included", "Labor Included", validation_rule="YES/NO, TRUE/FALSE, 1/0"),
            f("parts_included", "Parts Included", validation_rule="YES/NO, TRUE/FALSE, 1/0"),
            f("travel_included", "Travel Included", validation_rule="YES/NO, TRUE/FALSE, 1/0"),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        {
            "contract_type": ("FULL_SERVICE", "PREVENTIVE_MAINTENANCE", "LABOR_ONLY", "PARTS_ONLY", "CALIBRATION", "EXTENDED_WARRANTY", "ON_CALL", "OTHER"),
            "contract_status": ("DRAFT", "PENDING", "ACTIVE", "EXPIRED", "SUSPENDED", "CANCELLED", "RENEWED"),
            "labor_included": ("YES", "NO", "TRUE", "FALSE", "1", "0"),
            "parts_included": ("YES", "NO", "TRUE", "FALSE", "1", "0"),
            "travel_included": ("YES", "NO", "TRUE", "FALSE", "1", "0"),
        },
        ({"contract_number": "CT-001", "client_name": "Hotel Dieu", "contract_type": "FULL_SERVICE", "contract_status": "ACTIVE", "contract_start_date": "2026-01-01", "contract_end_date": "2026-12-31", "labor_included": "YES"},),
        import_supported=True,
        export_supported=True,
        export_table="contracts",
        export_order_by="contract_reference",
        template_filename="service_contracts_import_template.xlsx",
    ),
    DatasetDefinition(
        "service_intelligence_contract_equipment",
        "Customer-Contracted Equipment",
        "Contract Intelligence / Customer Contracts",
        "Equipment rows included in or excluded from customer service contracts.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("contract_number", "Contract Number", required=True),
            f("serial_number", "Serial Number", required=True),
            f("manufacturer", "Manufacturer", description="Recommended secondary match field."),
            f("system_id", "System ID"),
            f("model", "Model", description="Validation only; never used alone for matching."),
            f("client_name", "Client Name"),
            f("site_name", "Site Name"),
            f("coverage_start_date", "Coverage Start Date", data_type="date"),
            f("coverage_end_date", "Coverage End Date", data_type="date"),
            f("coverage_type", "Coverage Type"),
            f("coverage_status", "Coverage Status", validation_rule="ACTIVE, EXCLUDED, SUSPENDED, EXPIRED, PENDING"),
            f("exclusion_reason", "Exclusion Reason"),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        {"coverage_status": ("ACTIVE", "EXCLUDED", "SUSPENDED", "EXPIRED", "PENDING")},
        ({"contract_number": "CT-001", "serial_number": "SN-001", "manufacturer": "GE HealthCare", "coverage_status": "ACTIVE", "coverage_start_date": "2026-01-01", "coverage_end_date": "2026-12-31"},),
        import_supported=True,
        export_supported=False,
        template_filename="contract_equipment_import_template.xlsx",
    ),
    DatasetDefinition(
        "service_intelligence_pm_history",
        "Contract PM Commitments",
        "Contract Intelligence / Customer Contracts",
        "Customer contract PM commitments and completed/scheduled PM events used in opportunity scoring.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("serial_number", "Serial Number", required=True),
            f("manufacturer", "Manufacturer", description="Recommended secondary matching field."),
            f("pm_date", "PM Date", required=True, data_type="date"),
            f("pm_status", "PM Status", required=True, validation_rule="COMPLETED, PARTIALLY_COMPLETED, FAILED, CANCELLED, RESCHEDULED, OVERDUE, UNKNOWN"),
            f("next_pm_date", "Next PM Date", data_type="date"),
            f("service_report_number", "Service Report Number"),
            f("engineer_name", "Engineer Name"),
            f("work_order_number", "Work Order Number"),
            f("contract_number", "Contract Number"),
            f("findings", "Findings"),
            f("recommendations", "Recommendations"),
            f("source", "Source"),
            f("notes", "Notes"),
        ),
        {"pm_status": ("COMPLETED", "PARTIALLY_COMPLETED", "FAILED", "CANCELLED", "RESCHEDULED", "OVERDUE", "UNKNOWN")},
        ({"serial_number": "SN-001", "manufacturer": "GE HealthCare", "pm_date": "2026-06-01", "pm_status": "COMPLETED", "next_pm_date": "2026-12-01"},),
        import_supported=True,
        export_supported=True,
        export_table="pm_tasks",
        export_order_by="scheduled_date",
        template_filename="preventive_maintenance_import_template.xlsx",
    ),
    DatasetDefinition(
        "service_intelligence_service_opportunities",
        "Customer Renewal Opportunities",
        "Contract Intelligence / Customer Contracts",
        "Optional migration template for customer renewal opportunities from another system. Imported values never override calculated equipment classifications.",
        REGISTRY_VERSION,
        REGISTRY_UPDATED_AT,
        (
            f("serial_number", "Serial Number", required=True),
            f("opportunity_type", "Opportunity Type", required=True),
            f("opportunity_status", "Opportunity Status", required=True),
            f("priority", "Priority", validation_rule="HIGH, MEDIUM, LOW"),
            f("score", "Score", data_type="number"),
            f("assigned_to_email", "Assigned To Email", data_type="email"),
            f("detected_date", "Detected Date", data_type="date"),
            f("contacted_date", "Contacted Date", data_type="date"),
            f("contract_number", "Contract Number"),
            f("quotation_reference", "Quotation Reference"),
            f("next_action", "Next Action"),
            f("next_action_date", "Next Action Date", data_type="date"),
            f("lost_reason", "Lost Reason", validation_rule="Required when opportunity_status is LOST"),
            f("notes", "Notes"),
        ),
        {
            "opportunity_type": ("NEW_SERVICE_CONTRACT", "CUSTOMER_CONTRACT_RENEWAL", "PREVENTIVE_MAINTENANCE_CONTRACT", "LABOR_CONTRACT", "FULL_SERVICE_CONTRACT", "CALIBRATION_CONTRACT", "COVERAGE_UPGRADE"),
            "opportunity_status": ("NEW", "REVIEWED", "ASSIGNED", "CONTACTED", "QUOTE_REQUESTED", "QUOTE_SENT", "WON", "LOST", "DISMISSED"),
            "priority": ("HIGH", "MEDIUM", "LOW"),
        },
        ({"serial_number": "SN-001", "opportunity_type": "NEW_SERVICE_CONTRACT", "opportunity_status": "NEW", "priority": "HIGH", "score": 85, "next_action": "Call biomedical engineering"},),
        import_supported=True,
        export_supported=True,
        export_table="service_opportunities",
        export_order_by="detected_at",
        template_filename="service_opportunities_import_template.xlsx",
    ),
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
