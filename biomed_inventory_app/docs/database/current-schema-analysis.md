# Current Schema Analysis

Generated from repository code without modifying application models, routers, migrations, or database files. The machine-readable source is `docs/database/current-schema-inventory.json`.

## Exact ORM Model Count

- SQLAlchemy mapped classes in `Base.registry.mappers`: **21**.
- `TimestampMixin` is not a mapped table; it contributes timestamp columns only.
- Alembic and legacy SQLite create additional non-ORM tables: `roles`, `permissions`, `role_permissions`, `user_roles`, `import_batches`, `import_errors`, `audit_log`, `mdmanser_calendar_events`, `equipment_assets`, `service_reports`, and `service_report_parts`.
- `erp_schemas.py` contains Pydantic schemas, not SQLAlchemy models.

## Current SQLAlchemy Models

### CaseItem -> `case_items`

Source: `app/erp_models.py:231`  
Primary key: `id`  
Relationships declared: none  
Referenced by: procurement_requests.case_item_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| case_id | INTEGER | required |  |  | cases.id ondelete=CASCADE | ix_case_items_case_id |
| item_type | VARCHAR(80) | required |  |  |  |  |
| description | TEXT | nullable |  |  |  |  |
| requested_qty | INTEGER | required | 1 |  |  |  |
| unit_price | NUMERIC(12, 2) | required | 0 |  |  |  |
| status | VARCHAR(50) | required | open |  |  |  |
| procurement_status | VARCHAR(50) | required | not_ordered |  |  |  |
| inventory_item_id | INTEGER | nullable |  |  | inventory_items.id ondelete=SET NULL |  |

### Case -> `cases`

Source: `app/erp_models.py:134`  
Primary key: `id`  
Relationships declared: none  
Referenced by: case_items.case_id (CASCADE), client_activities.case_id (SET NULL), invoices.case_id (SET NULL), pm_tasks.case_id (SET NULL), procurement_requests.case_id (SET NULL), quotations.case_id (SET NULL), service_calls.case_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_cases_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL | ix_cases_department_id |
| equipment_id | INTEGER | nullable |  |  | equipment.id ondelete=SET NULL |  |
| parent_case_reference | VARCHAR(120) | required |  |  |  | ix_cases_parent_case_reference |
| case_type | VARCHAR(80) | required |  |  |  |  |
| title | VARCHAR(255) | required |  |  |  |  |
| description | TEXT | nullable |  |  |  |  |
| status | VARCHAR(50) | required | open |  |  |  |
| priority | VARCHAR(50) | required | normal |  |  |  |
| blocked_reason | TEXT | nullable |  |  |  |  |
| responsible_user_id | INTEGER | nullable |  |  | users.id ondelete=SET NULL |  |
| created_at | DATETIME | required | now() |  |  |  |
| updated_at | DATETIME | required | now() |  |  |  |

### ClientActivity -> `client_activities`

Source: `app/erp_models.py:259`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_client_activities_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL |  |
| case_id | INTEGER | nullable |  |  | cases.id ondelete=SET NULL | ix_client_activities_case_id |
| activity_type | VARCHAR(40) | required |  |  |  |  |
| title | VARCHAR(255) | required |  |  |  |  |
| description | TEXT | nullable |  |  |  |  |
| status | VARCHAR(50) | required | open |  |  |  |
| date | DATE | nullable |  |  |  |  |
| created_by | INTEGER | nullable |  |  | users.id ondelete=SET NULL |  |

### Client -> `clients`

Source: `app/erp_models.py:11`  
Primary key: `id`  
Relationships declared: none  
Referenced by: cases.client_id (CASCADE), client_activities.client_id (CASCADE), contacts.client_id (CASCADE), contracts.client_id (CASCADE), departments.client_id (CASCADE), equipment.client_id (CASCADE), invoices.client_id (CASCADE), pm_tasks.client_id (CASCADE), quotations.client_id (SET NULL), service_calls.client_id (CASCADE), warranties.client_id (CASCADE)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| name | VARCHAR(255) | required |  |  |  | ix_clients_name |
| location | VARCHAR(255) | nullable |  |  |  |  |
| address | TEXT | nullable |  |  |  |  |
| status | VARCHAR(50) | required | active |  |  |  |
| financial_status | VARCHAR(50) | required | good_standing |  |  |  |
| created_at | DATETIME | required | now() |  |  |  |
| updated_at | DATETIME | required | now() |  |  |  |

