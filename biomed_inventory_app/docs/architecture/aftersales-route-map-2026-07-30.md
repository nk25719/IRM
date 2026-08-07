# Aftermarket / After Sales Route Map

Generated before navigation changes on 2026-07-30.

## Existing Page Inventory

- `app/static/after_sales.html` serves the main Aftermarket workspace for `/aftersales`, `/after-sales`, and most `/aftersales/{section}` catch-all routes. It currently contains dashboard, operations, installed base, service history, coverage, spare parts, PM summary, and analytics panels.
- `app/static/engineer_schedule.html` serves `/aftersales/schedule` and `/after-sales/schedule`, with weekly schedule, import, workload, unassigned queue, and engineer assignment views.
- `app/static/pm.html` serves `/aftersales/pm`, `/aftersales/pm-tracking`, `/after-sales/pm`, and nested PM sections. It contains PM dashboard, schedule, calendar, assets, reports, and history.
- `app/static/pm/index.html` is the React PM/contracts bundle served by `/aftersales/contracts`, `/after-sales/contracts`, `/pm`, and nested contracts routes. It owns contract tracker and hospital contract status.
- `app/static/service_intelligence.html` serves service contract intelligence routes such as `/aftersales/contract-intelligence`, `/service/contract-intelligence`, `/service/customer-contracts`, and `/administration/manufacturer-coverage`.
- `app/static/crm_client.html` contains client-level After Sales views and links to service calls, PM, contracts, FMI, delivery/installation, and quotations from a client context.
- `app/static/quotations.html` owns quotation workflow pages under `/quotations`, `/api/quotations`, and `/sales/quotations`; Aftermarket links currently point at `/aftersales/quotations`, which falls through to `after_sales.html`.

## Current-To-Proposed Route Mapping

