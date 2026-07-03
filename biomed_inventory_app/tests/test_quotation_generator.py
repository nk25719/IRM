import io
import unittest
from zipfile import ZipFile

from openpyxl import Workbook

from app.quotation_ai_service import QuotationAIService
from app.quotation_export import build_excel, build_pdf, calculate_totals
from app.quotation_import_service import parse_excel_bytes


class QuotationGeneratorTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
