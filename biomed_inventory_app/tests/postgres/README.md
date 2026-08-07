# PostgreSQL Integration Tests

Tests in this directory are blocking in CI.

Rules:

- Use PostgreSQL through SQLAlchemy.
- Run Alembic before database integration tests.
- Do not create `.db` files.
- Do not import `sqlite3`.
