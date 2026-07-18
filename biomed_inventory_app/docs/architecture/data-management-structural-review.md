# Data Management Structural Review

Date: 2026-07-17
Scope: architecture review for the database-foundation checkpoint.

## Guardrail

No additional Data Management features should be added until this sequence is complete:

```text
Architecture first
-> department design
-> model design
-> dataset specifications
-> templates
-> import execution
```

`app/data/inventory.db` is replaceable local runtime state and is ignored by Git. The committed schema authority is the SQLAlchemy model set plus Alembic migrations.

## Current UI Architecture

- Active entrypoint: `app.main:app`.
- `app/main.py` is a composition layer that mounts static assets, auth middleware, legacy routers, modular routers, master-data APIs, import APIs, and Data Management APIs.
- Pages are mostly static HTML under `app/static`, with shared shell/navigation in `app/static/app_layout.js` and styling in `app/static/theme.css`.
- Administration pages are currently rendered by static HTML routes:
  - `/administration` and `/administration/{section:path}` -> `module_page.html`
  - `/administration/data-management` -> `data_management.html`
  - `/admin/database-map` -> `database_map.html`
  - `/admin/imports` -> `imports.html`
  - `/admin/query` -> `query.html`
- The app has mixed data access:
  - Legacy direct SQLite through `legacy_main.db()`.
  - Module-specific direct SQLite in `quotation_api.py`, `admin_api.py`, and `aftermarket_service_reports.py`.
  - SQLAlchemy session/services through `app.database`, `app.services.*`, and foundation models.

## Current-State Call Graph

```text
Browser
  -> app/static/app_layout.js shell
  -> static page HTML
  -> fetch(...)
  -> app.main auth_middleware
  -> route group
       legacy_main route
         -> legacy_main.db()
         -> SQLite tables / Excel reports
       admin_api route
         -> legacy_main.db() or report helpers
         -> admin/import tables / audit_log
       master_data_api route
         -> SQLAlchemy service
         -> foundation master-data tables
       imports_api route
         -> SQLAlchemy ImportBatchService
         -> import_batches
       data_management_api route
         -> template_registry
         -> SQLAlchemy ImportBatch/ImportRow/DataValidationError/AuditEvent
         -> optional export read SQL
       quotation_api route
         -> direct sqlite3 connection
         -> quotation tables
       aftermarket_service_reports route
         -> legacy_main.db()
         -> service report / equipment asset tables
```

## Target-State Call Graph

```text
Department screen
  -> department router
  -> department service
  -> owned model aggregate
  -> database tables

Data Management Center
  -> dataset registry
  -> dataset validator
  -> import staging service
       -> import_batches
       -> import_rows
       -> data_validation_errors
  -> reviewer approval workflow
  -> department-owned execution service
       -> normalized tables through domain services only
  -> reconciliation/audit service
       -> audit_events
       -> status_history where applicable
```

Target rule: Data Management should never write directly to operational tables. It should hand validated records to the owning department service after dataset grain, unique key, validation, and rollback behavior are approved.

## Department Ownership Matrix

| Department | Current screens | Current API paths | Major models/tables | Current DB access | Target owner |
|---|---|---|---|---|---|
| CRM / Clients | `crm.html`, `crm_client.html`, `core_list.html` | `/api/clients`, `/api/crm/*`, `/api/erp/clients` | `clients`, `departments`, `contacts`, `client_sites`, `locations` | legacy SQLite + SQLAlchemy master-data | CRM service owns client, contact, site, department identity |
| Administration | `module_page.html`, `data_management.html`, `database_map.html`, `imports.html`, `query.html` | `/api/admin/*`, `/api/data-management/*`, `/api/imports/*`, `/api/master-data/*` | `roles`, `permissions`, `import_batches`, `import_rows`, `data_validation_errors`, `audit_events` | mixed legacy SQLite + SQLAlchemy | Admin/data governance owns staging, security, audit |
| Master Data | Data Management + future Master Data UI | `/api/master-data/*` | `manufacturers`, `manufacturer_aliases`, `suppliers`, `equipment_categories`, `equipment_category_aliases` | SQLAlchemy services | Master-data service owns canonical references |
| Equipment Registry | `equipment_database.html`, `pm.html`, PM React bundle | `/api/equipment`, `/api/pm-assets`, `/api/biomedical/*` | `equipment`, `equipment_models`, `equipment_assets`, PM asset tables | legacy SQLite + SQLAlchemy model definitions | Biomedical equipment service owns installed assets and model catalog |
| Warehouse | `warehouse.html` | `/api/items`, `/api/inventory/*`, `/api/transactions/*`, `/api/export` | `inventory_items`, legacy `inventory`, stock transactions | legacy SQLite | Warehouse service owns item master, stock balances, stock movements |
| Sales / Commercial | `sales.html`, `quotations.html` | `/api/customer-requests`, `/quotations/*`, `/api/commercial/*` | `quotations`, `quotation_items`, customer request/order tables | direct SQLite + legacy SQLite | Sales service owns offers, quotations, customer requests |
| Procurement | `procurement.html` | `/api/purchase-orders/*`, `/api/procurement/*` | `procurement_requests`, `purchase_orders`, `purchase_order_items` | legacy SQLite | Procurement service owns supplier purchasing and PO lifecycle |
| After-Sales / Service | `after_sales.html`, `pm.html`, PM bundle | `/api/service-calls`, `/api/aftermarket/*`, `/api/after-sales/*` | `service_calls`, `cases`, service reports, service parts | legacy SQLite + module SQLite helper | Service service owns calls, visits, service history |
| Preventive Maintenance | PM bundle | `/api/pm-tasks`, `/api/pm-history`, `/api/pm-calendar`, `/api/pm-reports` | `pm_tasks`, PM history/assets tables | legacy SQLite | PM service owns PM plans, tasks, completions |
| Finance | `module_page.html` | `/api/client-orders`, invoice/report endpoints | `invoices`, client orders, balances | legacy SQLite | Finance service owns invoices and financial exports |

