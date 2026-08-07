# IRM

Biomedical ERP workspace for the IRM/CMM inventory, warehouse, sales, procurement, after-sales, contracts, scheduling, and administration application.

The main FastAPI application lives in:

```text
biomed_inventory_app/
```

## Run The App

```bash
cd biomed_inventory_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Production Notes

- Cloud Run/FastAPI owns authenticated routes, APIs, sessions, uploads, and database-backed pages.
- Firebase Hosting is only for static assets and legacy redirects that match FastAPI ownership.
- Use PostgreSQL through SQLAlchemy for production database work.
- Set strong production values for `APP_ENV`, `DATABASE_URL`, `SESSION_SECRET`, `APP_USERNAME`, and `APP_PASSWORD`.

See `biomed_inventory_app/README.md` for app-specific details.
