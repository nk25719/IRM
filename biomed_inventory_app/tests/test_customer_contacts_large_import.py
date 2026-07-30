import csv
import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.database import Base, build_engine
from app.erp_models import Client, Contact, CustomerContactImportJob, CustomerContactImportStaging, OrganizationDomainMapping, User
from app.models.foundation import Manufacturer, Supplier
from app.services import customer_contacts_import_service as import_service
from app.services.customer_contacts_import_service import CustomerContactsLargeImportService


class CustomerContactsLargeImportTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = build_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_storage = import_service.CONTACT_IMPORT_STORAGE
        import_service.CONTACT_IMPORT_STORAGE = Path(self.tmpdir.name)
        self.user = User(username="admin", role="admin")
        self.client = Client(name="Example Hospital")
        self.db.add_all([self.user, self.client, Manufacturer(code="GE", name="GE HealthCare", normalized_name="ge healthcare"), Supplier(supplier_code="S1", name="Supplier One")])
        self.db.commit()
        self.db.add(OrganizationDomainMapping(domain="examplehospital.com", organization_type="client", organization_id=self.client.id))
        self.db.add(Contact(name="Existing Person", email="existing@examplehospital.com", normalized_email="existing@examplehospital.com", client_id=self.client.id, organization_type="client"))
        self.db.commit()

    def tearDown(self):
        import_service.CONTACT_IMPORT_STORAGE = self.old_storage
        self.tmpdir.cleanup()
        self.db.close()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def write_csv(self, name: str, rows: int, duplicate_every: int | None = None) -> Path:
        path = Path(self.tmpdir.name) / name
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Name", "Email", "Company / Domain", "Emails Exchanged", "Role", "Phone", "Notes"])
            for index in range(rows):
                email_index = 0 if duplicate_every and index and index % duplicate_every == 0 else index
                writer.writerow([f"Person {index}", f"person{email_index}@examplehospital.com", "examplehospital.com", index % 40, "Engineer", "+96112345", ""])
        return path

    def create_job(self, path: Path):
        checksum = "test-" + path.name
        return CustomerContactsLargeImportService(self.db, self.user.id).create_upload_job_from_stored_file(path, path.name, path.stat().st_size, checksum, allow_duplicate=True)

    def test_csv_is_staged_streaming_with_paged_preview(self):
        path = self.write_csv("contacts.csv", 120)
        payload = self.create_job(path)
        service = CustomerContactsLargeImportService(self.db, self.user.id)
        service.analyse_job(payload["id"])
        rows = service.rows(payload["id"], page=2, page_size=25)
        self.assertEqual(rows["total"], 120)
        self.assertEqual(len(rows["items"]), 25)
        self.assertEqual(rows["items"][0]["source_row_number"], 27)
        self.assertEqual(self.db.query(CustomerContactImportStaging).count(), 120)

    def test_duplicate_heavy_file_marks_duplicates_without_failed_transaction(self):
        path = self.write_csv("dupes.csv", 30, duplicate_every=2)
        payload = self.create_job(path)
        service = CustomerContactsLargeImportService(self.db, self.user.id)
        service.analyse_job(payload["id"])
        job = self.db.get(CustomerContactImportJob, payload["id"])
        self.assertEqual(job.status, "awaiting_review")
        self.assertGreater(job.duplicate_rows, 0)

    def test_confirm_is_idempotent_and_imports_once(self):
        path = self.write_csv("confirm.csv", 5)
        payload = self.create_job(path)
        service = CustomerContactsLargeImportService(self.db, self.user.id)
        service.analyse_job(payload["id"])
        service.confirm_job(payload["id"], "abc")
        service.confirm_job(payload["id"], "abc")
        service.run_import_job(payload["id"])
        service.run_import_job(payload["id"])
        self.assertEqual(self.db.query(Contact).filter(Contact.email.like("person%@examplehospital.com")).count(), 5)

    def test_cancel_and_resume_between_batches(self):
        path = self.write_csv("cancel.csv", 5)
        payload = self.create_job(path)
        service = CustomerContactsLargeImportService(self.db, self.user.id)
        service.cancel(payload["id"])
        service.analyse_job(payload["id"])
        self.assertEqual(self.db.get(CustomerContactImportJob, payload["id"]).status, "cancelled")
        service.resume(payload["id"])
        service.analyse_job(payload["id"])
        self.assertEqual(self.db.get(CustomerContactImportJob, payload["id"]).status, "awaiting_review")

    @unittest.skipUnless(os.getenv("RUN_CONTACT_IMPORT_PERF_TESTS") == "1", "Set RUN_CONTACT_IMPORT_PERF_TESTS=1 for the 100k-row import coverage test")
    def test_synthetic_100k_csv_stages_in_batches(self):
        path = self.write_csv("large.csv", 100000, duplicate_every=25)
        payload = self.create_job(path)
        CustomerContactsLargeImportService(self.db, self.user.id).analyse_job(payload["id"])
        job = self.db.get(CustomerContactImportJob, payload["id"])
        self.assertEqual(job.total_rows, 100000)
        self.assertEqual(job.status, "awaiting_review")


if __name__ == "__main__":
    unittest.main()
