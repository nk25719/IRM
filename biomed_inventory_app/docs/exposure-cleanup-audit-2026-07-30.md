# IRM Codebase Cleanup and Exposure Audit

Date: 2026-07-30

## Executive Summary

The IRM app is a FastAPI/SQLAlchemy system with a modern modular layer sitting beside a large compatibility module, `app/legacy_main.py`. The highest cleanup value is not a broad rewrite; it is reducing duplicate route exposure, moving remaining legacy business logic into services, and tightening upload/download/admin surfaces.

Current route inventory from `app.main`:

- API routes: 330
- Page routes: 120
- Upload/import related routes: 49
- Export/download/report related routes: 46
- OpenAPI documentation routes: 3
- Static mounts: 3

The app has useful central structures already: shared shell files, a Data Management module, import batches, validation errors, audit events, service modules, and focused regression tests. The main risks are duplicate compatibility aliases, large modules, broad static upload exposure, default development credentials, public OpenAPI docs, and route handlers returning ad hoc dictionaries instead of explicit response schemas.

## Files Reviewed

Primary backend:

- `app/main.py`
- `app/legacy_main.py`
- `app/admin_api.py`
- `app/erp_api.py`
- `app/quotation_api.py`
- `app/aftermarket_service_reports.py`
- `app/routers/*.py`
- `app/services/*.py`
- `app/models/*.py`
- `app/schemas/*.py`
- `app/data_management/template_registry.py`
- `app/database.py`
- `app/config/*.py`

Primary frontend/static:

- `app/static/*.html`
- `app/static/app_layout.js`
- `app/static/theme.css`
- `app/static/pm/*`
- `pm-frontend/src/*`

Data/migrations/tests:

- `alembic/versions/*.py`
- `tests/*.py`
- `scripts/*.py`
- `firebase.json`
- `.env.example`

Generated/vendor folders such as `.venv` and `pm-frontend/node_modules` were excluded from code-quality findings.

## Code-Quality Findings

| Finding | Classification | Location | Why It Matters | Proposed Correction | Risk | Tests Needed |
| --- | --- | --- | --- | --- | --- | --- |
| Very large legacy entrypoint | Important architecture cleanup | `app/legacy_main.py` | 10k lines mixes routes, SQL, HTML helpers, auth, imports, exports, and workflow logic. | Continue extracting one domain at a time into routers/services while preserving aliases. | Medium | Route parity check, focused domain tests, app import smoke |
| Large modern routers/services | Important architecture cleanup | `app/quotation_api.py`, `app/routers/data_management_api.py`, `app/services/customer_contacts_import_service.py` | Harder review surface and higher regression risk. | Split pure parsing/export/schema logic from route handlers; keep handlers thin. | Medium | Existing quotation, data management, contacts tests |
| Duplicate route aliases | Important architecture cleanup | `/after-sales`, `/aftersales`, `/aftermarket`, `/quotations`, `/api/quotations`, `/admin/imports` | Same action/data is exposed through multiple URLs. Some aliases are compatibility, some are duplicate exposure. | Keep canonical routes, document compatibility aliases, add deprecation metadata where safe. | Medium | Route inventory diff and browser/page smoke |
| Ad hoc response dictionaries | Important architecture cleanup | Many routers, especially schedule, contacts, legacy routes | Easy to overexpose DB fields and hard to document API contracts. | Add Pydantic response schemas incrementally for high-value APIs. | Medium | Schema tests and frontend smoke |
| Repeated auth/role checks | Important architecture cleanup | `app/main.py`, `app/admin_api.py`, `app/legacy_main.py`, routers | Permission behavior is split between middleware, helper functions, and service methods. | Centralize permission dependency helpers and route metadata. | Medium | Permission tests per role |
| Inline frontend scripts | Style improvement | `app/static/*.html` | Table rendering, escaping, fetch handling, and import/export UI repeat across pages. | Move common table/action helpers to shared JS after stabilizing UI. | Low/Medium | Static layout tests, page smoke |
| Debug/CLI print statements | Optional refactor | `scripts/*.py` | Fine for scripts, but inconsistent with structured logging. | Leave scripts for now; use logging for app code. | Low | Script smoke if changed |
| Hard-coded display defaults | Style improvement | `app/legacy_main.py`, static pages | Defaults like credentials, role, salesperson, titles may drift from deployment settings. | Move operational defaults to environment/config where behavior-sensitive. | Medium | Login/auth and quotation UI tests |