### Contact -> `contacts`

Source: `app/erp_models.py:35`  
Primary key: `id`  
Relationships declared: none  
Referenced by: quotations.contact_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_contacts_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL | ix_contacts_department_id |
| name | VARCHAR(255) | required |  |  |  |  |
| title | VARCHAR(255) | nullable |  |  |  |  |
| phone | VARCHAR(80) | nullable |  |  |  |  |
| email | VARCHAR(255) | nullable |  |  |  |  |
| notes | TEXT | nullable |  |  |  |  |

### Contract -> `contracts`

Source: `app/erp_models.py:106`  
Primary key: `id`  
Relationships declared: none  
Referenced by: pm_tasks.contract_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_contracts_client_id |
| contract_reference | VARCHAR(120) | nullable |  | yes |  | ix_contracts_contract_reference |
| contract_type | VARCHAR(80) | required | service_contract |  |  |  |
| start_date | DATE | nullable |  |  |  |  |
| end_date | DATE | nullable |  |  |  |  |
| status | VARCHAR(50) | required | active |  |  |  |
| coverage_notes | TEXT | nullable |  |  |  |  |
| pms_per_year | INTEGER | nullable |  |  |  |  |
| pm_pattern | VARCHAR(120) | nullable |  |  |  |  |
| source | VARCHAR(80) | nullable |  |  |  |  |

### Department -> `departments`

Source: `app/erp_models.py:22`  
Primary key: `id`  
Relationships declared: none  
Referenced by: cases.department_id (SET NULL), client_activities.department_id (SET NULL), contacts.department_id (SET NULL), equipment.department_id (SET NULL), pm_tasks.department_id (SET NULL), quotations.department_id (SET NULL), service_calls.department_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_departments_client_id |
| name | VARCHAR(255) | required |  |  |  |  |
| floor_location | VARCHAR(255) | nullable |  |  |  |  |
| contact_name | VARCHAR(255) | nullable |  |  |  |  |
| phone | VARCHAR(80) | nullable |  |  |  |  |
| email | VARCHAR(255) | nullable |  |  |  |  |
| notes | TEXT | nullable |  |  |  |  |

### Engineer -> `engineers`

Source: `app/erp_models.py:59`  
Primary key: `id`  
Relationships declared: none  
Referenced by: pm_tasks.assigned_engineer_id (SET NULL), service_calls.assigned_engineer_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| user_id | INTEGER | nullable |  |  | users.id ondelete=SET NULL |  |
| engineer_name | VARCHAR(255) | required |  | yes |  |  |
| email | VARCHAR(255) | nullable |  |  |  |  |
| phone | VARCHAR(80) | nullable |  |  |  |  |
| active | BOOLEAN | required | True |  |  |  |
| notes | TEXT | nullable |  |  |  |  |
| created_at | DATETIME | required | now() |  |  |  |
| updated_at | DATETIME | required | now() |  |  |  |

### Equipment -> `equipment`

Source: `app/erp_models.py:77`  
Primary key: `id`  
Relationships declared: none  
Referenced by: cases.equipment_id (SET NULL), pm_tasks.equipment_id (SET NULL), service_calls.equipment_id (SET NULL), warranties.equipment_id (CASCADE)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_equipment_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL | ix_equipment_department_id |
| equipment_model_id | INTEGER | nullable |  |  | equipment_models.id ondelete=SET NULL |  |
| name | VARCHAR(255) | required |  |  |  |  |
| manufacturer | VARCHAR(255) | nullable |  |  |  |  |
| model | VARCHAR(255) | nullable |  |  |  |  |
| serial_number | VARCHAR(255) | nullable |  |  |  | ix_equipment_serial_number |
| asset_tag | VARCHAR(255) | nullable |  |  |  |  |
| installation_date | DATE | nullable |  |  |  |  |
| warranty_start_date | DATE | nullable |  |  |  |  |
| warranty_end_date | DATE | nullable |  |  |  |  |
| status | VARCHAR(50) | required | active |  |  |  |
| risk_classification | VARCHAR(80) | nullable |  |  |  |  |
| life_support | BOOLEAN | required | False |  |  |  |
| pm_frequency | VARCHAR(80) | nullable |  |  |  |  |
| last_pm_date | DATE | nullable |  |  |  |  |
| next_pm_date | DATE | nullable |  |  |  |  |
| calibration_required | BOOLEAN | required | False |  |  |  |
| calibration_due_date | DATE | nullable |  |  |  |  |

