# Legacy Migration Issue Tracker

GitHub issue creation is required to complete this tracker. The local environment is not authenticated with `gh`, so these entries are issue titles to create and link.

Each legacy compatibility failure should link to one of these migration issues:

| Issue title | Legacy coverage currently affected | Target suite |
| --- | --- | --- |
| Migrate legacy startup schema creation to Alembic-only checks | `tests.test_database_foundation.ApplicationRouteSmokeTest`, startup `ensure_*` calls | `tests/postgres` |
| Port Alembic foundation tests from SQLite files to PostgreSQL test database | `tests.test_database_foundation.AlembicFoundationTest` | `tests/postgres` |
| Port database foundation fixtures to PostgreSQL transactions | `tests.test_database_foundation.DatabaseFoundationTest` | `tests/postgres` |
| Port data management center tests to PostgreSQL | `tests.test_data_management_center` | `tests/postgres` |
| Port customer contacts import tests to PostgreSQL | `tests.test_customer_contacts_import`, `tests.test_customer_contacts_large_import` | `tests/postgres` |
| Port engineer schedule tests to PostgreSQL | `tests.test_engineer_schedule` | `tests/postgres` |
| Port master data backfill tests to PostgreSQL | `tests.test_master_data_backfill` | `tests/postgres` |
| Extract quotation workflow from direct SQLite | `tests.test_quotation_generator` workflow tests | `tests/postgres` |
| Extract aftermarket service reports from direct SQLite | `tests.test_aftermarket_service_reports` | `tests/postgres` |
| Extract core legacy workflows from `legacy_main.py` | `tests.test_core_foundation` | `tests/postgres` |

The `Legacy compatibility debt` CI job is allowed to fail only while this tracker has open migration issues. When the table is empty, remove `continue-on-error: true` from that job or move the remaining tests into `tests/unit` and `tests/postgres`.
