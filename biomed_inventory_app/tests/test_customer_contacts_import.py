import io
import os
import tempfile
import types
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy.orm import sessionmaker

from app.database import Base, build_engine
from app.erp_models import Client, Contact, OrganizationDomainMapping, User
from app.models.foundation import AuditEvent, DataValidationError, ImportBatch, ImportRow, Manufacturer, Supplier
from app.routers.customer_contacts_api import _require_manage
from app.services.customer_contacts_import_service import CustomerContactsImportService, engagement_level, normalize_email


class CustomerContactsImportTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = build_engine(f"sqlite:///{self.db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()
        self.user = User(username="admin", role="admin")
        self.client = Client(name="Example Hospital")
        self.manufacturer = Manufacturer(code="GE", name="GE HealthCare", normalized_name="ge healthcare")
        self.supplier = Supplier(supplier_code="SUP-1", name="Medical Supplier")
        self.db.add_all([self.user, self.client, self.manufacturer, self.supplier])
        self.db.commit()
        for row in [self.user, self.client, self.manufacturer, self.supplier]:
            self.db.refresh(row)
        self.db.add(OrganizationDomainMapping(domain="examplehospital.com", organization_type="client", organization_id=self.client.id))
        self.existing = Contact(client_id=self.client.id, name="Existing Person", display_name="Existing Person", email="existing@examplehospital.com", normalized_email="existing@examplehospital.com", phone="+9611000", phone_verified=True, emails_exchanged=4, engagement_level="moderate", organization_type="client", data_quality_status="complete")
        self.db.add(self.existing)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def workbook_bytes(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Customer Contacts"
        ws.append(["Name", "Email", "Company / Domain", "Emails Exchanged", "Role", "Phone", "Notes"])
        ws.append(["examplehospital.com", "", "examplehospital.com", "", "", "", ""])
        ws.append(["Jane Example", " Jane@ExampleHospital.COM ", "examplehospital.com", 12, "", "+961 1 234 567", ""])
        ws.append(["VIP Doctor", "vip@examplehospital.com", "examplehospital.com", 40, "Chief", "", ""])
        ws.append(["Purchasing", "purchasing@examplehospital.com", "examplehospital.com", 35, "", "", ""])
        ws.append(["Learning Notifications", "learning.notifications@examplehospital.com", "examplehospital.com", 4, "", "", ""])
        ws.append(["Personal Person", "person@gmail.com", "gmail.com", 7, "", "", ""])
        ws.append(["Unmatched Hospital", "bio@newhospital.org", "newhospital.org", 5, "", "", ""])
        ws.append(["Existing Person", "existing@examplehospital.com", "examplehospital.com", 9, "", "+9619999", ""])
        ws.append(["Bad Email", "not an email", "bad", 1, "", "", ""])
        stream = io.BytesIO()
        wb.save(stream)
        return stream.getvalue()

    def preview(self):
        return CustomerContactsImportService(self.db, self.user.id).preview(self.workbook_bytes(), "Customer_Contacts-2.xlsx")

    def test_grouping_rows_skipped_and_valid_contacts_staged(self):
        preview = self.preview()
        self.assertEqual(preview["metrics"]["skipped_group_rows"], 1)
        self.assertGreaterEqual(preview["metrics"]["contacts"], 7)
        self.assertEqual(self.db.query(ImportBatch).count(), 1)
        self.assertEqual(self.db.query(ImportRow).filter_by(processing_status="skipped").count(), 1)

    def test_invalid_email_rejected_and_normalized_email(self):
        preview = self.preview()
        bad = next(row for row in preview["rows"] if row.get("display_name") == "Bad Email")
        jane = next(row for row in preview["rows"] if row.get("display_name") == "Jane Example")
        self.assertEqual(bad["import_status"], "error")
        self.assertEqual(jane["email"], "jane@examplehospital.com")
        self.assertGreater(self.db.query(DataValidationError).filter_by(error_code="invalid_email").count(), 0)

    def test_duplicate_email_updates_existing_without_overwriting_verified_phone(self):
        preview = self.preview()
        result = CustomerContactsImportService(self.db, self.user.id).confirm(preview["import_id"])
        self.assertGreaterEqual(result["updated"], 1)
        contact = self.db.query(Contact).filter_by(normalized_email="existing@examplehospital.com").one()
        self.assertEqual(contact.phone, "+9611000")
        self.assertEqual(contact.emails_exchanged, 9)

    def test_business_domain_matching_and_public_domain_review(self):
        preview = self.preview()
        jane = next(row for row in preview["rows"] if row.get("email") == "jane@examplehospital.com")
        gmail = next(row for row in preview["rows"] if row.get("email") == "person@gmail.com")
        unmatched = next(row for row in preview["rows"] if row.get("email") == "bio@newhospital.org")
        self.assertEqual(jane["client_id"], self.client.id)
        self.assertEqual(gmail["organization_type"], "personal")
        self.assertEqual(unmatched["data_quality_status"], "needs_organization_match")

    def test_shared_and_automated_detection(self):
        preview = self.preview()
        purchasing = next(row for row in preview["rows"] if row.get("email") == "purchasing@examplehospital.com")
        automated = next(row for row in preview["rows"] if row.get("email") == "learning.notifications@examplehospital.com")
        self.assertTrue(purchasing["is_shared_inbox"])
        self.assertTrue(automated["is_automated_address"])

    def test_missing_phone_and_role_handling_and_engagement(self):
        preview = self.preview()
        vip = next(row for row in preview["rows"] if row.get("email") == "vip@examplehospital.com")
        self.assertEqual(vip["engagement_level"], "high")
        self.assertEqual(engagement_level(2), "low")
        self.assertEqual(engagement_level(9), "moderate")
        self.assertIn("Phone is missing", " ".join(vip["validation_messages"]))

    def test_transaction_rollback_on_import_failure(self):
        preview = self.preview()
        service = CustomerContactsImportService(self.db, self.user.id)
        with patch.object(service, "upsert_contact", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                service.confirm(preview["import_id"])
        self.assertEqual(self.db.query(Contact).filter(Contact.normalized_email == "jane@examplehospital.com").count(), 0)

    def test_import_permission_enforcement(self):
        request = types.SimpleNamespace(session={"role": "viewer"})
        with self.assertRaises(HTTPException):
            _require_manage(request)

    def test_audit_event_creation(self):
        preview = self.preview()
        CustomerContactsImportService(self.db, self.user.id).confirm(preview["import_id"])
        event_types = {row.event_type for row in self.db.query(AuditEvent).all()}
        self.assertIn("customer_contacts_preview_generated", event_types)
        self.assertIn("customer_contacts_import_confirmed", event_types)

    def test_email_normalization(self):
        self.assertEqual(normalize_email(" Jane@Example.COM "), "jane@example.com")


if __name__ == "__main__":
    unittest.main()
