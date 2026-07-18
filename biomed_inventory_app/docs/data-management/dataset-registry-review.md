# Dataset Registry Review

Date: 2026-07-18

## Source

`app/data_management/template_registry.py`

## Purpose

The registry defines dataset keys, labels, domains, descriptions, versions, fields, required fields, examples, import support, export support, export tables, and export ordering. It is the Data Management Center contract for template generation, upload validation, and export column allow-listing.

## Current Enabled Import Datasets

- `clients`
- `departments`
- `contacts`
- `manufacturers`
- `suppliers`
- `equipment_categories`
- `equipment_models`
- `equipment`
- `inventory_items`
- `service_calls`

## Current Export-Supported Datasets

- `clients`
- `departments`
- `contacts`
- `manufacturers`
- `suppliers`
- `equipment_categories`
- `equipment_models`
- `equipment`
- `inventory_items`

## Review Notes

- Sensitive fields are excluded from export defaults.
- Export requests are checked against registered fields and live table columns.
- Disabled datasets remain visible as future contracts but are not executable.
- Several dataset names intentionally need later refinement, especially `equipment`, `inventory_items`, `service_calls`, `preventive_maintenance`, and `contracts`.

## Decision

Keep the registry as the canonical staging contract for this checkpoint. Do not enable deferred datasets or production execution until ownership, grain, key, duplicate, validation, and rollback behavior are documented per dataset.