### EquipmentModel -> `equipment_models`

Source: `app/erp_models.py:70`  
Primary key: `id`  
Relationships declared: none  
Referenced by: equipment.equipment_model_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| manufacturer | VARCHAR(255) | nullable |  |  |  |  |
| model | VARCHAR(255) | nullable |  |  |  |  |

### InventoryItem -> `inventory_items`

Source: `app/erp_models.py:215`  
Primary key: `id`  
Relationships declared: none  
Referenced by: case_items.inventory_item_id (SET NULL), procurement_requests.inventory_item_id (SET NULL), quotation_items.inventory_item_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| pn | VARCHAR(255) | required |  |  |  | ix_inventory_items_pn |
| description | TEXT | nullable |  |  |  |  |
| category | VARCHAR(50) | required | spare_part |  |  |  |
| manufacturer | VARCHAR(255) | nullable |  |  |  |  |
| minimum_qty | INTEGER | required | 0 |  |  |  |
| physical_qty | INTEGER | required | 0 |  |  |  |
| reserved_qty | INTEGER | required | 0 |  |  |  |
| available_qty | INTEGER | required | 0 |  |  |  |
| location | VARCHAR(255) | nullable |  |  |  |  |
| status | VARCHAR(50) | required | active |  |  |  |

### Invoice -> `invoices`

Source: `app/erp_models.py:274`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_invoices_client_id |
| case_id | INTEGER | nullable |  |  | cases.id ondelete=SET NULL | ix_invoices_case_id |
| parent_case_reference | VARCHAR(120) | nullable |  |  |  | ix_invoices_parent_case_reference |
| invoice_number | VARCHAR(120) | required |  |  |  |  |
| status | VARCHAR(50) | required | draft |  |  |  |
| total_amount | NUMERIC(12, 2) | required | 0 |  |  |  |
| due_date | DATE | nullable |  |  |  |  |
| paid_date | DATE | nullable |  |  |  |  |

### PMTask -> `pm_tasks`

Source: `app/erp_models.py:186`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_pm_tasks_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL |  |
| equipment_id | INTEGER | nullable |  |  | equipment.id ondelete=SET NULL | ix_pm_tasks_equipment_id |
| contract_id | INTEGER | nullable |  |  | contracts.id ondelete=SET NULL | ix_pm_tasks_contract_id |
| case_id | INTEGER | nullable |  |  | cases.id ondelete=SET NULL |  |
| scheduled_date | DATE | nullable |  |  |  |  |
| completed_date | DATE | nullable |  |  |  |  |
| status | VARCHAR(50) | required | scheduled |  |  |  |
| assigned_engineer_id | INTEGER | nullable |  |  | engineers.id ondelete=SET NULL |  |
| pm_label | VARCHAR(80) | nullable |  |  |  |  |
| communication_stage | VARCHAR(120) | nullable |  |  |  |  |
| reminder_1_sent | BOOLEAN | required | False |  |  |  |
| reminder_2_sent | BOOLEAN | required | False |  |  |  |
| final_reminder_sent | BOOLEAN | required | False |  |  |  |
| engineer_alert_sent | BOOLEAN | required | False |  |  |  |
| visit_confirmed_date | DATE | nullable |  |  |  |  |
| overdue | BOOLEAN | required | False |  |  |  |
| source | VARCHAR(80) | nullable |  |  |  |  |
| source_row_hash | VARCHAR(64) | nullable |  |  |  |  |

### ProcurementRequest -> `procurement_requests`

