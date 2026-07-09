# IRM ERM Database Guide

This guide explains the IRM database in beginner-friendly terms: where it lives, how tables are created, how imports work, how backups work, and how roles protect sensitive data.

## Where The Database Is Stored

The app supports two database modes:

- `DATABASE_URL` set: the app is prepared to use the database described by that URL, usually PostgreSQL.
- `DATABASE_URL` not set: the local SQLite database is used at `app/data/inventory.db`.

The admin page `/admin/database-map` shows the active engine and a safe version of the database location. If a URL contains a password, the password is hidden.

## How Tables Are Created

Most existing tables are created by `app/legacy_main.py` in the `init_db()` function. The newer admin foundation adds only additive tables and columns through `app/admin_api.py`.

Important table families:

- Client master data: `clients`, `departments`, `contacts`
- Equipment and service: `equipment`, `service_calls`, `pm_tasks`
- Case workflow: `cases`, `case_items`, `case_timeline`
- Warehouse: `inventory`, `inventory_items`, `stock_items`, `stock_movements`
- Sales: `quotations`, `quotation_items`, `quotation_equipment_groups`, `customer_orders`
- Procurement and logistics: `purchase_orders`, `purchase_order_items`, `shipments`, `receptions`, `delivery_orders`
- Finance: `invoices`, `payments`
- Admin foundation: `roles`, `permissions`, `role_permissions`, `user_roles`, `import_batches`, `import_errors`, `audit_log`

## What Migrations Are

A migration is a controlled database change. Instead of manually changing a production database, you write a migration that says what table or column should be added.

Migrations matter because they make database changes repeatable:

- Local developer database
- Test database
- Cloud Run or production database
- Future PostgreSQL database

## How Alembic Works

Alembic is the migration tool included in this repo. Migration files live in `alembic/versions/`.

Typical commands:

```bash
alembic revision -m "describe the change"
alembic upgrade head
alembic downgrade -1
```

Today, many legacy tables are still created by `init_db()`. As the app moves further toward PostgreSQL, new structural changes should increasingly be represented as Alembic migrations.

## How To Add A New Table

For a quick local-compatible addition:

1. Add `CREATE TABLE IF NOT EXISTS ...` to the startup initializer.
2. Add missing-column checks with `PRAGMA table_info(...)` for SQLite compatibility.
3. Add a matching Alembic migration for PostgreSQL-ready deployments.
4. Add the table to `/admin/database-map` explanations if it is important for users.
5. Add tests for insert, read, and update behavior.

For long-term production work, prefer Alembic first.

## Bulk Import Data

Open `/admin/imports`.

Supported CSV/XLSX targets include:

- `clients`
- `departments`
- `contacts`
- `equipment`
- `inventory_items`
- `service_calls`
- `pm_tasks`
- `quotation_items`
- `purchase_order_items`

Import flow:

1. Choose the target table.
2. Upload a CSV or Excel file.
3. Preview detected columns.
4. Map file columns to database fields.
5. Validate rows.
6. Review errors before saving.
7. Confirm import.
8. The app creates an `import_batches` record.
9. Errors are stored in `import_errors`.
10. Successful inserts are recorded in `audit_log`.

The import system does not blindly overwrite existing data. It skips duplicates using these rules:

- Client: normalized client name
- Department: client plus department name
- Contact: email, or client plus name
- Equipment: serial number
- Inventory item: PN or item code
- Service call: source reference, case number, or call number

## Back Up The Database

Manual UI backup:

1. Open `/admin/database-map`.
2. Click `Create Backup`, or call `POST /admin/backups/create`.
3. Backups are stored in `app/backups/`.

CLI backup:

```bash
python3 scripts/backup_database.py
```

SQLite backups:

- Copy `app/data/inventory.db`
- Save as `app/backups/inventory_YYYYMMDD_HHMMSS.db`
- Also create a compressed `.zip`
- Keep the latest 30 backup sets

PostgreSQL backups:

- Use `pg_dump`
- Save to `app/backups/inventory_YYYYMMDD_HHMMSS.dump`
- Also create a compressed `.zip`

## Restore Safely

Restore is intentionally not available as a normal UI button.

SQLite restore:

```bash
python3 scripts/restore_database.py app/backups/inventory_YYYYMMDD_HHMMSS.db
```

PostgreSQL restore:

```bash
python3 scripts/restore_database.py app/backups/inventory_YYYYMMDD_HHMMSS.dump
```

The restore script requires typing `RESTORE` twice. Stop the running app before restoring.

## Move From SQLite To PostgreSQL

High-level path:

1. Set `DATABASE_URL` to a PostgreSQL URL.
2. Run Alembic migrations with `alembic upgrade head`.
3. Export SQLite data into CSV or a migration script.
4. Import the data into PostgreSQL.
5. Run `/admin/database-map` and compare table counts.
6. Run smoke tests for clients, warehouse, quotations, imports, and reports.

PostgreSQL backup command used by the app:

```bash
pg_dump "$DATABASE_URL" -Fc -f app/backups/inventory_YYYYMMDD_HHMMSS.dump
```

PostgreSQL restore command:

```bash
pg_restore --clean --if-exists --dbname "$DATABASE_URL" app/backups/inventory_YYYYMMDD_HHMMSS.dump
```

## Security Roles And Permissions

Default roles:

- `admin`
- `sales`
- `procurement`
- `warehouse`
- `after_sales`
- `engineer`
- `viewer`

Important permissions:

- `view_all_clients`
- `view_prices`
- `edit_quotations`
- `approve_quotations`
- `export_pdf`
- `import_data`
- `manage_users`
- `create_backup`
- `view_reports`
- `view_after_sales_cases`
- `edit_service_calls`
- `view_database_map`
- `run_select_queries`

Users without `view_prices` should not see unit prices, totals, supplier prices, invoice values, or quotation totals in admin reports/query results.

## Safe Query And Reporting

Open `/admin/query` or `/reports/query`.

Admins can run read-only `SELECT` statements. Destructive SQL such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `PRAGMA`, `VACUUM`, `ATTACH`, and `DETACH` is blocked.

Predefined reports:

- Open service calls by engineer
- Pending quotations by salesperson
- Pending customer orders
- Pending POs
- Upcoming shipments
- Warehouse low stock
- Equipment by client
- Cases by status
- PM tasks due this month

Reports can be exported to Excel.
