# Backup And Restore

Always back up before applying migrations to an existing database.

## SQLite Backup

```bash
cp app/data/inventory.db app/data/inventory.$(date +%Y%m%d-%H%M%S).db
```

## SQLite Restore

```bash
cp app/data/inventory.backup.db app/data/inventory.db
```

Stop the application before restoring SQLite files.

## PostgreSQL Custom Backup

```bash
pg_dump "$DATABASE_URL" -Fc -f backups/irm.$(date +%Y%m%d-%H%M%S).dump
```

## PostgreSQL Plain SQL Backup

```bash
pg_dump "$DATABASE_URL" -f backups/irm.$(date +%Y%m%d-%H%M%S).sql
```

## PostgreSQL Restore From Custom Backup

```bash
pg_restore --clean --if-exists --dbname "$DATABASE_URL" backups/irm.dump
```

## PostgreSQL Restore From SQL

```bash
psql "$DATABASE_URL" -f backups/irm.sql
```

## Migration Safety Checklist

1. Create a backup.
2. Copy the database to a disposable test location.
3. Run `alembic upgrade head` on the copy.
4. Run integrity and application smoke tests.
5. Only then run the migration on the intended database.
