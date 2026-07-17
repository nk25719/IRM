import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config.database import get_database_url, get_sqlite_database_path, is_sqlite_database
from app.database import Base, build_engine
from app.erp_models import Client, Department, Equipment, EquipmentModel, User
from app.models.foundation import AuditEvent, DataValidationError, EquipmentCategoryAlias, ImportBatch, ImportRow, ManufacturerAlias, StatusHistory
from app.routers.master_data_api import create_manufacturer, get_manufacturer, list_manufacturers
from app.schemas.master_data import ManufacturerCreate
from app.services.audit_service import AuditEventService, StatusHistoryService
from app.services.base import DuplicateRecordError, ServiceError
from app.services.client_site_service import ClientSiteService
from app.services.import_service import DataValidationErrorService, ImportBatchService, ImportRowService
from app.services.location_service import EquipmentCategoryAliasService, EquipmentCategoryService, LocationService
from app.services.manufacturer_service import ManufacturerAliasService, ManufacturerService
from app.services.supplier_service import SupplierService


class DatabaseFoundationTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.url = f"sqlite:///{self.db_path}"
        self.engine = build_engine(self.url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()
        self.client = Client(name="Hospital A")
        self.department = Department(client_id=1, name="ICU")
        self.equipment = Equipment(client_id=1, name="Monitor A")
        self.user = User(username="admin")
        self.db.add_all([self.client, self.department, self.equipment, self.user])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_equipment_model_master_data_columns_remain_present(self):
        columns = {column["name"] for column in inspect(self.engine).get_columns("equipment_models")}
        self.assertIn("manufacturer_id", columns)
        self.assertIn("equipment_category_id", columns)

    def test_manufacturer_creation_duplicate_and_soft_delete(self):
        service = ManufacturerService(self.db)
        created = service.create({"code": "GE", "name": "GE Healthcare"})
        self.assertEqual(created.normalized_name, "ge healthcare")
        with self.assertRaises(DuplicateRecordError):
            service.create({"code": "GE", "name": "Another GE"})
        deleted = service.soft_delete(created.id)
        self.assertTrue(deleted.is_deleted)
        self.assertEqual(service.list(), [])
        restored = service.restore(created.id)
        self.assertFalse(restored.is_deleted)

    def test_duplicate_manufacturer_name_case_difference_and_rollback(self):
        service = ManufacturerService(self.db)
        service.create({"code": "GE", "name": "GE Healthcare"})
        with self.assertRaises(DuplicateRecordError):
            service.create({"code": "GE2", "name": "ge healthcare"})
        supplier = SupplierService(self.db).create({"supplier_code": "SUP-ROLLBACK", "name": "Supplier After Rollback"})
        self.assertEqual(supplier.name, "Supplier After Rollback")

    def test_supplier_creation(self):
        supplier = SupplierService(self.db).create({"supplier_code": "SUP-1", "name": "Supplier One"})
        self.assertEqual(supplier.supplier_code, "SUP-1")

    def test_client_site_and_nested_location(self):
        site = ClientSiteService(self.db).create({"client_id": self.client.id, "site_code": "MAIN", "name": "Main Campus"})
        parent = LocationService(self.db).create({"client_id": self.client.id, "site_id": site.id, "location_code": "B1", "name": "Building 1"})
        child = LocationService(self.db).create(
            {"client_id": self.client.id, "site_id": site.id, "parent_location_id": parent.id, "location_code": "ICU-1", "name": "ICU Room 1"}
        )
        self.assertEqual(child.parent_location_id, parent.id)

    def test_primary_client_site_and_self_parent_validation(self):
        service = ClientSiteService(self.db)
        service.create({"client_id": self.client.id, "site_code": "MAIN", "name": "Main Campus", "is_primary": True})
        with self.assertRaises(DuplicateRecordError):
            service.create({"client_id": self.client.id, "site_code": "BRANCH", "name": "Branch", "is_primary": True})

        location = LocationService(self.db).create({"client_id": self.client.id, "location_code": "LOC-1", "name": "Location 1"})
        with self.assertRaises(ServiceError):
            LocationService(self.db).update(location.id, {"parent_location_id": location.id})

    def test_equipment_category_hierarchy(self):
        service = EquipmentCategoryService(self.db)
        parent = service.create({"code": "IMAGING", "name": "Imaging"})
        child = service.create({"code": "XRAY", "name": "X-Ray", "parent_category_id": parent.id})
        self.assertEqual(child.parent_category_id, parent.id)
        with self.assertRaises(ServiceError):
            service.update(parent.id, {"parent_category_id": parent.id})

    def test_verified_alias_lookup_and_duplicate_protection(self):
        manufacturer = ManufacturerService(self.db).create({"code": "GE", "name": "GE Healthcare"})
        alias_service = ManufacturerAliasService(self.db)
        alias = alias_service.create({"manufacturer_id": manufacturer.id, "alias": "G.E. Healthcare", "is_verified": True, "confidence": 95})
        self.assertEqual(alias.normalized_alias, "g.e. healthcare")
        self.assertEqual(alias_service.find_verified("  G.E.   Healthcare ").manufacturer_id, manufacturer.id)
        with self.assertRaises(DuplicateRecordError):
            alias_service.create({"manufacturer_id": manufacturer.id, "alias": "g.e. healthcare"})
        with self.assertRaises(ServiceError):
            alias_service.soft_delete(alias.id)

    def test_category_alias_lookup(self):
        category = EquipmentCategoryService(self.db).create({"code": "MONITOR", "name": "Patient Monitor"})
        alias = EquipmentCategoryAliasService(self.db).create(
            {"equipment_category_id": category.id, "alias": "Monitor", "is_verified": True, "confidence": 90}
        )
        self.assertEqual(alias.normalized_alias, "monitor")
        self.assertEqual(EquipmentCategoryAliasService(self.db).find_verified("monitor").equipment_category_id, category.id)

    def test_import_batch_row_and_validation_error(self):
        batch = ImportBatchService(self.db).create({"source_type": "excel", "source_filename": "assets.xlsx", "total_rows": 1})
        row = ImportRowService(self.db).create({"import_batch_id": batch.id, "row_number": 1, "raw_data": {"Serial": "SN-1"}})
        error = DataValidationErrorService(self.db).create(
            {"import_batch_id": batch.id, "import_row_id": row.id, "error_code": "missing_model", "error_message": "Model is required"}
        )
        self.assertEqual(error.severity, "error")
        self.db.refresh(row)
        self.assertEqual(row.raw_data, {"Serial": "SN-1"})
        with self.assertRaises(DuplicateRecordError):
            ImportRowService(self.db).create({"import_batch_id": batch.id, "row_number": 1})

    def test_audit_event_and_status_history_are_append_only(self):
        audit = AuditEventService(self.db).create(
            {"event_type": "create", "entity_type": "manufacturer", "entity_id": "1", "new_values": {"name": "GE"}}
        )
        history = StatusHistoryService(self.db).create(
            {"entity_type": "service_case", "entity_id": "1", "previous_status": "open", "new_status": "closed"}
        )
        self.assertIsNotNone(audit.id)
        self.assertIsNotNone(history.id)
        with self.assertRaises(ServiceError):
            AuditEventService(self.db).update(audit.id, {"event_type": "update"})
        with self.assertRaises(ServiceError):
            StatusHistoryService(self.db).create({"entity_type": "service_case", "entity_id": "1", "previous_status": "open", "new_status": "open"})

    def test_api_404_409_and_pagination_shape(self):
        with self.assertRaises(HTTPException) as missing:
            get_manufacturer(999, db=self.db)
        self.assertEqual(missing.exception.status_code, 404)

        create_manufacturer(ManufacturerCreate(code="GE", name="GE Healthcare"), db=self.db)
        with self.assertRaises(HTTPException) as duplicate:
            create_manufacturer(ManufacturerCreate(code="GE2", name="ge healthcare"), db=self.db)
        self.assertEqual(duplicate.exception.status_code, 409)
        page = list_manufacturers(limit=1, offset=0, db=self.db)
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["total"], 1)

    def test_metadata_registration_contains_existing_and_foundation_tables(self):
        expected = {
            "clients",
            "equipment",
            "manufacturers",
            "suppliers",
            "client_sites",
            "locations",
            "equipment_categories",
            "import_batches",
            "import_rows",
            "data_validation_errors",
            "audit_events",
            "status_history",
        }
        self.assertTrue(expected.issubset(set(Base.metadata.tables)))
        self.assertIs(Base.metadata.tables["clients"].metadata, Base.metadata.tables["manufacturers"].metadata)