## Major Model Grain And Keys

| Model/table | Grain | Candidate unique matching key | Owner | Notes |
|---|---|---|---|---|
| `clients` | One customer organization/hospital | `client_code` target; currently normalized `name` | CRM | Needs stable code before high-volume imports |
| `departments` | One department under one client | `client_id + department_code` target; currently `client + department_name` | CRM | Do not merge with sites/locations |
| `contacts` | One person/contact method under client/department | email when present; else `client_id + name` | CRM | Role history may need separate model later |
| `client_sites` | One physical site for a client | `client_id + site_code` | CRM / Master Data | Keep separate from department |
| `locations` | One nested physical location | `site_id + location_code` | CRM / Equipment | Needed for installed equipment placement |
| `manufacturers` | One canonical manufacturer | `code`; fallback `normalized_name` | Master Data | Alias resolution must remain review-gated |
| `manufacturer_aliases` | One verified source alias | `normalized_alias` | Master Data | Do not merge automatically |
| `suppliers` | One supplier organization | `supplier_code` | Master Data / Procurement | Separate from manufacturer |
| `equipment_categories` | One taxonomy node | `code`; parent/name uniqueness | Master Data | Category import should not consume stock labels blindly |
| `equipment_category_aliases` | One verified category alias | `normalized_alias` | Master Data | Review-gated |
| `equipment_models` | One manufacturer/model/catalog record | `manufacturer_id + normalized model`; interim raw `manufacturer + model` | Equipment Registry | Separate from installed assets |
| `equipment` | One installed asset | `serial_number` target; optionally `client_id + asset_number` | Equipment Registry | Asset grain, not model grain |
| `inventory_items` | One warehouse item/part master | `pn` | Warehouse | Not stock balance or transaction |
| stock balances | One item/location balance | `item_id + location` | Warehouse | Should be split from `inventory_items` |
| stock transactions | One stock movement event | generated transaction id | Warehouse | Should be split from item master/balance imports |
| `cases` | One workflow/case envelope | `case_no` / external reference | Cross-department workflow | Needs ownership by case type |
| `service_calls` | One service request/call | `client_id + call_no` or source reference | After-Sales | Not the same as visit/service report |
| service visits/reports | One visit/report occurrence | `sr_number` or source report id | After-Sales | Separate from service call header |
| PM plans | One recurring maintenance plan | `equipment_id + plan_code` | PM | Not currently cleanly separated |
| `pm_tasks` | One scheduled/assigned PM task occurrence | generated task id; `asset_id + due_date + task_name` candidate | PM | Separate from plans and history |
| `contracts` | One contract header | `client_id + contract_number` | Finance / After-Sales | Contract lines/coverage should be separate |
| `quotations` | One quotation header | `quotation_number` | Sales | Commercial offer only |
| `quotation_items` | One quotation line | `quotation_id + line number` target | Sales | Separate from quotation header |

## Data Management Dataset Classification

| Dataset | Current status | Classification | Grain/key decision | Required change before import execution |
|---|---|---|---|---|
| `clients` | Enabled import/export | Extend | One client; key should be `client_code`, fallback normalized name | Add stable code handling and duplicate policy |
| `departments` | Enabled import/export | Extend | One department under client; key `client_code + department_code/name` | Clarify site vs department and add client-code resolver |
| `contacts` | Enabled import/export | Rename | Current fields use `contact_name`; table uses `name` | Rename dataset fields to match target API contract or map explicitly |
| `manufacturers` | Enabled import/export | Keep | One canonical manufacturer; key `code`/`normalized_name` | Keep alias matching review-only |
| `suppliers` | Enabled import/export | Keep | One supplier; key `supplier_code` | Decide supplier vs manufacturer overlap rules |
| `equipment_categories` | Enabled import/export | Keep | One taxonomy node; key `code` | Keep parent-code validation and alias review |
| `equipment_models` | Enabled import/export | Extend | One model catalog row; key `manufacturer + model` | Require canonical manufacturer/category resolution before execution |
| `equipment` | Enabled import/export | Split | Current dataset mixes installed asset, model, manufacturer, category, warranty, and location | Split into equipment assets, model links, warranty/coverage, and location assignment |
| `inventory_items` | Enabled import/export | Rename | One item master; key `pn` | Rename to `warehouse_item_master`; split stock balances/transactions |
| `service_cases` | Disabled | Merge or Split | Case envelope; key `case_no` | Decide relationship to `cases`, `service_calls`, and visits |
| `service_calls` | Import enabled only | Split | Service call/request; key `client + call_no` | Separate call header from visit/service report and parts usage |
| `preventive_maintenance` | Disabled | Split | Currently ambiguous plan/task/history | Split PM plans, PM tasks, PM completions/history |
| `contracts` | Disabled | Extend | Contract header; key `client + contract_number` | Define coverage lines, equipment links, financial fields |
| `quotations` | Disabled | Keep | Quotation header; key `quotation_number` | Keep separate from items; no stock/procurement side effects |
| `quotation_items` | Disabled | Keep | Quotation line; key `quotation + line` | Needs line numbering/grouping and price permission rules |

