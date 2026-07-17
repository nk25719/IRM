import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.database import Base, build_engine
from app.erp_models import EquipmentModel
from app.models.foundation import EquipmentCategory, EquipmentCategoryAlias, Manufacturer, ManufacturerAlias
from app.schemas.common import normalized_name
from scripts import backfill_equipment_model_master_data as backfill
from scripts.seed_master_data import apply_category_seed, plan_category_seed
from scripts.master_data_utils import write_csv


class MasterDataBackfillTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = build_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_manufacturer_mapping = backfill.MANUFACTURER_MAPPING
        self.old_category_mapping = backfill.CATEGORY_MAPPING
        self.old_reconciliation = backfill.RECONCILIATION_FILE
        backfill.MANUFACTURER_MAPPING = Path(self.tempdir.name) / "manufacturer_mapping.csv"
        backfill.CATEGORY_MAPPING = Path(self.tempdir.name) / "equipment_category_mapping.csv"
        backfill.RECONCILIATION_FILE = Path(self.tempdir.name) / "reconciliation.csv"

    def tearDown(self):
        backfill.MANUFACTURER_MAPPING = self.old_manufacturer_mapping
        backfill.CATEGORY_MAPPING = self.old_category_mapping
        backfill.RECONCILIATION_FILE = self.old_reconciliation
        self.db.close()
        self.engine.dispose()
        self.tempdir.cleanup()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _manufacturer(self, code="GE", name="GE Healthcare"):
        manufacturer = Manufacturer(code=code, name=name, normalized_name=normalized_name(name), status="active")
        self.db.add(manufacturer)
        self.db.flush()
        return manufacturer

    def _category(self, code="MONITOR", name="Patient Monitor"):
        category = EquipmentCategory(code=code, name=name, normalized_name=normalized_name(name), status="active")
        self.db.add(category)
        self.db.flush()
        return category

    def _write_mappings(self, manufacturer_rows=None, category_rows=None):
        write_csv(
            backfill.MANUFACTURER_MAPPING,
            ["approved", "raw_value", "normalized_value", "canonical_code", "canonical_name", "match_action", "alias_source", "confidence", "review_notes"],
            manufacturer_rows or [],
        )
        write_csv(
            backfill.CATEGORY_MAPPING,
            [
                "approved",
                "raw_value",
                "normalized_value",
                "canonical_code",
                "canonical_name",
                "parent_code",
                "parent_name",
                "match_action",
                "alias_source",
                "confidence",
                "review_notes",
            ],
            category_rows or [],
        )

    def test_seed_master_data_is_idempotent(self):
        first_plan = plan_category_seed(self.db)
        self.assertGreater(sum(1 for row in first_plan if row["action"] == "create"), 0)
        apply_category_seed(self.db)
        second_plan = plan_category_seed(self.db)
        self.assertEqual(sum(1 for row in second_plan if row["action"] == "create"), 0)

    def test_dry_run_does_not_change_equipment_model(self):
        self._manufacturer()
        self.db.add(EquipmentModel(manufacturer="GE Healthcare", model="Dash 4000"))
        self.db.commit()
        self._write_mappings(
            manufacturer_rows=[
                {
                    "approved": "false",
                    "raw_value": "GE Healthcare",
                    "normalized_value": "ge healthcare",
                    "canonical_code": "GE",
                    "canonical_name": "GE Healthcare",
                }
            ]
        )
        reconciliation, changed = backfill.plan_backfill(self.db)
        self.assertEqual(changed, [])
        self.assertEqual(reconciliation[0]["manufacturer_action"], "skip")
        self.assertIsNone(self.db.query(EquipmentModel).one().manufacturer_id)

    def test_approved_mapping_applies_without_overwriting_existing_fk(self):
        manufacturer = self._manufacturer()
        other = self._manufacturer("PHILIPS", "Philips")
        category = self._category()
        self.db.add_all(
            [
                EquipmentModel(manufacturer="GE Healthcare", model="Monitor", manufacturer_id=None, equipment_category_id=None),
                EquipmentModel(manufacturer="GE Healthcare", model="Monitor", manufacturer_id=other.id, equipment_category_id=None),
            ]
        )
        self.db.commit()
        self._write_mappings(
            manufacturer_rows=[
                {
                    "approved": "true",
                    "raw_value": "GE Healthcare",
                    "normalized_value": "ge healthcare",
                    "canonical_code": "GE",
                    "canonical_name": "GE Healthcare",
                }
            ],
            category_rows=[
                {
                    "approved": "yes",
                    "raw_value": "Monitor",
                    "normalized_value": "monitor",
                    "canonical_code": "MONITOR",
                    "canonical_name": "Patient Monitor",
                }
            ],
        )
        with self.db.begin():
            reconciliation = backfill.apply_backfill(self.db)
        models = self.db.query(EquipmentModel).order_by(EquipmentModel.id).all()
        self.assertEqual(models[0].manufacturer_id, manufacturer.id)
        self.assertEqual(models[0].equipment_category_id, category.id)
        self.assertEqual(models[1].manufacturer_id, other.id)
        self.assertTrue(any(row["manufacturer_action"] == "blocked_existing_fk" for row in reconciliation))

    def test_verified_alias_can_match_when_mapping_is_absent(self):
        manufacturer = self._manufacturer()
        category = self._category()
        self.db.add(ManufacturerAlias(manufacturer_id=manufacturer.id, alias="GEHC", normalized_alias="gehc", is_verified=True, confidence=90))
        self.db.add(EquipmentCategoryAlias(equipment_category_id=category.id, alias="mon", normalized_alias="mon", is_verified=True, confidence=90))
        self.db.add(EquipmentModel(manufacturer="GEHC", model="mon"))
        self.db.commit()
        self._write_mappings()
        with self.db.begin():
            backfill.apply_backfill(self.db)
        model = self.db.query(EquipmentModel).one()
        self.assertEqual(model.manufacturer_id, manufacturer.id)
        self.assertEqual(model.equipment_category_id, category.id)

    def test_unverified_alias_is_unresolved(self):
        manufacturer = self._manufacturer()
        self.db.add(ManufacturerAlias(manufacturer_id=manufacturer.id, alias="GEHC", normalized_alias="gehc", is_verified=False, confidence=40))
        self.db.add(EquipmentModel(manufacturer="GEHC", model="Monitor"))
        self.db.commit()
        self._write_mappings()
        reconciliation, changed = backfill.plan_backfill(self.db)
        self.assertEqual(changed, [])
        self.assertEqual(reconciliation[0]["manufacturer_reason"], "unapproved or unresolved")


if __name__ == "__main__":
    unittest.main()