class AlembicFoundationTest(unittest.TestCase):
    def test_alembic_upgrade_and_downgrade_on_disposable_database(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(db_path)
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        try:
            upgrade = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr + upgrade.stdout)
            downgrade = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "-1"], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
            self.assertEqual(downgrade.returncode, 0, downgrade.stderr + downgrade.stdout)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_import_batches_old_row_survives_upgrade_and_new_columns_downgrade(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(db_path)
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        root = Path(__file__).resolve().parents[1]
        try:
            base = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "20260709_aftermarket_service_reports"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(base.returncode, 0, base.stderr + base.stdout)
            engine = build_engine(env["DATABASE_URL"])
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO import_batches (import_type, target_table, filename, status, total_rows, valid_rows, error_rows, saved_rows, created_by, mapping_json) "
                        "VALUES ('legacy', 'clients', 'legacy.xlsx', 'preview', 7, 6, 1, 0, 'admin', '{\"a\":\"b\"}')"
                    )
                )
            engine.dispose()

            upgrade = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(upgrade.returncode, 0, upgrade.stderr + upgrade.stdout)
            engine = build_engine(env["DATABASE_URL"])
            with engine.connect() as conn:
                row = conn.execute(text("SELECT import_type, target_table, filename, status, total_rows, valid_rows, error_rows, saved_rows, created_by, mapping_json FROM import_batches WHERE filename='legacy.xlsx'")).mappings().one()
                self.assertEqual(row["import_type"], "legacy")
                self.assertEqual(row["target_table"], "clients")
                self.assertEqual(row["total_rows"], 7)
                self.assertIn("source_filename", [c["name"] for c in inspect(conn).get_columns("import_batches")])
                with self.assertRaises(IntegrityError):
                    conn.execute(text("INSERT INTO equipment_models (manufacturer_id, model) VALUES (999, 'Ghost')"))
            engine.dispose()

            downgrade = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "20260709_aftermarket_service_reports"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(downgrade.returncode, 0, downgrade.stderr + downgrade.stdout)
            engine = build_engine(env["DATABASE_URL"])
            with engine.connect() as conn:
                columns = [c["name"] for c in inspect(conn).get_columns("import_batches")]
                self.assertIn("filename", columns)
                self.assertNotIn("source_filename", columns)
                row = conn.execute(text("SELECT filename, status, total_rows FROM import_batches WHERE filename='legacy.xlsx'")).mappings().one()
                self.assertEqual(row["status"], "preview")
            engine.dispose()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class DatabaseConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.old_database_url = os.environ.get("DATABASE_URL")
        self.old_db_path = os.environ.get("DB_PATH")

    def tearDown(self):
        if self.old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.old_database_url
        if self.old_db_path is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self.old_db_path

    def test_database_url_and_legacy_path_share_sqlite_location(self):
        os.environ.pop("DATABASE_URL", None)
        os.environ["DB_PATH"] = "./tmp/test-shared.db"
        self.assertTrue(is_sqlite_database())
        self.assertEqual(get_database_url(), "sqlite:///./tmp/test-shared.db")
        self.assertEqual(get_sqlite_database_path(), Path("./tmp/test-shared.db").resolve())

    def test_relative_and_absolute_sqlite_urls_resolve(self):
        os.environ["DATABASE_URL"] = "sqlite:///./app/data/relative-test.db"
        self.assertEqual(get_sqlite_database_path(), Path("./app/data/relative-test.db").resolve())
        absolute = Path(tempfile.gettempdir()) / "absolute-test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{absolute}"
        self.assertEqual(get_sqlite_database_path(), absolute)

    def test_postgresql_url_rejects_legacy_sqlite_path(self):
        os.environ["DATABASE_URL"] = "postgresql+psycopg://irm_user:change_me@db:5432/irm"
        self.assertFalse(is_sqlite_database())
        with self.assertRaises(RuntimeError):
            get_sqlite_database_path()


class ApplicationRouteSmokeTest(unittest.TestCase):
    def test_existing_application_startup_and_routes_remain_registered(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(db_path)
        old_db_path = os.environ.get("DB_PATH")
        old_database_url = os.environ.get("DATABASE_URL")
        os.environ["DB_PATH"] = db_path
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        try:
            import importlib
            import app.database as database
            import app.main as main

            importlib.reload(database)
            main = importlib.reload(main)
            main.init_db()
            paths = {route.path for route in main.app.routes if hasattr(route, "path")}
            self.assertIn("/", paths)
            self.assertIn("/api/erp/dashboard/summary", paths)
            self.assertIn("/api/master-data/manufacturers", paths)
            self.assertIn("/api/imports/batches", paths)
        finally:
            if old_db_path is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = old_db_path
            if old_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_database_url
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