| Primary Tab | Existing Page | Current Route | Proposed Route | Page Purpose | Keep / Merge / Redirect / Remove |
| ----------- | ------------- | ------------- | -------------- | ------------ | -------------------------------- |
| Dashboard | `after_sales.html` dashboard panel | `/aftersales`, `/after-sales` | `/aftersales/dashboard` | Operational summaries, overdue work, workload, alerts, upcoming visits | Keep `/aftersales` as compatibility entry; add `/aftersales/dashboard` canonical tab route |
| Dashboard | Legacy dashboard API | `/api/after-sales/dashboard`, `/api/aftermarket/dashboard` | `/api/aftermarket/dashboard/summary` for operational dashboard | Dashboard data | Keep legacy API for old consumers; use summary endpoint for new dashboard |
| Service Calls | `after_sales.html` service history/calls panels | `/aftersales/service-calls`, `/aftersales/service-cases`, `/aftersales/service-history/*` | `/aftersales/service-calls` | Corrective calls, service reports, open/closed calls, equipment fault history | Merge under Service Calls; redirect `service-cases` and `service-history/*` to filtered Service Calls routes where possible |
| Service Calls | `engineer_schedule.html` assignment context | `/aftersales/schedule` | `/aftersales/service-calls?view=assigned` or linked schedule | Engineer assignment support for calls | Keep schedule as a linked support page, not a primary tab |
| Quotations | `quotations.html` Sales quotation page and Aftermarket catch-all | `/sales/quotations`, `/quotations`, `/aftersales/quotations` | `/aftersales/quotations` | Service, repair, inspection, parts quotations and PDF exports | Keep page owner as Quotations; connect Aftermarket tab to canonical path; legacy sales/global quotation routes remain cross-module links |
| Preventive Maintenance | `pm.html` | `/aftersales/pm`, `/aftersales/pm/schedule`, `/aftersales/pm/calendar`, `/aftersales/pm/reports` | `/aftersales/preventive-maintenance` | PM schedules, due work, calendars, reports, contracted/non-contract PM | Keep PM page; add canonical redirect/alias from preventive-maintenance to existing PM page first |
| Preventive Maintenance | `pm.html` legacy alias | `/aftersales/pm-tracking`, `/after-sales/pm-tracking` | `/aftersales/preventive-maintenance` | Legacy PM tracker access | Redirect |
| Installations | `after_sales.html` operations row | `/aftersales/installations`, `/aftersales/delivery-installation` | `/aftersales/installations` | Installation planning, readiness, checklist, completion | Keep catch-all view for now; split ownership from deliveries in navigation |
| Deliveries | `after_sales.html` operations row and warehouse cross-links | `/aftersales/deliveries`, `/aftersales/delivery-installation`, `/warehouse/delivery-orders` | `/aftersales/deliveries` | Delivery scheduling, handover, delivery-linked installation | Keep After Sales delivery tab; warehouse delivery orders remain Warehouse-owned cross-links |
| Trainings | `after_sales.html` operations row and schedule event type | `/aftersales/training-demo`, `/training-demo`, `/training` | `/aftersales/trainings` | User, technical, application, and post-installation training | Redirect After Sales training-demo child route; global Training & Demo remains master-data/cross-module |
| Contracts | `pm/index.html` React bundle | `/aftersales/contracts`, `/aftersales/contracts/hospital-status`, `/after-sales/contracts/*` | `/aftersales/contracts`, `/aftersales/contracts/hospital-status`, `/aftersales/contracts/renewals` | Customer service contracts overview, PM contract coverage, hospital contract status | Keep as canonical contracts tab; do not route contracts dashboard to PM |
| Contracts | `service_intelligence.html` | `/aftersales/contract-intelligence`, `/service/contract-intelligence`, `/service/customer-contracts` | `/aftersales/contracts/renewals` or linked intelligence subview | Coverage gaps, warranty timing, renewal opportunities | Merge under Contracts as linked subview; preserve old service-intelligence URLs as aliases |
| Contracts | Manufacturer coverage | `/administration/manufacturer-coverage` | `/administration/manufacturer-coverage` | Manufacturer coverage/admin data | Keep outside After Sales main tabs |
| Spare Parts Requests | `after_sales.html` spare parts panel | `/aftersales/spare-parts`, `/aftersales/spare-parts/*` | `/aftersales/spare-parts` | Parts required for calls, usage, approval, availability, delays | Keep as canonical tab; do not expose warehouse stock adjustment here |
| FMI / Technical Cases | `after_sales.html` operations row and CRM client links | `/aftersales/fmi-field-modifications`, `/aftersales/fmi-recall` | `/aftersales/technical-cases` | FMI, recalls, manufacturer technical cases, escalations | Merge and redirect legacy FMI URLs to technical-cases |
| Installed Base | `after_sales.html` installed/coverage panels and `equipment_database.html` | `/aftersales/installed-base/*`, `/equipment-database`, `/equipment-registry` | Linked from Service Calls, PM, Contracts, Installations | Equipment context, serials, warranty status | Remove as primary Aftermarket tab; keep as supporting linked page |
| Coverage | `after_sales.html` warranty panel | `/aftersales/coverage/*`, `/aftersales/warranty` | `/aftersales/contracts` | Warranty and contract status | Merge into Contracts; redirect broad After Sales coverage URLs where safe |
| Analytics / Reports | `after_sales.html` analytics panel and PM reports | `/aftersales/analytics/*`, `/aftersales/reports` | Dashboard summaries or tab-level exports | Analysis and reporting | Remove as primary tab; keep reports as exports inside each owner tab |
| Hospital CRM | `crm_client.html` | `/crm/client/{id}`, `/aftersales/hospital-crm` metadata only | `/crm/client/{id}` with links into tabs | Client-specific cross-module view | Keep under Clients; do not duplicate as Aftermarket tab |

## Canonical Primary Routes

- `/aftersales/dashboard`
- `/aftersales/service-calls`
- `/aftersales/quotations`
- `/aftersales/preventive-maintenance`
- `/aftersales/installations`
- `/aftersales/deliveries`
- `/aftersales/trainings`
- `/aftersales/contracts`
- `/aftersales/spare-parts`
- `/aftersales/technical-cases`

## Duplicate, Legacy, And Orphaned Routes

- Legacy roots: `/aftermarket`, `/after-sales`, and nested `/after-sales/*` should redirect to `/aftersales/*`.
- PM legacy: `/aftersales/pm`, `/aftersales/pm-tracking`, and `/after-sales/pm*` should remain working, with user-facing navigation preferring `/aftersales/preventive-maintenance`.
- Reports legacy: `/aftersales/reports` currently redirects to `/aftersales/pm/reports`; future owner should be tab-level reports/exports.
- Service call duplicates: `/aftersales/service-cases` and `/aftersales/service-history/*` should fold into `/aftersales/service-calls`.
- FMI duplicates: `/aftersales/fmi-recall` and `/aftersales/fmi-field-modifications` should fold into `/aftersales/technical-cases`.
- Delivery/installation duplicate: `/aftersales/delivery-installation` should stop being a shared owner and redirect/link to either Installations or Deliveries depending on context.
- Installed base and coverage are supporting views, not primary tabs.

## Permission Notes

- Preserve existing route permission grouping for `/aftersales`, `/api/aftermarket`, and `/api/after-sales`.
- Keep manufacturer coverage under Administration/Service Intelligence instead of exposing it as a customer contract tab.
- Keep warehouse stock adjustment and purchasing controls in Warehouse/Procurement; After Sales should only link to availability or request workflows.
