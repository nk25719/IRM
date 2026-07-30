import io
import os
import tempfile
import unittest
from zipfile import ZipFile

from openpyxl import Workbook

from app.quotation_api import QuotationAIDraftRequest, QuotationEquipmentGroupIn, QuotationIn, QuotationItemIn, approve_quotation, ai_create_draft, connect, create_quotation, submit_review
from app.quotation_ai_service import QuotationAIService, QuotationContext, RuleBasedQuotationExtractionProvider
from app.quotation_export import build_excel, build_pdf, calculate_totals
from app.quotation_import_service import parse_excel_bytes

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


class QuotationGeneratorTest(unittest.TestCase):
    def pdf_text(self, content: bytes) -> str:
        if PdfReader is None:
            self.skipTest("pypdf is not installed in this interpreter")
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def test_quotation_calculation(self):
        totals = calculate_totals(
            [
                {"quantity": 2, "unit_price": 100, "discount_percent": 10},
                {"quantity": 1, "unit_price": 50, "discount_percent": 0},
            ],
            discount_amount=20,
            vat_rate=11,
        )
        self.assertEqual(totals["subtotal"], 230)
        self.assertEqual(totals["discount_amount"], 20)
        self.assertEqual(totals["vat_amount"], 23.1)
        self.assertEqual(totals["total_amount"], 233.1)

    def test_excel_import_mapping_messy_columns(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["part", "item", "qty", "unit price", "discount %", "delivery"])
        ws.append(["ECG-001", "ECG trunk cable", 3, 25.5, 5, "2 weeks"])
        buf = io.BytesIO()
        wb.save(buf)

        items = parse_excel_bytes(buf.getvalue())

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_code"], "ECG-001")
        self.assertEqual(items[0]["description"], "ECG trunk cable")
        self.assertEqual(items[0]["quantity"], 3)
        self.assertEqual(items[0]["unit_price"], 25.5)
        self.assertEqual(items[0]["delivery_time"], "2 weeks")

    def test_ai_validation_fallback_suggests_match_and_does_not_change_description(self):
        item = {"item_code": "ECG-001", "description": "Trunk cable", "quantity": 1, "unit_price": 10}
        inventory = [{"id": 7, "pn": "ECG-001", "description": "ECG trunk cable", "manufacturer": "GE"}]

        result = QuotationAIService().validate_items([item], inventory)[0]

        self.assertEqual(result["inventory_item_id"], 7)
        self.assertEqual(result["ai_validation_status"], "ok")
        self.assertEqual(result["description"], "Trunk cable")
        self.assertIn("ECG-001", result["ai_normalized_description"])

    def test_ai_extraction_returns_strict_editable_draft_schema_without_inventing_reference(self):
        text = "Hotel Dieu anesthesia machine has a problem with the flow sensor. Engineer found the sensor defective. Need 2 hours labour and one flow sensor part number 12345. Sensor price 450 dollars and labour 100. Warranty three months."

        result = RuleBasedQuotationExtractionProvider().extract_quotation_sync(text, QuotationContext(client_id=1, client_name="Hotel Dieu", preferred_currency="USD"))

        self.assertEqual(result.client.id, 1)
        self.assertEqual(result.items[0].part_number, "12345")
        self.assertEqual(result.items[0].unit_price, 450)
        self.assertEqual(result.labour[0].hours, 2)
        self.assertIn("review", " ".join(result.warnings).lower())
        self.assertIsNone(result.references.customer_reference)

    def test_excel_export_generation(self):
        content = build_excel(
            {"quotation_number": "QT-TEST-001", "client_id": 1, "currency": "USD", "vat_rate": 11},
            [{"item_code": "PN-1", "description": "Cable", "quantity": 2, "unit_price": 10, "discount_percent": 0}],
            {"name": "Hospital A"},
        )

        self.assertTrue(content.startswith(b"PK"))
        with ZipFile(io.BytesIO(content)) as archive:
            self.assertIn("xl/workbook.xml", archive.namelist())

    def test_pdf_export_generation(self):
        content = build_pdf(
            {"quotation_number": "QT-TEST-001", "client_id": 1, "currency": "USD", "vat_rate": 0},
            [{"item_code": "PN-1", "description": "Cable", "quantity": 1, "unit_price": 10, "line_total": 10}],
            {"name": "Hospital A"},
        )

        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 100)

    def test_cmm_pdf_contains_template_tokens_totals_footer_and_draft_watermark(self):
        content = build_pdf(
            {"quotation_number": "HMC-SRV-1 / 14867", "client_id": 1, "currency": "USD", "vat_rate": 11, "status": "draft", "payment_terms": "Cash in Advance", "footer_form_code": "CMM-SA-F-04-03-Edition01"},
            [
                {"item_code": "FLOW-123", "description": "Defective flow sensor replacement with a long wrapped description for line-height testing.", "quantity": 1, "unit_price": 450, "discount_percent": 0, "item_type": "spare_part"},
                {"item_code": "CMM-LabA", "description": "Corrective maintenance labour", "quantity": 2, "unit_price": 100, "discount_percent": 0, "item_type": "labor"},
            ],
            {"name": "Hamidi Medical Center"},
            [{"equipment_name": "ANESTHESIA MACHINE", "serial_number": "ABC123", "service_report_number": "4-14867"}],
        )
        text = self.pdf_text(content)

        self.assertIn("DRAFT", text)
        self.assertIn("Financial Offer", text)
        self.assertIn("HMC-SRV-1 / 14867", text)
        self.assertIn("Hamidi Medical Center", text)
        self.assertIn("TOTAL BEFORE VAT", text)
        self.assertIn("11% VAT", text)
        self.assertIn("721.50", text)
        self.assertIn("CMM-SA-F-04-03-Edition01", text)
        self.assertIn("Page 1 of", text)

    def test_cmm_pdf_approved_tax_exempt_has_no_draft_watermark(self):
        content = build_pdf(
            {"quotation_number": "QT-APPROVED", "client_id": 1, "currency": "EUR", "vat_rate": 0, "status": "approved", "footer_form_code": "CMM-SA-F-04-03-Edition01"},
            [{"item_code": "SERVICE", "description": "Approved service item", "quantity": 1, "unit_price": 99, "discount_percent": 0, "item_type": "service_fee"}],
            {"name": "Long Client Name Hospital Biomedical Engineering Department"},
        )
        text = self.pdf_text(content)

        self.assertNotIn("DRAFT", text)
        self.assertIn("VAT EXEMPT", text)
        self.assertIn("EUR", text)
        self.assertIn("99.00", text)

    def test_grouped_quotation_allows_duplicate_parts_across_serial_numbers(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            os.environ["DB_PATH"] = db_path
            with connect() as conn:
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
                conn.execute("INSERT INTO clients (name) VALUES (?)", ("Hospital A",))
                conn.commit()

            quotation = create_quotation(
                QuotationIn(
                    client_id=1,
                    quotation_number="QT-DUP-001",
                    vat_rate=11,
                    equipment_groups=[
                        QuotationEquipmentGroupIn(
                            equipment_name="SLE 2000",
                            serial_number="D0424",
                            service_report_number="6-14762",
                            items=[QuotationItemIn(item_code="SL-N2191", description="Oxygen cell sensor", quantity=1, unit_price=220)],
                        ),
                        QuotationEquipmentGroupIn(
                            equipment_name="SLE 2000",
                            serial_number="D0410",
                            service_report_number="6-14763",
                            items=[QuotationItemIn(item_code="SL-N2191", description="Oxygen cell sensor", quantity=1, unit_price=220)],
                        ),
                    ],
                )
            )

            self.assertEqual(len(quotation["equipment_groups"]), 2)
            self.assertEqual([g["serial_number"] for g in quotation["equipment_groups"]], ["D0424", "D0410"])
            self.assertEqual([g["items"][0]["item_code"] for g in quotation["equipment_groups"]], ["SL-N2191", "SL-N2191"])
            self.assertEqual(quotation["subtotal"], 440)
            self.assertEqual(quotation["vat_amount"], 48.4)
            self.assertEqual(quotation["total_amount"], 488.4)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_ai_draft_starts_review_only_and_requires_approval(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        previous = os.environ.get("DB_PATH")
        try:
            os.environ["DB_PATH"] = db_path
            with connect() as conn:
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
                conn.execute("INSERT INTO clients (name) VALUES (?)", ("Hospital A",))
                conn.commit()
            extraction = RuleBasedQuotationExtractionProvider().extract_quotation_sync(
                "Need one cable part number PN-1. Cable price 50 dollars. Warranty three months.",
                QuotationContext(client_id=1, client_name="Hospital A", preferred_currency="USD"),
            )
            draft = ai_create_draft(QuotationAIDraftRequest(extraction=extraction, context=QuotationContext(client_id=1)))

            self.assertEqual(draft["quotation"]["status"], "ai_draft")
            reviewed = submit_review(draft["quotation"]["id"])
            self.assertEqual(reviewed["status"], "under_review")
            approved = approve_quotation(draft["quotation"]["id"], {"approved_by": "manager"})
            self.assertEqual(approved["status"], "approved")
            self.assertEqual(approved["approved_by"], "manager")
        finally:
            if previous is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = previous
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