## Migration Review: Import Batch Timestamps

Priority finding:

- `ImportBatch` uses `TimestampMixin`, so the Alembic-managed schema must provide both `created_at` and `updated_at`.
- Earlier local checkpoint work added a branch-local repair migration for these columns. Because this branch is unreleased and the development database is disposable, the repair migration was removed and the columns were folded into `20260716_database_foundation.py`.
- The Alembic head is now `20260716_equipment_model_master_fks`; an empty database should receive import-batch timestamp columns directly during the foundation migration.

Remaining review items:

- PostgreSQL: `batch_alter_table` plus `server_default=sa.func.now()` should compile, but should still be tested in the Postgres deployment path before merge.
- SQLite: the local runtime database can be rebuilt from migrations; it is not part of the checkpoint commit.

## Known Legacy Test Failures

Latest verification during checkpoint prep:

- `python3 -m compileall app tests`: passed.
- `python3 -m unittest tests.test_database_foundation -v`: passed, 19 tests.
- `python3 -m unittest tests.test_master_data_backfill -v`: passed, 5 tests.
- `python3 -m unittest tests.test_data_management_center -v`: passed, 8 tests.
- `python3 -m unittest tests.test_aftermarket_service_reports tests.test_quotation_generator -v`: passed, 9 tests.
- `python3 -m unittest discover -s tests -v`: 44 passed, 2 failures, 2 errors.
- `test_pending_offer_import_department_progress_search_and_bulk_edit`: still fails in full discovery with `external_reference` as `None`.
- `test_procurement_assigns_unassigned_client_order_items_to_po`: still fails with `HTTPException 400: Generate and approve a quotation before converting to customer order`.
- `test_procurement_tracks_duplicate_refs_as_separate_rows`: same quotation approval precondition failure.
- `test_service_hospital_follow_up_tracks_service_department_buckets`: still expects score `4` but runtime returns `5`.

Assessment:

- The remaining failures execute legacy sales/procurement/service workflow paths in `legacy_main.py`.
- They do not call `/api/data-management/*`, the template registry, or the new import staging router.
- They predate or are behaviorally independent from the new Data Management registry and UI work.
- ResourceWarnings about unclosed legacy SQLite connections are still emitted by some legacy tests.

## UI Review Notes

Browser status:

- In-app browser backend was unavailable in this session (`agent.browsers.list()` returned `[]`), so a true visual/manual browser inspection could not be completed from Codex.

HTTP/UI smoke performed against `http://127.0.0.1:8000`:

- `/login`: 200.
- Login with local default credentials: 200.
- `/administration`: 200.
- `/administration/data-management`: 200.
- `/api/data-management/datasets`: 200, 15 registered datasets.
- `/api/data-management/summary`: 200.
- `/api/data-management/templates/equipment/download`: 200 Excel response.
- `/api/data-management/exports/preview`: 200.
- Upload preview smoke staged one client CSV successfully, then the staged smoke batch was removed from `import_batches`, `import_rows`, `data_validation_errors`, and `audit_events`.

Functional review findings to verify visually when browser access is available:

- Navigation: confirm Administration tab state highlights correctly on `/administration/data-management`.
- Empty states: confirm history/validation tables show clear empty rows after smoke cleanup.
- Disabled datasets: confirm disabled options are visible as `Coming soon` and cannot be selected.
- Template downloads: confirm cards group by Master data, Operations, Commercial and warehouse.
- Upload preview: confirm mapping/preview/status is readable on narrow screens and errors are not hidden below the fold.
- Export behavior: confirm column checkbox labels fit and preview table does not overlap.
- Usability issue to consider: `View structure` currently uses `alert(...)`; acceptable for review foundation, but target should use a modal/detail panel later.

## Target Review Tasks Before More Data Management Features

1. Create department-by-department service ownership boundaries.
2. Replace direct import execution designs with department-owned execution services.
3. Finalize grain and stable matching keys for every dataset.
4. Split ambiguous datasets: equipment assets vs models, inventory items vs stock balances vs transactions, service calls vs visits, PM plans vs tasks.
5. Add dataset-specific validation specs before any production-table import.
6. Re-run full route parity after deciding which legacy `/api/imports` paths stay active.
7. Complete visual browser review once browser tooling is available.
