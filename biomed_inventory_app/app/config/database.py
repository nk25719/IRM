import os
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
DATA_ROOT = Path(os.getenv("IRM_DATA_ROOT", Path.home() / "IRM-data")).resolve()
POSTGRESQL_DRIVERS = {"postgresql", "postgres"}
DEFAULT_DATABASE_URL = "postgresql+psycopg2://irm:irm@localhost:5432/irm"


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        database_url = DEFAULT_DATABASE_URL
    driver = database_driver(database_url)
    if driver == "postgres":
        return database_url.replace("postgres://", "postgresql://", 1)
    if driver != "postgresql":
        raise RuntimeError(
            f"Unsupported database driver '{driver}'. Configure DATABASE_URL with a PostgreSQL SQLAlchemy URL."
        )
    return database_url


def database_driver(database_url: str | None = None) -> str:
    url = database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    return urlparse(url).scheme.split("+", 1)[0]


def is_postgresql_database(database_url: str | None = None) -> bool:
    return database_driver(database_url) in POSTGRESQL_DRIVERS


def is_sqlite_database(database_url: str | None = None) -> bool:
    return False


def get_sqlite_database_path(database_url: str | None = None) -> Path:
    raise RuntimeError("SQLite support has been removed. Use SQLAlchemy sessions from app.database instead.")
