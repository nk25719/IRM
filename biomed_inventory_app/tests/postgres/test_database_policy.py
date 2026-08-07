import os
import unittest

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config.database import get_database_url, is_postgresql_database, is_sqlite_database
from app.database import build_engine


class PostgreSQLDatabasePolicyTest(unittest.TestCase):
    def test_database_url_targets_postgresql(self):
        self.assertTrue(is_postgresql_database())
        self.assertFalse(is_sqlite_database())
        self.assertTrue(get_database_url().startswith("postgresql"))

    def test_postgresql_connection_is_available(self):
        engine = build_engine(get_database_url())
        try:
            try:
                with engine.connect() as connection:
                    self.assertEqual(connection.execute(text("SELECT 1")).scalar_one(), 1)
            except OperationalError as exc:
                if os.getenv("CI"):
                    raise
                self.skipTest(f"PostgreSQL test database is not available locally: {exc}")
        finally:
            engine.dispose()
