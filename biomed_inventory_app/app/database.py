from contextlib import contextmanager
from threading import RLock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.database import DATA_DIR, get_database_url, is_postgresql_database

DATA_DIR.mkdir(exist_ok=True)
Base = declarative_base()


def _engine_kwargs(url: str) -> dict:
    if not is_postgresql_database(url):
        raise RuntimeError("Only PostgreSQL SQLAlchemy DATABASE_URL values are supported.")
    kwargs = {"future": True, "pool_pre_ping": True}
    kwargs.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    return kwargs


def build_engine(database_url: str):
    return create_engine(database_url, **_engine_kwargs(database_url))


class DatabaseRuntime:
    def __init__(self):
        self._lock = RLock()
        self._database_url: str | None = None
        self._engine = None
        self._session_factory = None

    @property
    def database_url(self) -> str:
        if self._database_url is None:
            self._database_url = get_database_url()
        return self._database_url

    @property
    def engine(self):
        with self._lock:
            if self._engine is None:
                self._engine = build_engine(self.database_url)
            return self._engine

    @property
    def session_factory(self):
        with self._lock:
            if self._session_factory is None:
                self._session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
            return self._session_factory

    def configure(self, database_url: str | None = None, *, dispose_existing: bool = True):
        with self._lock:
            if dispose_existing and self._engine is not None:
                self._engine.dispose()
            self._database_url = database_url or get_database_url()
            self._engine = None
            self._session_factory = None


runtime = DatabaseRuntime()


def configure_database(database_url: str | None = None, *, dispose_existing: bool = True) -> None:
    runtime.configure(database_url, dispose_existing=dispose_existing)


def get_engine():
    return runtime.engine


def get_session_factory():
    return runtime.session_factory


class EngineProxy:
    def __getattr__(self, name: str):
        return getattr(get_engine(), name)

    def __repr__(self) -> str:
        return repr(get_engine())


class SessionLocalProxy:
    def __call__(self, *args, **kwargs):
        return get_session_factory()(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(get_session_factory(), name)


engine = EngineProxy()
SessionLocal = SessionLocalProxy()


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
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def get_database_revisions() -> list[str]:
    """Return applied Alembic revisions without changing database state."""
    with get_engine().connect() as connection:
        result = connection.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
        return [str(version) for version in result.scalars().all()]


def check_database_schema_current() -> bool:
    return bool(get_database_revisions())
