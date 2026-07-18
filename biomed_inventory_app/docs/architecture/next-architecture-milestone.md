# Next Architecture Milestone

Date: 2026-07-18

## Objective

Move from a hybrid legacy/foundation baseline toward service-owned department workflows without changing visible business behavior.

## Recommended Sequence

1. Create a compatibility adapter for legacy `audit_log` writes that can mirror to `audit_events`.
2. Move one low-risk department read path from direct sqlite3 to SQLAlchemy service code.
3. Define warehouse item master, stock balance, and stock movement boundaries.
4. Define Data Management execution contracts per dataset before enabling production-table writes.
5. Add route-level tests for authenticated page/API behavior around the shared shell.

## Do Not Start Yet

- Production Data Management imports.
- Mapping profile persistence.
- Duplicate merging.
- Validation correction editing.
- New department workflows.
- A root Node/Vite/Expo setup.
