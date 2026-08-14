# Contributing

Work from `biomed_inventory_app/` for the FastAPI application.

Before opening a PR:

- Run the focused tests for the area changed.
- Run `python -m compileall app alembic tests` from `biomed_inventory_app/`.
- Keep generated runtime data and build output out of Git.
- Add Alembic migrations for schema changes.
- Do not add new direct database access outside the SQLAlchemy session layer.

For routing changes, keep Cloud Run/FastAPI and Firebase redirects aligned. Firebase must not point a business route to different content than the FastAPI app.