Source: `app/erp_models.py:245`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| case_id | INTEGER | nullable |  |  | cases.id ondelete=SET NULL | ix_procurement_requests_case_id |
| case_item_id | INTEGER | nullable |  |  | case_items.id ondelete=SET NULL | ix_procurement_requests_case_item_id |
| inventory_item_id | INTEGER | nullable |  |  | inventory_items.id ondelete=SET NULL |  |
| requested_qty | INTEGER | required | 0 |  |  |  |
| shortage_qty | INTEGER | required | 0 |  |  |  |
| procurement_status | VARCHAR(50) | required | not_ordered |  |  |  |
| supplier | VARCHAR(255) | nullable |  |  |  |  |
| expected_date | DATE | nullable |  |  |  |  |

### QuotationAttachment -> `quotation_attachments`

Source: `app/erp_models.py:348`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| quotation_id | INTEGER | required |  |  | quotations.id ondelete=CASCADE | ix_quotation_attachments_quotation_id |
| filename | VARCHAR(255) | required |  |  |  |  |
| content_type | VARCHAR(120) | nullable |  |  |  |  |
| storage_path | VARCHAR(500) | nullable |  |  |  |  |
| extracted_text | TEXT | nullable |  |  |  |  |
| created_at | DATETIME | required | now() |  |  |  |

### QuotationItem -> `quotation_items`

Source: `app/erp_models.py:319`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| quotation_id | INTEGER | required |  |  | quotations.id ondelete=CASCADE | ix_quotation_items_quotation_id |
| inventory_item_id | INTEGER | nullable |  |  | inventory_items.id ondelete=SET NULL | ix_quotation_items_inventory_item_id |
| item_code | VARCHAR(255) | nullable |  |  |  |  |
| manufacturer_part_number | VARCHAR(255) | nullable |  |  |  |  |
| description | TEXT | required |  |  |  |  |
| ai_normalized_description | TEXT | nullable |  |  |  |  |
| quantity | NUMERIC(12, 2) | required | 1 |  |  |  |
| unit_price | NUMERIC(12, 2) | required | 0 |  |  |  |
| discount_percent | NUMERIC(5, 2) | required | 0 |  |  |  |
| line_total | NUMERIC(12, 2) | required | 0 |  |  |  |
| warranty | VARCHAR(255) | nullable |  |  |  |  |
| delivery_time | VARCHAR(255) | nullable |  |  |  |  |
| ai_match_confidence | NUMERIC(5, 3) | nullable |  |  |  |  |
| ai_validation_status | VARCHAR(40) | required | missing_info |  |  |  |
| ai_validation_notes | TEXT | nullable |  |  |  |  |
| product_id | INTEGER | nullable |  |  |  |  |
| ref | VARCHAR(255) | nullable |  |  |  |  |
| qty | INTEGER | nullable |  |  |  |  |
| total_price | NUMERIC(12, 2) | required | 0 |  |  |  |
| notes | TEXT | nullable |  |  |  |  |

### QuotationTemplate -> `quotation_templates`

Source: `app/erp_models.py:360`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| name | VARCHAR(255) | required |  |  |  |  |
| currency | VARCHAR(12) | required | USD |  |  |  |
| payment_terms | TEXT | nullable |  |  |  |  |
| delivery_terms | TEXT | nullable |  |  |  |  |
| warranty_terms | TEXT | nullable |  |  |  |  |
| notes | TEXT | nullable |  |  |  |  |
| is_default | BOOLEAN | required | False |  |  | ix_quotation_templates_default |
| created_at | DATETIME | required | now() |  |  |  |
| updated_at | DATETIME | required | now() |  |  |  |

### Quotation -> `quotations`

