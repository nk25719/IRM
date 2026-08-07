from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.database import DATA_DIR, get_database_url, is_postgresql_database

DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = get_database_url()


def _engine_kwargs(url: str) -> dict:
    if not is_postgresql_database(url):
        raise RuntimeError("Only PostgreSQL SQLAlchemy DATABASE_URL values are supported.")
    kwargs = {"future": True, "pool_pre_ping": True}
    kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    return kwargs


def build_engine(database_url: str):
    return create_engine(database_url, **_engine_kwargs(database_url))


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
