# Engineer Scheduling Module

The Engineer Schedule module lives under After Sales at `/aftersales/schedule`.
It uses the existing FastAPI app, SQLAlchemy database, shared shell, users,
engineers, clients, client sites, equipment, service cases, PM tasks, contracts,
import batches, and audit events.

## Creating Events

Open `/aftersales/schedule`, choose `New Event`, and enter the title, type,
status, start/end time, client, equipment, location, travel buffers, assigned
engineers, and notes. Use `Save as Draft` when the work is not ready for the
coordinator schedule, or `Schedule` for a live assignment.

Events can have no engineer, one engineer, or several engineers. Assignments
are stored in `engineer_schedule_assignments`; engineer IDs are never stored as
comma-separated text or JSON.

## Conflicts

Conflicts are warnings, not hard blocks. The backend checks each assigned
engineer for:

- direct overlaps using `new_start < existing_end AND new_end > existing_start`
- all-day and timed overlaps
- travel-buffer conflicts
- unavailable or leave records
- missing engineer or missing times
- inactive engineers
- events outside standard working hours

Cancelled events are excluded from active conflict checks. Authorized
coordinators can save with an override reason; the reason is stored in
`schedule_change_log` and the shared `audit_events` table.

## Importing Weekly Excel Schedules

Use `Import` on `/aftersales/schedule` to upload the current weekly workbook.
The preview detects the worksheet, `Week of` date, Monday-Saturday columns,
separable activities inside cells, common time formats, possible clients, and
unresolved rows. Confirmation creates structured schedule events and stores the
original cell text in `source_reference`. Duplicate imports are blocked by file
checksum unless explicitly allowed through the API.

## Exporting

The page provides two exports:

- structured schedule export with dates, engineers, linked records, status,
  priority, conflicts, and notes
- weekly-grid export with one row per engineer and Monday-Saturday cells

Excel remains an import/export interface only; the database is the source of
truth.

## Linked IRM Records

The API can create schedule events from source records with:

- `POST /api/schedule/from/service_case/{id}`
- `POST /api/schedule/from/pm/{id}`
- `POST /api/schedule/from/contract/{id}`
- `POST /api/schedule/from/customer_contract/{id}`

The schedule event links back to the source record and pre-fills available
client, equipment, title, and type fields. Completing a schedule event does not
automatically complete the underlying service case or PM record.