Source: `app/erp_models.py:288`  
Primary key: `id`  
Relationships declared: none  
Referenced by: quotation_attachments.quotation_id (CASCADE), quotation_items.quotation_id (CASCADE)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| quotation_number | VARCHAR(120) | nullable |  |  |  | ix_quotations_number |
| quotation_no | VARCHAR(120) | nullable |  |  |  |  |
| client_id | INTEGER | nullable |  |  | clients.id ondelete=SET NULL | ix_quotations_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL |  |
| contact_id | INTEGER | nullable |  |  | contacts.id ondelete=SET NULL |  |
| case_id | INTEGER | nullable |  |  | cases.id ondelete=SET NULL |  |
| status | VARCHAR(50) | required | draft |  |  | ix_quotations_status |
| quotation_date | DATE | nullable |  |  |  |  |
| quote_date | DATE | nullable |  |  |  |  |
| valid_until | DATE | nullable |  |  |  |  |
| currency | VARCHAR(12) | required | USD |  |  |  |
| subtotal | NUMERIC(12, 2) | required | 0 |  |  |  |
| discount_amount | NUMERIC(12, 2) | required | 0 |  |  |  |
| vat_rate | NUMERIC(5, 2) | required | 0 |  |  |  |
| vat_amount | NUMERIC(12, 2) | required | 0 |  |  |  |
| total_amount | NUMERIC(12, 2) | required | 0 |  |  |  |
| amount | NUMERIC(12, 2) | required | 0 |  |  |  |
| payment_terms | TEXT | nullable |  |  |  |  |
| delivery_terms | TEXT | nullable |  |  |  |  |
| warranty_terms | TEXT | nullable |  |  |  |  |
| notes | TEXT | nullable |  |  |  |  |
| created_at | DATETIME | required | now() |  |  |  |
| updated_at | DATETIME | required | now() |  |  |  |

### ServiceCall -> `service_calls`

Source: `app/erp_models.py:156`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_service_calls_client_id |
| department_id | INTEGER | nullable |  |  | departments.id ondelete=SET NULL |  |
| equipment_id | INTEGER | nullable |  |  | equipment.id ondelete=SET NULL |  |
| case_id | INTEGER | nullable |  |  | cases.id ondelete=SET NULL | ix_service_calls_case_id |
| call_type | VARCHAR(120) | required | service |  |  |  |
| call_type_2 | VARCHAR(120) | nullable |  |  |  |  |
| priority | VARCHAR(50) | required | normal |  |  |  |
| status | VARCHAR(50) | required | open |  |  |  |
| blocked_reason | TEXT | nullable |  |  |  |  |
| assigned_engineer_id | INTEGER | nullable |  |  | engineers.id ondelete=SET NULL |  |
| call_reason | TEXT | nullable |  |  |  |  |
| call_by | VARCHAR(255) | nullable |  |  |  |  |
| received_by | VARCHAR(255) | nullable |  |  |  |  |
| request_date | DATE | nullable |  |  |  |  |
| request_time | VARCHAR(40) | nullable |  |  |  |  |
| visit_date | DATE | nullable |  |  |  |  |
| visit_time | VARCHAR(40) | nullable |  |  |  |  |
| completed_date | DATE | nullable |  |  |  |  |
| completed_time | VARCHAR(40) | nullable |  |  |  |  |
| source | VARCHAR(80) | nullable |  |  |  |  |
| source_row_hash | VARCHAR(64) | nullable |  |  |  |  |

### User -> `users`

Source: `app/erp_models.py:48`  
Primary key: `id`  
Relationships declared: none  
Referenced by: cases.responsible_user_id (SET NULL), client_activities.created_by (SET NULL), engineers.user_id (SET NULL)

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| username | VARCHAR(120) | required |  | yes |  |  |
| full_name | VARCHAR(255) | nullable |  |  |  |  |
| role | VARCHAR(80) | nullable |  |  |  |  |
| email | VARCHAR(255) | nullable |  |  |  |  |
| phone | VARCHAR(80) | nullable |  |  |  |  |
| active | BOOLEAN | required | True |  |  |  |
| created_at | DATETIME | required | now() |  |  |  |
| updated_at | DATETIME | required | now() |  |  |  |

### Warranty -> `warranties`

Source: `app/erp_models.py:122`  
Primary key: `id`  
Relationships declared: none  
Referenced by: none

| column | type | required | default | unique | fk | index |
| --- | --- | --- | --- | --- | --- | --- |
| id | INTEGER | required |  |  |  |  |
| equipment_id | INTEGER | required |  |  | equipment.id ondelete=CASCADE | ix_warranties_equipment_id |
| client_id | INTEGER | required |  |  | clients.id ondelete=CASCADE | ix_warranties_client_id |
| start_date | DATE | nullable |  |  |  |  |
| end_date | DATE | nullable |  |  |  |  |
| status | VARCHAR(50) | required | active |  |  |  |
| coverage_notes | TEXT | nullable |  |  |  |  |

