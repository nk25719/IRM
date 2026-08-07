import unittest

from app.database import configure_database, get_engine


class DatabaseRuntimeTest(unittest.TestCase):
    def tearDown(self):
        configure_database()

    def test_configure_database_replaces_lazy_engine_url(self):
        first_url = "postgresql+psycopg2://irm:first@localhost:5432/irm_first"
        second_url = "postgresql+psycopg2://irm:second@localhost:5432/irm_second"

        configure_database(first_url)
        first_engine = get_engine()
        self.assertEqual(first_engine.url.database, "irm_first")

        configure_database(second_url)
        second_engine = get_engine()
        self.assertEqual(second_engine.url.database, "irm_second")
        self.assertIsNot(first_engine, second_engine)
