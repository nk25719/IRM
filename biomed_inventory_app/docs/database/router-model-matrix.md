# Router Model Matrix

## Dependency Matrix

| module | line | method | endpoint | function | schema | model | operation | legacy_dependency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| app/admin_api.py | 479 | GET | /admin/database-map | database_map_page | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 485 | GET | /admin/imports | imports_page | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 492 | GET | /admin/query | query_page | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 492 | GET | /reports/query | query_page | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 500 | GET | /api/admin/security/me | security_me | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 506 | GET | /api/admin/database-map | database_map | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 549 | GET | /api/admin/import-targets | import_targets | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 593 | POST | /api/admin/imports/{batch_id}/confirm | import_confirm | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 622 | GET | /api/admin/imports | list_admin_imports | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 630 | POST | /admin/backups/create | create_backup_endpoint | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 680 | GET | /admin/backups | backups | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 686 | GET | /admin/backups/{filename}/download | backup_download | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 703 | GET | /api/admin/reports | report_list | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 709 | GET | /api/admin/reports/{report_id} | report_run | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/admin_api.py | 717 | GET | /api/admin/reports/{report_id}/export | report_export | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/quotation_api.py | 401 | POST |  | create_quotation | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 401 | POST | / | create_quotation | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 459 | GET |  | list_quotations | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 459 | GET | / | list_quotations | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 475 | POST | /demo/cmm-service-offer | create_cmm_service_demo | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 550 | GET | /{quotation_id} | get_quotation | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 557 | PATCH | /{quotation_id} | patch_quotation | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 576 | DELETE | /{quotation_id} | delete_quotation | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 588 | POST | /{quotation_id}/items | create_item | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 599 | POST | /{quotation_id}/equipment-groups | create_equipment_group | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 617 | PATCH | /{quotation_id}/equipment-groups/{group_id} | patch_equipment_group | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 634 | DELETE | /{quotation_id}/equipment-groups/{group_id} | delete_equipment_group | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 645 | POST | /{quotation_id}/equipment-groups/{group_id}/items | create_group_item | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 658 | PATCH | /{quotation_id}/items/{item_id} | patch_item | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 681 | DELETE | /{quotation_id}/items/{item_id} | delete_item | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 703 | POST | /{quotation_id}/validate-ai | validate_ai | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 732 | GET | /{quotation_id}/export/excel | export_excel | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/quotation_api.py | 745 | GET | /{quotation_id}/export/pdf | export_pdf | Pydantic classes | raw sqlite tables | read/write/export/import/delete per function | no |
| app/erp_api.py | 58 | GET | /dashboard/summary | dashboard_summary | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/erp_api.py | 69 | GET | /pm/tasks | pm_tasks | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/erp_api.py | 75 | GET | /{resource} | list_records | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/erp_api.py | 82 | GET | /{resource}/{record_id} | get_record | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/erp_api.py | 91 | POST | /{resource} | create_record | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/erp_api.py | 102 | PUT | /{resource}/{record_id} | update_record | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/erp_api.py | 117 | DELETE | /{resource}/{record_id} | delete_record | dynamic dict/Pydantic | SQLAlchemy dynamic resource map | read/write/export/import/delete per function | no |
| app/aftermarket_service_reports.py | 475 | GET | /service-reports | list_service_reports | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/aftermarket_service_reports.py | 495 | GET | /equipment-assets | list_equipment_assets | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/aftermarket_service_reports.py | 534 | GET | /service-reports/{sr_number} | get_service_report | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/aftermarket_service_reports.py | 545 | GET | /service-report-parts/usage | spare_parts_usage | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/aftermarket_service_reports.py | 563 | GET | /equipment/service-history | equipment_service_history | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/aftermarket_service_reports.py | 608 | GET | /service-reports/analytics/summary | service_report_analytics | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/routers/dashboard_api.py | 33 | GET | /api/aftermarket/dashboard | aftermarket_dashboard | none/legacy | raw sqlite tables | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 10 | GET | /aftermarket | aftermarket_page_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 15 | GET | /aftermarket/{section:path} | aftermarket_section_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 20 | GET | /after-sales | after_sales_legacy_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 25 | GET | /after-sales/{section:path} | after_sales_legacy_section_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 30 | GET | /aftersales/pm-tracking | aftersales_pm_tracking_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 35 | GET | /aftersales/pm-tracking/{section:path} | aftersales_pm_tracking_section_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |
| app/routers/web_pages.py | 40 | GET | /sales-cases | sales_cases_alias | none/legacy | legacy mounted | read/write/export/import/delete per function | yes |

## Legacy Route Surface
`app/legacy_main.py` declares approximately **209** `@app.*` routes. Modular routers mount subsets via `_legacy.mount_legacy_routes`, so business logic remains split between new routers and legacy implementation.

## Direct Model Query Pattern
- `app/erp_api.py` uses SQLAlchemy ORM directly.
- `app/admin_api.py`, `app/quotation_api.py`, and `app/aftermarket_service_reports.py` use raw SQLite SQL.
- Department routers mostly remount legacy routes.