## Foreign Key Matrix
| source_table | source_column | target_table | target_column | nullable | ondelete | indexed | expected_cardinality | safe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_items | case_id | cases | id | False | CASCADE | True | many-to-one | RISK |
| case_items | inventory_item_id | inventory_items | id | True | SET NULL | False | many-to-one | generally ok |
| cases | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| cases | department_id | departments | id | True | SET NULL | True | many-to-one | generally ok |
| cases | equipment_id | equipment | id | True | SET NULL | False | many-to-one | review |
| cases | responsible_user_id | users | id | True | SET NULL | False | many-to-one | generally ok |
| client_activities | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| client_activities | department_id | departments | id | True | SET NULL | False | many-to-one | generally ok |
| client_activities | case_id | cases | id | True | SET NULL | True | many-to-one | review |
| client_activities | created_by | users | id | True | SET NULL | False | many-to-one | generally ok |
| contacts | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| contacts | department_id | departments | id | True | SET NULL | True | many-to-one | generally ok |
| contracts | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| departments | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| engineers | user_id | users | id | True | SET NULL | False | many-to-one | generally ok |
| equipment | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| equipment | department_id | departments | id | True | SET NULL | True | many-to-one | generally ok |
| equipment | equipment_model_id | equipment_models | id | True | SET NULL | False | many-to-one | generally ok |
| invoices | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| invoices | case_id | cases | id | True | SET NULL | True | many-to-one | review |
| pm_tasks | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| pm_tasks | department_id | departments | id | True | SET NULL | False | many-to-one | generally ok |
| pm_tasks | equipment_id | equipment | id | True | SET NULL | True | many-to-one | review |
| pm_tasks | contract_id | contracts | id | True | SET NULL | True | many-to-one | generally ok |
| pm_tasks | case_id | cases | id | True | SET NULL | False | many-to-one | review |
| pm_tasks | assigned_engineer_id | engineers | id | True | SET NULL | False | many-to-one | generally ok |
| procurement_requests | case_id | cases | id | True | SET NULL | True | many-to-one | review |
| procurement_requests | case_item_id | case_items | id | True | SET NULL | True | many-to-one | generally ok |
| procurement_requests | inventory_item_id | inventory_items | id | True | SET NULL | False | many-to-one | generally ok |
| quotation_attachments | quotation_id | quotations | id | False | CASCADE | True | many-to-one | generally ok |
| quotation_items | quotation_id | quotations | id | False | CASCADE | True | many-to-one | generally ok |
| quotation_items | inventory_item_id | inventory_items | id | True | SET NULL | True | many-to-one | generally ok |
| quotations | client_id | clients | id | True | SET NULL | True | many-to-one | review |
| quotations | department_id | departments | id | True | SET NULL | False | many-to-one | generally ok |
| quotations | contact_id | contacts | id | True | SET NULL | False | many-to-one | generally ok |
| quotations | case_id | cases | id | True | SET NULL | False | many-to-one | review |
| service_calls | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |
| service_calls | department_id | departments | id | True | SET NULL | False | many-to-one | generally ok |
| service_calls | equipment_id | equipment | id | True | SET NULL | False | many-to-one | review |
| service_calls | case_id | cases | id | True | SET NULL | True | many-to-one | review |
| service_calls | assigned_engineer_id | engineers | id | True | SET NULL | False | many-to-one | generally ok |
| warranties | equipment_id | equipment | id | False | CASCADE | True | many-to-one | RISK |
| warranties | client_id | clients | id | False | CASCADE | True | many-to-one | RISK |

