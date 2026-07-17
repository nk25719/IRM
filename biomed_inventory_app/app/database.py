from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.database import DATA_DIR, database_driver, get_database_url

DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = get_database_url()


def _engine_kwargs(url: str) -> dict:
    driver = database_driver(url)
    kwargs = {"future": True, "pool_pre_ping": True}
    if driver == "sqlite":
        kwargs["connect_args"] = {"check_same_thread": False}
    elif driver == "postgresql":
        kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    return kwargs


def build_engine(database_url: str):
    engine_ = create_engine(database_url, **_engine_kwargs(database_url))
    if database_driver(database_url) == "sqlite":
        @event.listens_for(engine_, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine_


engine = build_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_health() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
