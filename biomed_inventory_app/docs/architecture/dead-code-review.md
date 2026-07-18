# Dead Code Review

Date: 2026-07-18

## Removed Now

| File or symbol | Why it was dead | Verification | Replacement |
|---|---|---|---|
| `app/pm_routes_patch.py` | It was an instruction snippet, not imported by `app.main`, and referenced undefined `app` and `BASE_DIR` if imported directly. | `rg pm_routes_patch`, `rg pm_module_page`, and router registration review found no callers. PM routes are served by active web/static routes and mounted `/pm/assets`. | Existing `app.routers.web_pages` routes and `app/static/pm/index.html`. |
| `app/backups/inventory_20260709_065303.db` | Generated runtime database backup committed into source. | Backup functionality writes runtime artifacts under `app/backups/`; database policy excludes mutable DB files from Git. | Runtime backup creation through Admin/CLI, ignored by Git. |
| `app/backups/inventory_20260709_065303.db.zip` | Generated runtime backup archive committed into source. | Same as above. | Runtime backup creation through Admin/CLI, ignored by Git. |

## Still Active

- `app/legacy_main.py`: large but active startup and workflow owner.
- `app/legacy_static/warehouse_legacy.html`: retained as legacy static artifact because it is tracked and references active warehouse APIs; removal needs separate route/static ownership review.
- `app/admin_api.py`, `app/quotation_api.py`, `app/aftermarket_service_reports.py`: active routers.
- `app/static/app_layout.js` and `app/static/theme.css`: canonical shared sidebar implementation.

## Compatibility Code

- `app.main.__getattr__`.
- `app.routers._legacy`.
- `audit_log.item_id` idempotent startup patch.
- Aftermarket route aliases.

## Possibly Obsolete, Not Removed

- `app/legacy_static/warehouse_legacy.html`: appears superseded by `app/static/warehouse.html`, but it was not removed because no full static deployment parity review was performed in this pass.
- Some old Excel import/export paths in `legacy_main.py`: still reachable through active routes and tests.
- Root `python3 -m unittest discover -v`: now discovers the suite because `tests/__init__.py` was added, but documentation keeps `python3 -m unittest discover -s tests -v` as the explicit checkpoint command.

## npm/Expo Review

No Expo references or root package configuration were found. The root `package-lock.json` was an accidental artifact and was removed before this checkpoint. `pm-frontend/package.json` is the only package file and must be used from `pm-frontend/`.
