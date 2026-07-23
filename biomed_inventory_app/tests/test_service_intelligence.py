import unittest
from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.erp_models import Case, Client, CustomerServiceContract, Equipment, ManufacturerAgreement, ManufacturerAgreementEquipment, PMTask, ServiceOpportunity
from app.models.foundation import ClientSite
from app.services.service_intelligence import (
    LIFECYCLE_CONTRACTED,
    LIFECYCLE_EXPIRED,
    LIFECYCLE_EXPIRING,
    LIFECYCLE_UNKNOWN,
    LIFECYCLE_UNDER_WARRANTY,
    MANUFACTURER_OPPORTUNITY_TYPES,
    ServiceIntelligenceService,
    opportunity_domain,
    normalize_serial,
)
from app.data_management.template_registry import get_dataset


class ServiceIntelligenceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.today = date(2026, 7, 23)
        self.client = Client(name="Hospital A")
        self.db.add(self.client)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def equipment(self, **values):
        payload = {
            "client_id": self.client.id,
            "name": "Ventilator",
            "manufacturer": "GE",
            "model": "V100",
            "serial_number": "SN-1",
            "installation_date": self.today - timedelta(days=365 * 9),
        }
        payload.update(values)
        equipment = Equipment(**payload)
        self.db.add(equipment)
        self.db.commit()
        return equipment

    def service(self):
        return ServiceIntelligenceService(self.db, today=self.today)

    def test_active_contract_takes_precedence_over_expiring_warranty(self):
        equipment = self.equipment(warranty_end_date=self.today + timedelta(days=30))
        self.db.add(CustomerServiceContract(client_id=self.client.id, contract_number="CT-1", start_date=self.today, end_date=self.today, status="active"))
        self.db.commit()

        evaluation = self.service().evaluate_equipment(equipment)

        self.assertEqual(evaluation.lifecycle_status, LIFECYCLE_CONTRACTED)

    def test_warranty_date_boundaries(self):
        cases = [
            (self.today, LIFECYCLE_EXPIRING),
            (self.today + timedelta(days=90), LIFECYCLE_EXPIRING),
            (self.today + timedelta(days=180), LIFECYCLE_EXPIRING),
            (self.today + timedelta(days=181), LIFECYCLE_UNDER_WARRANTY),
            (self.today - timedelta(days=1), LIFECYCLE_EXPIRED),
            (None, LIFECYCLE_UNKNOWN),
        ]
        for warranty_end, expected in cases:
            with self.subTest(warranty_end=warranty_end):
                equipment = self.equipment(serial_number=f"SN-{warranty_end}", warranty_end_date=warranty_end)
                self.assertEqual(self.service().classify(equipment), expected)

    def test_score_priority_and_pm_case_signals(self):
        equipment = self.equipment(warranty_end_date=self.today - timedelta(days=1), next_pm_date=self.today - timedelta(days=2))
        self.db.add(Case(client_id=self.client.id, equipment_id=equipment.id, parent_case_reference="AS-1", case_type="corrective", title="Repair", status="open"))
        self.db.commit()

        evaluation = self.service().evaluate_equipment(equipment)

        self.assertGreaterEqual(evaluation.score, 80)
        self.assertEqual(evaluation.priority, "HIGH")
        self.assertIn("Warranty expired", evaluation.score_reasons)
        self.assertTrue(evaluation.pm_overdue)

    def test_refresh_is_idempotent_and_preserves_won_history(self):
        equipment = self.equipment(warranty_end_date=self.today - timedelta(days=1))
        first = self.service().refresh()
        second = self.service().refresh()
        opportunity = self.db.query(ServiceOpportunity).filter(ServiceOpportunity.opportunity_type == "NEW_SERVICE_CONTRACT").one()
        opportunity.status = "WON"
        self.db.commit()
        third = self.service().refresh()

        self.assertEqual(first["opportunities_created"], 2)
        self.assertEqual(second["opportunities_created"], 0)
        self.assertEqual(second["opportunities_updated"], 2)
        self.assertEqual(third["opportunities_created"], 1)
        self.assertEqual(self.db.query(ServiceOpportunity).filter(ServiceOpportunity.status == "WON").count(), 1)

    def test_normalize_serial_preserves_safe_matching_key(self):
        self.assertEqual(normalize_serial(" ab  12\tcd "), "AB12CD")

    def test_summary_separates_under_warranty_from_expiring(self):
        self.equipment(serial_number="ACTIVE", warranty_end_date=self.today + timedelta(days=240))
        self.equipment(serial_number="EXPIRING", warranty_end_date=self.today + timedelta(days=90))
        self.equipment(serial_number="EXPIRED", warranty_end_date=self.today - timedelta(days=1))

        summary = self.service().summary()

        self.assertEqual(summary["under_warranty_equipment_without_contract"], 1)
        self.assertEqual(summary["warranties_expiring_within_90_days"], 1)
        self.assertEqual(summary["out_of_warranty_equipment_without_contract"], 1)

    def test_required_upload_templates_are_registered(self):
        expected = {
            "service_intelligence_installed_equipment": ("installed_equipment_import_template.xlsx", "Contract Intelligence / Manufacturer Coverage"),
            "service_intelligence_equipment_warranty": ("equipment_warranty_import_template.xlsx", "Contract Intelligence / Manufacturer Coverage"),
            "manufacturer_agreements": ("manufacturer_agreements_import_template.xlsx", "Contract Intelligence / Manufacturer Coverage"),
            "manufacturer_covered_equipment": ("manufacturer_covered_equipment_import_template.xlsx", "Contract Intelligence / Manufacturer Coverage"),
            "manufacturer_eosl_data": ("manufacturer_eosl_import_template.xlsx", "Contract Intelligence / Manufacturer Coverage"),
            "service_intelligence_service_contracts": ("service_contracts_import_template.xlsx", "Contract Intelligence / Customer Contracts"),
            "service_intelligence_contract_equipment": ("contract_equipment_import_template.xlsx", "Contract Intelligence / Customer Contracts"),
            "service_intelligence_pm_history": ("preventive_maintenance_import_template.xlsx", "Contract Intelligence / Customer Contracts"),
            "service_intelligence_service_opportunities": ("service_opportunities_import_template.xlsx", "Contract Intelligence / Customer Contracts"),
        }
        for dataset_key, (filename, domain) in expected.items():
            with self.subTest(dataset_key=dataset_key):
                dataset = get_dataset(dataset_key)
                self.assertEqual(dataset.domain, domain)
                self.assertEqual(dataset.template_filename, filename)
                self.assertTrue(dataset.import_supported)
                self.assertGreater(len(dataset.required_fields), 0)

    def test_manufacturer_coverage_does_not_create_customer_contract_coverage(self):
        equipment = self.equipment(warranty_end_date=self.today + timedelta(days=30))
        agreement = ManufacturerAgreement(manufacturer="GE", agreement_number="GE-1", start_date=self.today, end_date=self.today + timedelta(days=365), status="active")
        self.db.add(agreement)
        self.db.flush()
        self.db.add(ManufacturerAgreementEquipment(manufacturer_agreement_id=agreement.id, equipment_id=equipment.id, serial_number=equipment.serial_number, coverage_start_date=self.today, coverage_end_date=self.today + timedelta(days=365), coverage_status="active"))
        self.db.commit()

        summary = self.service().equipment_summary(equipment.id)

        self.assertEqual(self.service().classify(equipment), LIFECYCLE_EXPIRING)
        self.assertEqual(summary["manufacturer_coverage"]["coverage_status"], "active")
        self.assertEqual(summary["customer_service_contract"]["contract_status"], "not_contracted")

    def test_customer_contract_does_not_create_manufacturer_coverage(self):
        equipment = self.equipment(warranty_end_date=self.today + timedelta(days=30))
        self.db.add(CustomerServiceContract(client_id=self.client.id, contract_number="CUST-1", start_date=self.today, end_date=self.today + timedelta(days=365), status="active", coverage_type="FULL_SERVICE"))
        self.db.commit()

        summary = self.service().equipment_summary(equipment.id)

        self.assertEqual(self.service().classify(equipment), LIFECYCLE_CONTRACTED)
        self.assertEqual(summary["customer_service_contract"]["contract_status"], "active")
        self.assertEqual(summary["manufacturer_coverage"]["coverage_status"], "not_covered")

    def test_unified_refresh_creates_manufacturer_and_customer_opportunities(self):
        equipment = self.equipment(warranty_end_date=self.today - timedelta(days=1))

        result = self.service().refresh()
        rows = self.service().opportunity_rows({})

        self.assertEqual(result["opportunities_created"], 2)
        self.assertEqual({row["domain"] for row in rows}, {"Manufacturer", "Customer"})
        self.assertTrue(any(row["opportunity_type"] in MANUFACTURER_OPPORTUNITY_TYPES for row in rows))
        self.assertTrue(all(opportunity_domain(row["opportunity_type"]) == row["domain"] for row in rows))


if __name__ == "__main__":
    unittest.main()