## Duplicated And Denormalized Fields
| field | source | owner | risk | migration | compatibility |
| --- | --- | --- | --- | --- | --- |
| equipment.manufacturer, equipment.model, equipment.equipment_model_id | `Equipment` has manufacturer/model strings and FK to `equipment_models` | `equipment_models` | manufacturer/model can diverge from FK model record | backfill equipment_models from distinct manufacturer/model then set equipment_model_id | legacy screens/imports may read/write strings |
| inventory_items.physical_qty, reserved_qty, available_qty | `InventoryItem` stores balances directly | inventory_transactions ledger plus stock_balances | stock can change without auditable movement history | create inventory_transactions from initial balances and maintain stock_balances | warehouse UI expects direct quantity columns |
| quotations.quotation_number and quotation_no | `Quotation` and `quotation_api` use both | quotation_number | identifiers can disagree | coalesce into quotation_number; keep quotation_no read alias | old payloads use quotation_no |
| quotations.subtotal,total_amount,amount and quotation_items.line_total,total_price,qty/quantity | `Quotation`/`QuotationItem` contain legacy and current totals | item quantity/unit_price/discount_percent plus calculated totals | stored totals can disagree | recompute totals; deprecate amount,total_price,qty | exports/UI may consume old fields |
| service_reports equipment_model/equipment_serial_number/institution plus equipment_asset_id/equipment_id | service report import tables | equipment_assets/equipment/equipment_models/clients | snapshot data doubles as master data | retain snapshots, resolve FK links | imports rely on raw text |
| users.role plus roles/user_roles | `User.role` and admin foundation RBAC tables | roles/user_roles | authorization can diverge | backfill user_roles from users.role | middleware reads session role |

## Status, Type, Category, Priority, Role, State Columns
| table | column | type | default | validation | recommended |
| --- | --- | --- | --- | --- | --- |
| case_items | item_type | VARCHAR(80) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| case_items | status | VARCHAR(50) | open | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| case_items | procurement_status | VARCHAR(50) | not_ordered | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| cases | case_type | VARCHAR(80) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| cases | status | VARCHAR(50) | open | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| cases | priority | VARCHAR(50) | normal | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| client_activities | activity_type | VARCHAR(40) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| client_activities | status | VARCHAR(50) | open | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| clients | status | VARCHAR(50) | active | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| clients | financial_status | VARCHAR(50) | good_standing | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| contracts | contract_type | VARCHAR(80) | service_contract | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| contracts | status | VARCHAR(50) | active | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| equipment | status | VARCHAR(50) | active | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| equipment | risk_classification | VARCHAR(80) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| inventory_items | category | VARCHAR(50) | spare_part | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| inventory_items | status | VARCHAR(50) | active | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| invoices | status | VARCHAR(50) | draft | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| pm_tasks | status | VARCHAR(50) | scheduled | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| procurement_requests | procurement_status | VARCHAR(50) | not_ordered | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| quotation_attachments | content_type | VARCHAR(120) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| quotation_items | ai_validation_status | VARCHAR(40) | missing_info | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| quotations | status | VARCHAR(50) | draft | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| service_calls | call_type | VARCHAR(120) | service | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| service_calls | call_type_2 | VARCHAR(120) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| service_calls | priority | VARCHAR(50) | normal | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| service_calls | status | VARCHAR(50) | open | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| users | role | VARCHAR(80) |  | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |
| warranties | status | VARCHAR(50) | active | free text String; no Enum/Check/lookup in ORM | workflow history for transactional statuses; lookup/check for simple categories; roles via roles/user_roles |

## Database Configuration Evidence

- `app/database.py` loads `DATABASE_URL` from environment or defaults to `sqlite:///app/data/inventory.db`; engine uses `pool_pre_ping=True` and SQLite `check_same_thread=False`.
- `app/legacy_main.py`, `app/quotation_api.py`, and `app/aftermarket_service_reports.py` use raw `sqlite3` and `DB_PATH`, defaulting to `app/data/inventory.db`.
- `requirements.txt` includes `psycopg2-binary`, so PostgreSQL driver support exists.
- `alembic.ini` defaults to `sqlite:///app/data/inventory.db`; `alembic/env.py` overrides from `DATABASE_URL` when present.
- `docker-compose.yml`: missing in this checkout; no compose volume persistence evidence.
- Live SQLite file exists: `True` at `/Users/naghamkheir/Repos/IRM/biomed_inventory_app/app/data/inventory.db`; it is inside the repository tree.
- SQLite foreign-key enforcement on current connection: `0`. No repo code found enabling `PRAGMA foreign_keys=ON` globally.
- SQLAlchemy sessions from `get_db()` and `session_scope()` close in `finally`; tests set `DB_PATH` temp files for legacy/sqlite paths but not consistently SQLAlchemy `DATABASE_URL`.