## Exposure Inventory

| Item | Type | File | Route or Name | Intended Audience | Authentication | Data Exposed | Number of Exposures | Duplicate Exposure | Risk |
| --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| Home/portal | Web page | `app/legacy_main.py`, `app/static/portal.html` | `/`, `/home`, `/portal` | Users | Public | Department entry links | 3 | Yes, intentional aliases | Low |
| Login/logout | Web/auth | `app/legacy_main.py` | `/login`, `/logout` | Users | Public login | Auth state, errors | 2 | No | Medium due default creds |
| Swagger/OpenAPI | Docs/API | FastAPI default | `/docs`, `/redoc`, `/openapi.json` | Developers/admins | Public by `PUBLIC_PATHS` | Full API surface | 3 | Yes | Medium/High in production |
| Static assets | Static files | `app/main.py` | `/static` | Browser | Public for suffixes | CSS/JS/images | 1 mount | No | Low |
| Uploaded files | Static files | `app/main.py` | `/uploads` | Browser/API consumers | Requires auth middleware except mount itself | Uploaded documents/images | 1 mount | No | High if sensitive uploads are stored |
| Admin database map | Admin page/API | `app/admin_api.py` | `/admin/database-map`, `/api/admin/database-map` | Admin/data manager | Permission-gated | DB tables/columns/row counts | 2 | Yes | Medium |
| Admin imports | Admin page/API | `app/admin_api.py`, legacy | `/admin/imports`, `/imports`, `/api/admin/imports`, `/api/imports*` | Admin/data manager | Permission-gated | Import batches/rows/errors | 4+ | Yes | Medium |
| Data Management | Page/API | `app/routers/data_management_api.py`, `app/static/data_management.html` | `/administration/data-management`, `/api/data-management/*` | Data managers | Permission-gated | Templates, staged rows, export rows | 12+ | Partial with admin imports | Medium |
| Query reports | Admin page/API | `app/admin_api.py` | `/admin/query`, `/reports/query`, `/api/admin/query*` | Admin/report users | Permission-gated | Query result rows | 4 | Yes | High if query permissions too broad |
| Backups | Admin page/API | `app/admin_api.py` | `/admin/backups*` | Admin | Permission-gated | Database backups | 3 | No | High |
| Clients/CRM | Page/API | legacy + `customer_contacts_api.py` | `/clients`, `/crm`, `/api/clients`, `/api/crm/*` | Sales/After Sales/CRM | Permission-gated | Client, contacts, equipment, contracts, timeline | 20+ | Yes | Medium |
| Contacts | Page/API | `app/routers/customer_contacts_api.py` | `/crm/contacts`, `/api/contacts*`, `/api/imports/customer-contacts*` | CRM/data managers | Permission-gated | Names, emails, phones, engagement | 15+ | Partial | Medium/High privacy |
| Quotations | Page/API | `app/quotation_api.py` | `/quotations*`, `/api/quotations*`, `/sales/quotations` | Sales | Permission-gated | Commercial offers, prices, PDF/Excel | 20+ | Yes, compatibility alias | Medium |
| Warehouse | Page/API | legacy + routers | `/warehouse`, `/inventory`, `/api/warehouse*`, `/api/export` | Warehouse/admin | Permission-gated | Stock, movements, quantities | 10+ | Yes | Medium |
| Procurement | Page/API | legacy + router | `/procurement*`, `/api/procurement*`, `/api/purchase-orders*` | Procurement | Permission-gated | PO, supplier, shipment data | 15+ | Partial | Medium |
| Aftermarket/After Sales | Page/API | `aftermarket_service_reports.py`, `aftersales_api.py`, legacy | `/aftersales*`, `/after-sales*`, `/aftermarket*`, `/api/aftermarket*`, `/api/after-sales*` | After Sales | Permission-gated | cases, reports, equipment, parts | 25+ | Yes | Medium |
| Engineer schedule | Page/API | `app/routers/schedule_api.py`, `app/static/engineer_schedule.html` | `/aftersales/schedule`, `/api/schedule/*` | After Sales/coordinators | Permission-gated plus service write role | Engineer availability/events | 14 | No major duplicate | Medium |
| Service intelligence | Page/API | `app/routers/service_intelligence_api.py` | `/service/contract-intelligence*`, `/api/service-intelligence/*` | After Sales/contracts | Permission-gated | warranty/contract/opportunity details | 10+ | Aliases with After Sales | Medium |
| PM React bundle | Static/app | `app/static/pm`, `pm-frontend` | `/pm`, `/aftersales/contracts*` | After Sales | Permission-gated page | PM/contract tracker data | Multiple page aliases | Yes | Medium |
| Master data | API | `app/routers/master_data_api.py` | `/api/master-data/*` | Admin/data manager | Middleware only unless helper invoked | Canonical manufacturers/suppliers/categories | 20+ | No | Medium |
| General imports/exports | API | legacy + routers | `/api/import`, `/api/export`, `/api/exports/{report_name}`, `/api/bulk-export`, `/api/data-management/exports/*` | Admin/operators | Permission-gated by route prefixes inconsistently | Broad DB/report extracts | 10+ | Yes | High |

