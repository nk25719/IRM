# Contributing

## Development

Use PostgreSQL through SQLAlchemy for application database work. Do not add new direct `sqlite3` access or table creation in route handlers.

Before opening a pull request:

- Run `python -m compileall app alembic tests`.
- Run the focused tests for the area changed.
- Add or update Alembic migrations for schema changes.
- Keep generated runtime data out of Git.

## Routing

Cloud Run/FastAPI owns authenticated application routes. Firebase Hosting may serve static assets and redirect old aliases, but it must not redefine business route ownership differently from FastAPI.

## Security

Production must set `APP_ENV=production`, a strong `SESSION_SECRET`, non-default credentials, and `SESSION_COOKIE_SECURE=true`.