## Alembic History
| file | revision | down_revision | creates | add_columns | potentially_destructive | downgrade_pass |
| --- | --- | --- | --- | --- | --- | --- |
| alembic/versions/20260524_erp_mdmanser_foundation.py | 20260524_erp_mdmanser | None | [] | [] | False | True |
| alembic/versions/20260524_mdmanser_calendar_events.py | 20260524_mdmanser_calendar_events | "20260524_erp_mdmanser" | ['mdmanser_calendar_events'] | [] | False | True |
| alembic/versions/20260703_quotation_generator.py | 20260703_quotation_generator | "20260524_mdmanser_calendar_events" | ['quotations', 'quotation_items', 'quotation_equipment_groups', 'quotation_attachments', 'quotation_templates'] | [] | False | True |
| alembic/versions/20260709_admin_foundation.py | 20260709_admin_foundation | "20260703_quotation_generator" | ['roles', 'permissions', 'role_permissions', 'user_roles', 'import_batches', 'import_errors', 'audit_log'] | [] | False | True |
| alembic/versions/20260709_aftermarket_service_reports.py | 20260709_aftermarket_service_reports | "20260709_admin_foundation" | ['equipment_assets', 'service_reports', 'service_report_parts'] | [] | False | True |

## Recreate Reliability
`alembic upgrade head` is additive but incomplete as the sole source of truth: the foundation migration clones model columns with relaxed nullability and does not recreate full FK/unique semantics, while startup functions also create/alter tables imperatively.

## Final Report Summary

### Files inspected
`app/erp_models.py`, `app/erp_schemas.py`, `app/database.py`, `app/main.py`, `app/legacy_main.py`, `app/admin_api.py`, `app/quotation_api.py`, `app/erp_api.py`, `app/aftermarket_service_reports.py`, `app/routers/*.py`, `alembic/env.py`, `alembic/versions/*.py`, `scripts/*.py`, `tests/*.py`, `firebase.json`, `requirements.txt`, `alembic.ini`, and repository root for `docker-compose.yml`.

### Findings supported directly by code
- The exact SQLAlchemy mapped model count is 21.
- `TimestampMixin` is not a table model.
- The live SQLite database contains additional legacy/migration-created tables beyond ORM models.
- Business-critical tables currently use `CASCADE` from `clients` into cases, service calls, PM tasks, contracts, invoices, warranties, contacts, departments, equipment, and client activities.
- Several modules bypass SQLAlchemy and use raw SQLite against `DB_PATH`.
- PostgreSQL driver/config support exists, but SQLite is the default active configuration.
- Alembic history is additive and does not fully express the live model constraints.

### Assumptions
- The checked-out repository state is the analysis target.
- The local `app/data/inventory.db` file represents the current active SQLite development database.
- Target architecture is intended for PostgreSQL-compatible production use while preserving existing SQLite data during migration.

### Unresolved questions
- Which deployed runtime should become the production database source of truth during migration?
- Should client deletion ever be allowed, or should clients be permanently soft-deleted?
- Which current free-text statuses are already used in historical data outside the visible code paths?
- Are service reports legally/audit-required immutable documents, or may corrected versions replace imported rows?

### Highest-risk database issues
- Cascading deletes from `clients`, `cases`, and `equipment` can remove operational history.
- SQLite foreign-key enforcement is not enabled globally in code.
- Raw SQLite and SQLAlchemy use separate configuration variables (`DB_PATH` vs `DATABASE_URL`).
- Inventory balances are stored as current quantities without a complete ledger source of truth.
- Quotation and equipment fields contain duplicated canonical/legacy representations.

### Recommended first implementation milestone
Create additive master-data normalization for manufacturers, equipment categories, and equipment models; backfill `equipment.equipment_model_id`; keep existing string fields for compatibility; add validation reports before enforcing constraints.
