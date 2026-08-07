import io
import os
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook

from app.quotation_api import (
    QuotationAIDraftRequest,
    QuotationEquipmentGroupIn,
    QuotationIn,
    QuotationItemIn,
    approve_quotation,
    ai_create_draft,
    cancel_client_order_item,
    connect,
    create_purchase_order_from_client_order_items,
    create_quotation,
    create_service_report_for_client_order,
    create_shipment_for_purchase_order_items,
    ensure_tables,
    receive_shipment_items,
    submit_review,
)
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

    def test_ai_extraction_handles_plain_language_pm_service_request(self):
        text = "Create a quotation for HMC Lab A for 3 patient monitors, annual PM, labor included, 2-year contract, urgent delivery."

        result = RuleBasedQuotationExtractionProvider().extract_quotation_sync(text, QuotationContext(client_id=1, client_name="HMC Lab A", preferred_currency="USD"))

        self.assertEqual(result.client.id, 1)
        self.assertEqual(result.equipment.model, "patient monitors")
        self.assertEqual(result.items[0].item_type, "service")
        self.assertEqual(result.items[0].quantity, 3)
        self.assertIn("Annual Pm", result.items[0].description)
        self.assertEqual(result.commercial_terms.warranty, "2-year")
        self.assertIn("urgent delivery", result.commercial_terms.delivery_time)
        self.assertTrue(any("Unit price" in item for item in result.missing_information))

    def test_quotation_page_has_ai_review_before_draft_creation(self):
        html = (Path(__file__).resolve().parents[1] / "app/static/quotations.html").read_text(encoding="utf-8")

        self.assertIn("Generate Structured Preview", html)
        self.assertIn("Create Reviewed Draft", html)
        self.assertIn("pendingAIExtraction", html)
        self.assertIn("aiExtractionEditor", html)
        self.assertIn("/quotations/ai/create-draft", html)

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
                ensure_tables(conn)
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
                ensure_tables(conn)
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

    def test_active_quotation_approval_creates_client_order_and_procurement_demand(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        previous = os.environ.get("DB_PATH")
        try:
            os.environ["DB_PATH"] = db_path
            with connect() as conn:
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
                conn.execute("INSERT INTO clients (name) VALUES (?)", ("Hospital A",))
                conn.commit()
            quotation = create_quotation(
                QuotationIn(
                    client_id=1,
                    quotation_number="QT-FLOW-001",
                    items=[QuotationItemIn(item_code="PN-NEEDS-ORDER", description="Service spare part", quantity=2, unit_price=50)],
                )
            )

            approved = approve_quotation(quotation["id"], {"approved_by": "manager"})

            self.assertEqual(approved["status"], "approved")
            self.assertEqual(approved["fulfillment"]["customer_order"]["status"], "open")
            self.assertEqual(approved["fulfillment"]["items"][0]["pending_qty"], 2)
            self.assertEqual(approved["fulfillment"]["items"][0]["status"], "purchase_required")
            self.assertEqual(approved["fulfillment"]["stock_items"][0]["status"], "purchase_required")
        finally:
            if previous is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = previous
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_active_quotation_approval_bypasses_procurement_when_stock_exists(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        previous = os.environ.get("DB_PATH")
        try:
            os.environ["DB_PATH"] = db_path
            with connect() as conn:
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
                conn.execute("INSERT INTO clients (name) VALUES (?)", ("Hospital A",))
                conn.commit()
            quotation = create_quotation(
                QuotationIn(
                    client_id=1,
                    quotation_number="QT-STOCK-001",
                    items=[QuotationItemIn(item_code="PN-IN-STOCK", description="Stock cable", quantity=2, unit_price=25)],
                )
            )
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO stock_items
                    (ref, description, qty, source, status, location, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("PN-IN-STOCK", "Stock cable", 3, "reception", "in_stock", "Main Stock", "2026-07-31", "2026-07-31"),
                )
                conn.commit()

            approved = approve_quotation(quotation["id"], {"approved_by": "manager"})

            self.assertEqual(approved["fulfillment"]["customer_order"]["status"], "procured")
            self.assertEqual(approved["fulfillment"]["items"][0]["pending_qty"], 0)
            self.assertEqual(approved["fulfillment"]["items"][0]["status"], "reserved")
            self.assertEqual(approved["fulfillment"]["stock_items"][0]["status"], "reserved")
            self.assertEqual(approved["fulfillment"]["stock_items"][0]["source"], "existing_stock")
            self.assertEqual(approved["fulfillment"]["reservations"][0]["qty"], 2)
            with connect() as conn:
                remaining = conn.execute("SELECT qty FROM stock_items WHERE customer_order_id IS NULL AND ref='PN-IN-STOCK'").fetchone()["qty"]
            self.assertEqual(remaining, 1)
        finally:
            if previous is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = previous
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_service_workflow_purchase_shipment_reception_and_service_report(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        previous = os.environ.get("DB_PATH")
        try:
            os.environ["DB_PATH"] = db_path
            with connect() as conn:
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
                conn.execute("INSERT INTO clients (name) VALUES (?)", ("Hospital A",))
                conn.commit()
            quotation = create_quotation(
                QuotationIn(
                    client_id=1,
                    quotation_number="QT-PURCHASE-001",
                    items=[QuotationItemIn(item_code="PN-BUY", description="Ordered spare part", quantity=3, unit_price=40)],
                )
            )
            approved = approve_quotation(quotation["id"], {"approved_by": "manager"})
            order = approved["fulfillment"]["customer_order"]
            line = approved["fulfillment"]["items"][0]

            self.assertEqual(line["status"], "purchase_required")
            self.assertEqual(line["required_qty"], 3)
            with connect() as conn:
                po = create_purchase_order_from_client_order_items(conn, [line["id"]], supplier_id=55)
                shipment = create_shipment_for_purchase_order_items(conn, {po["items"][0]["id"]: 3}, supplier_id=55, shipment_no="SH-PURCHASE-001")
                reception = receive_shipment_items(
                    conn,
                    shipment["shipment"]["id"],
                    [{
                        "shipment_item_id": shipment["items"][0]["id"],
                        "received_qty": 3,
                        "accepted_qty": 3,
                        "serial_number": "SN-PUR-1",
                        "batch_lot_number": "LOT-1",
                        "expiry_date": "2027-12-31",
                        "warehouse_location": "Main-A1",
                    }],
                )
                ready_line = dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (line["id"],)).fetchone())
                reserved_stock = dict(conn.execute("SELECT * FROM stock_items WHERE source='reception' AND customer_order_item_id=?", (line["id"],)).fetchone())
                report = create_service_report_for_client_order(
                    conn,
                    order["id"],
                    [{"customer_order_item_id": line["id"], "stock_item_id": reserved_stock["id"], "qty": 3, "action": "installed"}],
                )
                issued_stock = dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (reserved_stock["id"],)).fetchone())
                conn.commit()

            self.assertEqual(po["items"][0]["customer_order_item_id"], line["id"])
            self.assertEqual(shipment["items"][0]["purchase_order_item_id"], po["items"][0]["id"])
            self.assertEqual(reception["items"][0]["accepted_qty"], 3)
            self.assertEqual(ready_line["status"], "ready_for_delivery")
            self.assertEqual(ready_line["reception_status"], "received")
            self.assertEqual(report["items"][0]["customer_order_item_id"], line["id"])
            self.assertEqual(report["items"][0]["stock_item_id"], reserved_stock["id"])
            self.assertEqual(issued_stock["qty"], 0)
            self.assertEqual(issued_stock["status"], "issued")
        finally:
            if previous is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = previous
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_service_workflow_partial_stock_partial_shipment_reception_and_duplicate_guard(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        previous = os.environ.get("DB_PATH")
        try:
            os.environ["DB_PATH"] = db_path
            with connect() as conn:
                ensure_tables(conn)
                conn.execute("CREATE TABLE clients (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
                conn.execute("INSERT INTO clients (name) VALUES (?)", ("Hospital A",))
                conn.execute(
                    """
                    INSERT INTO stock_items
                    (ref, description, qty, source, status, location, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("PN-PARTIAL", "Partial stock part", 1, "reception", "in_stock", "Main Stock", "2026-07-31", "2026-07-31"),
                )
                conn.commit()
            quotation = create_quotation(
                QuotationIn(
                    client_id=1,
                    quotation_number="QT-PARTIAL-001",
                    items=[QuotationItemIn(item_code="PN-PARTIAL", description="Partial stock part", quantity=4, unit_price=10)],
                )
            )
            approved = approve_quotation(quotation["id"], {"approved_by": "manager"})
            line = approved["fulfillment"]["items"][0]

            self.assertEqual(line["reserved_qty"], 1)
            self.assertEqual(line["required_qty"], 3)
            self.assertEqual(line["status"], "purchase_required")

            with connect() as conn:
                po = create_purchase_order_from_client_order_items(conn, [line["id"]], supplier_id=77)
                shipment = create_shipment_for_purchase_order_items(conn, {po["items"][0]["id"]: 2}, supplier_id=77, shipment_no="SH-PARTIAL-001")
                reception = receive_shipment_items(
                    conn,
                    shipment["shipment"]["id"],
                    [{
                        "shipment_item_id": shipment["items"][0]["id"],
                        "received_qty": 2,
                        "accepted_qty": 1,
                        "rejected_qty": 1,
                        "warehouse_location": "Main-B2",
                    }],
                )
                partial_line = dict(conn.execute("SELECT * FROM customer_order_items WHERE id=?", (line["id"],)).fetchone())
                with self.assertRaises(Exception):
                    receive_shipment_items(
                        conn,
                        shipment["shipment"]["id"],
                        [{"shipment_item_id": shipment["items"][0]["id"], "received_qty": 1, "accepted_qty": 1}],
                    )
                cancelled = cancel_client_order_item(conn, line["id"], "Customer cancelled remaining quantity")
                conn.commit()

            self.assertEqual(reception["items"][0]["accepted_qty"], 1)
            self.assertEqual(reception["items"][0]["rejected_qty"], 1)
            self.assertEqual(partial_line["status"], "partially_received")
            self.assertEqual(cancelled["status"], "cancelled")
        finally:
            if previous is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = previous
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    unittest.main()