## Duplicate-Exposure Findings

- `quotations` are intentionally exposed both at `/quotations/*` and `/api/quotations/*`; preserve for compatibility, but document canonical API path.
- After Sales has three vocabulary families: `/aftersales`, `/after-sales`, and `/aftermarket`. This is the largest duplicate page/API exposure family.
- Import history exists in legacy/admin imports, generic imports API, customer contact imports, and Data Management imports.
- Export actions exist through generic full export, operational report export, Data Management export, and domain-specific exports.
- Exact duplicate route registrations detected at runtime:
  - `GET /admin/imports`
  - `GET /after-sales`
  - `GET /after-sales/{section:path}`
  - `GET /aftersales/pm-tracking`
  - `GET /sales-cases`

## Security Findings

| Finding | Classification | Location | Current Problem | Proposed Correction | Risk of Changing | Tests Needed |
| --- | --- | --- | --- | --- | --- | --- |
| Default admin credentials | Critical security fix | `app/legacy_main.py` | Defaults to `admin` / `admin123` if env is missing. | In non-local mode, require `APP_USERNAME`, `APP_PASSWORD`, and `SESSION_SECRET`. | Medium | Login tests with env variants |
| Default session secret | Critical security fix | `app/legacy_main.py`, `app/main.py` | Predictable fallback session secret. | Reject startup in production if secret is default. | Medium | Startup config tests |
| Session cookies not HTTPS-only | Critical security fix | `app/main.py`, `app/legacy_main.py` | `https_only=False`. | Use env-driven secure cookies, default secure for production. | Medium | Local/prod config tests |
| OpenAPI docs public | Important exposure reduction | FastAPI defaults + `PUBLIC_PATHS` | `/docs`, `/redoc`, `/openapi.json` public. | Gate docs in production or move behind admin permission. | Medium | Route/auth tests |
| `/uploads` static mount | Critical security fix | `app/main.py`, `app/legacy_main.py` | Uploaded files can be served by path; may include sensitive docs. | Serve downloads through checked endpoints with authorization and content-disposition. | High | Upload/download tests |
| Raw user-visible exception text | Important security cleanup | `schedule_api.py`, `customer_contacts_api.py`, `master_data_api.py`, legacy | `detail=str(exc)` can leak internals. | Map expected exceptions to safe messages and log internals. | Medium | Error response tests |
| Admin query endpoint | Critical security fix | `app/admin_api.py` | Powerful query/export surface. | Enforce SELECT-only parsing, parameter rules, row limits, audit logs, admin permission. | Medium/High | Query security tests |
| Mass assignment | Important security cleanup | `schedule_service.py`, contacts/master data routes | Payload dicts set model fields by name. | Use Pydantic request schemas with allowed fields. | Medium | Create/update tests |
| Overbroad data returns | Important schema cleanup | CRM/equipment/service intelligence endpoints | Some endpoints aggregate contacts, contracts, equipment, internal IDs. | Explicit response schemas and field-level permission trimming. | Medium | API contract tests |
| Frontend `innerHTML` | Important XSS cleanup | Static pages | Most values use `esc`, but many pages build HTML via strings. | Centralize rendering/escaping helpers and avoid raw server messages. | Medium | Static tests/manual smoke |

