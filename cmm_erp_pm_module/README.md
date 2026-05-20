# CMM ERP PM Module Conversion

This package converts the uploaded PM Tracking React files into a clean ERP-compatible PM module.

## What is included

- `pm-frontend/` — Vite React PM Tracking module
- `src/components/` — your uploaded PM components
- `src/utils/` — missing utility files required by App.jsx
- `src/components/HospitalDetailView.jsx` — missing component implementation
- `src/styles.css` — CMM-style healthcare ERP CSS palette
- `fastapi_integration/pm_routes_patch.py` — FastAPI route snippet for serving the built PM module at `/pm`

## Why this conversion was needed

Your uploaded PM files are React files. The current deployed inventory app is FastAPI + static HTML/JS. So the safest ERP-ready structure is:

```text
/login
/portal
/inventory    existing inventory ERP module
/pm           React PM Tracking module
/crm          placeholder
/contracts    placeholder or connected later
/procurement  placeholder
/service-calls placeholder
/reports      placeholder
/admin        admin-only
```

## Run PM frontend locally

```bash
cd pm-frontend
npm install
npm run dev
```

Open the Vite URL, usually:

```text
http://127.0.0.1:5174/pm/
```

## Build PM frontend for FastAPI

```bash
cd pm-frontend
npm run build
```

Then copy build output into your FastAPI static folder:

```bash
mkdir -p ../app/static/pm
cp -R dist/* ../app/static/pm/
```

If this package is outside the app folder, copy `dist/*` manually into:

```text
biomed_inventory_app/app/static/pm/
```

## Add FastAPI route

Copy the logic from:

```text
fastapi_integration/pm_routes_patch.py
```

into your `app/main.py`.

If you already have login/session protection, protect `/pm` the same way as `/inventory`.

## Notes

- This PM module currently uses browser localStorage for its PM rows.
- That makes it safe as a first ERP module without touching the inventory database.
- Later, migrate PM data into backend APIs under `/api/pm/*`.
- Inventory APIs and PM APIs should remain separate.

## Uploaded file mapping

The uploaded files were mapped like this:

```text
App.jsx                                  -> pm-frontend/src/App.jsx
main.jsx                                 -> pm-frontend/src/main.jsx
DashboardCards.jsx                       -> pm-frontend/src/components/DashboardCards.jsx
EquipmentTable.jsx                       -> pm-frontend/src/components/EquipmentTable.jsx
FiltersBar.jsx                           -> pm-frontend/src/components/FiltersBar.jsx
HospitalSummary.jsx                      -> pm-frontend/src/components/HospitalSummary.jsx
ImportExportBar.jsx                      -> pm-frontend/src/components/ImportExportBar.jsx
EquipmentDetailModal.jsx                 -> pm-frontend/src/components/EquipmentDetailModal.jsx
ContractTrackerView.jsx                  -> pm-frontend/src/components/ContractTrackerView.jsx
ContractDetailView.jsx                   -> pm-frontend/src/components/ContractDetailView.jsx
```

Added missing files:

```text
src/styles.css
src/storage.js
src/utils/storage.js
src/utils/dateUtils.js
src/utils/csvUtils.js
src/components/HospitalDetailView.jsx
```
