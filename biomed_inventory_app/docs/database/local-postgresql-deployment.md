# Local PostgreSQL Deployment

The local deployment uses PostgreSQL 16 through Docker Compose and stores database files in a named Docker volume, not inside the Git repository.

## Environment

```env
POSTGRES_DB=irm
POSTGRES_USER=irm_user
POSTGRES_PASSWORD=change_me
DATABASE_URL=postgresql+psycopg://irm_user:change_me@db:5432/irm
IRM_DATA_ROOT=/data/irm
```

Do not commit real passwords.

## Start Database

```bash
docker compose up -d db
```

## Run Migrations

```bash
docker compose run --rm app alembic upgrade head
```

## Run App

```bash
docker compose up -d
```

## Volumes

- `irm_postgres_data`: PostgreSQL data.
- `irm_app_data`: application file storage.

Expected app storage:

```text
/data/irm/
├── attachments/
├── imports/
├── exports/
├── backups/
└── logs/
```

Attachments should be stored as files with metadata in the database unless a future requirement explicitly changes this.