## Recommendations

### Critical Security Fixes

1. Production config hardening: fail startup when default credentials/session secret are used outside local development.
2. Restrict `/uploads`: replace static exposure with authenticated download endpoints.
3. Gate Swagger/OpenAPI in production.
4. Harden admin query/export endpoints with strict permission and query validation.

### Important Architecture Cleanup

1. Canonical route map: document canonical paths and compatibility aliases.
2. Gradually extract `legacy_main.py` domains into routers/services.
3. Consolidate import/export into Data Management where possible while preserving specialized workflows.
4. Add request/response schemas for high-risk APIs: contacts, schedule, quotations, admin imports/exports.
5. Centralize permission dependencies and remove per-router role drift.

### Style Improvements

1. Move shared static page helpers from inline scripts into common JS.
2. Normalize table/import/export action styling through the shared shell.
3. Replace repeated hard-coded labels/defaults with constants or config.
4. Use structured logging in app code.

### Optional Refactors

1. Split `theme.css` into shell, components, and page overrides after visual tests exist.
2. Split `quotation_api.py` into router, repository, service, and schema modules.
3. Add generated route inventory documentation in CI.

## Proposed Safe Implementation Plan

1. Add route inventory tests and a machine-readable route snapshot.
2. Remove exact duplicate route registrations only when route parity proves no behavior loss.
3. Add production config guard for default credentials/session secret behind an environment flag.
4. Add explicit schemas to one high-risk module at a time, starting with schedule or contacts.
5. Move `/uploads` to authenticated download endpoints for new uploads; leave legacy URLs temporarily.
6. Consolidate import/export UI labels and route targets through Data Management.
7. Add docs for canonical routes and compatibility aliases.

## Files Changed In This Audit Pass

- `docs/exposure-cleanup-audit-2026-07-30.md`

No behavior-changing code cleanup was made as part of this audit document. Existing uncommitted application changes from previous work remain untouched.

## Tests Added or Updated

No new tests were added in this audit-only pass.

Recommended next tests before architecture cleanup:

- `python3 -m unittest tests.test_static_layout -v`
- `python3 -m unittest tests.test_data_management_center -v`
- `python3 -m unittest tests.test_customer_contacts_import tests.test_customer_contacts_large_import -v`
- `python3 -m unittest tests.test_engineer_schedule tests.test_quotation_generator -v`
- `python3 -m py_compile app/main.py app/legacy_main.py app/routers/*.py app/services/*.py`
- `python3 -c "from app.main import app; print('app import OK', len(app.routes))"`

## Commands Executed

- `find . -maxdepth 3 -type f ...`
- `python3` route inventory from `app.main`
- `python3` first-party large-file line count scan
- `rg` scans for imports, exports, uploads, docs, secrets, raw SQL, exception exposure, debug prints, and static rendering risks
- `git status --short`

## Test and Lint Results

This phase was inspection-only. No lint or full test run was executed after creating this document.

Known useful recent focused checks for adjacent work passed before this audit:

- `node --check app/static/app_layout.js`
- `python3 -m py_compile ...`
- `python3 -m unittest tests.test_static_layout tests.test_customer_contacts_import tests.test_engineer_schedule -v`

## Remaining Risks

- Full endpoint-by-endpoint data schema inventory still needs generated OpenAPI comparison plus representative authenticated calls.
- Compatibility aliases are mixed with true duplicates; removing aliases without a migration plan could break bookmarks/deploy rewrites.
- The repo has an already dirty worktree; cleanup must avoid reverting unrelated user work.
- Production behavior cannot be fully assessed without the intended deployment environment and environment variables.

## Items Requiring Human Approval

- Whether to disable public Swagger/OpenAPI in production.
- Whether to reject startup when default `APP_USERNAME`, `APP_PASSWORD`, or `SESSION_SECRET` are used.
- Whether old aliases such as `/after-sales` and `/aftermarket` can redirect permanently to `/aftersales`.
- Whether uploaded files may remain directly addressable under `/uploads`.
- Which import/export route family should be canonical for each department.
