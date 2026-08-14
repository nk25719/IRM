# Legacy Compatibility Tests

The existing top-level `tests/test_*.py` files include SQLite-dependent legacy coverage.

CI runs them in the non-blocking `Legacy compatibility debt` job so failures remain visible during the PostgreSQL/SQLAlchemy migration. This job becomes blocking only after all legacy fixtures and legacy database access have been migrated.
