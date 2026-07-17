import os
from pathlib import Path
from urllib.parse import unquote, urlparse

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
DEFAULT_SQLITE_PATH = DATA_DIR / "inventory.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    legacy_db_path = os.getenv("DB_PATH")
    if legacy_db_path:
        return f"sqlite:///{legacy_db_path}"
    return DEFAULT_DATABASE_URL


def database_driver(database_url: str | None = None) -> str:
    url = database_url or get_database_url()
    return urlparse(url).scheme.split("+", 1)[0]


def is_sqlite_database(database_url: str | None = None) -> bool:
    return database_driver(database_url) == "sqlite"


def is_postgresql_database(database_url: str | None = None) -> bool:
    return database_driver(database_url) == "postgresql"


def get_sqlite_database_path(database_url: str | None = None) -> Path:
    url = database_url or get_database_url()
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Legacy sqlite3 access is only available when DATABASE_URL is a SQLite URL")
    raw_value = unquote(url.replace("sqlite:///", "", 1))
    if not raw_value:
        raise RuntimeError("SQLite DATABASE_URL must include a database path")
    if raw_value == ":memory:":
        return Path(":memory:")
    path = Path(raw_value)
    return path if path.is_absolute() else path.resolve()
