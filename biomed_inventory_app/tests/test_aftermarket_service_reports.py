import io
import os
import tempfile
import unittest

from openpyxl import Workbook


class AftermarketServiceReportImportTest(unittest.TestCase):
    def setUp(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(db_path)
        self.db_path = db_path
        os.environ["DB_PATH"] = db_path

        import importlib
        import app.legacy_main as legacy_main
        import app.aftermarket_service_reports as service_reports

        self.legacy_main = importlib.reload(legacy_main)
        self.service_reports = importlib.reload(service_reports)
        self.legacy_main.init_db()
        self.service_reports.ensure_service_report_tables()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def workbook_bytes(self, quantity=2, total=300):
        wb = Workbook()
        ws = wb.active
        ws.append(["SR#", "SR-1001", "", "Institution", "Hospital A"])
        ws.append(["City", "Beirut", "", "Country", "Lebanon"])
        ws.append(["Supplier", "IRM", "", "Equipment Model", "Ventilator X"])
        ws.append(["Serial Number", "SN-VENT-1", "", "Status", "open"])
        ws.append(["Call Date", "2026-07-01", "", "Call Time", "09:30"])
        ws.append(["Visit Date", "2026-07-02", "", "Visit Time", "10:30"])
        ws.append(["Completed Date", "2026-07-02", "", "Completed Time", "12:00"])
        ws.append(["Call Reason", "Alarm issue", "", "Description", "Checked oxygen sensor"])
        ws.append(["Total Travel Hours", 1, "", "Total Labor Hours", 2])
        ws.append(["Total Working Hours", 3, "", "Total Travel KM", 18])
        ws.append([])
        ws.append(["Supplier", "Part Number", "Description", "Quantity", "Unit Price", "Total Price"])
        ws.append(["Drager", "O2-SENSOR", "Oxygen sensor", quantity, 150, total])
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    def installed_base_bytes(self, status="Active"):
        wb = Workbook()
        ws = wb.active
        ws.append(["Company", "Supplier", "Product type", "Model", "Serial #", "Institution", "Unit Status", "Order #", "Installation date", "Warranty ends"])
        ws.append(["IRM", "Drager", "Ventilator", "Ventilator X", "SN-VENT-1", "Hospital A", status, "ORD-1", "2026-01-15", "2027-01-15"])
        output = io.BytesIO()
        wb.save(output)
        return output.getvalue()

    def test_installed_base_import_upserts_by_serial_number(self):
        first_rows = self.service_reports.parse_installed_base(self.installed_base_bytes(), "installed.xlsx")
        second_rows = self.service_reports.parse_installed_base(self.installed_base_bytes(status="Inactive"), "installed.xlsx")

        conn = self.legacy_main.db()
        try:
            self.assertEqual(self.service_reports.upsert_equipment_asset(conn, first_rows[0]), "created")
            self.assertEqual(self.service_reports.upsert_equipment_asset(conn, second_rows[0]), "updated")
            conn.commit()
            rows = [dict(r) for r in conn.execute("SELECT * FROM equipment_assets WHERE serial_number='SN-VENT-1'").fetchall()]
        finally:
            conn.close()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["unit_status"], "Inactive")

    def test_import_upserts_service_report_and_recreates_parts(self):
        conn = self.legacy_main.db()
        try:
            conn.execute(
                "INSERT INTO equipment (serial_number, manufacturer, model, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                ("SN-VENT-1", "Drager", "Ventilator X", "2026-07-01", "2026-07-01"),
            )
            conn.commit()
        finally:
            conn.close()

        report, parts = self.service_reports.parse_service_report(self.workbook_bytes(), "sr.xlsx")
        first = self.service_reports.upsert_service_report(report, parts)

        self.assertEqual(first["action"], "created")
        self.assertTrue(first["equipment_linked"])
        self.assertEqual(first["parts_count"], 1)

        report, parts = self.service_reports.parse_service_report(self.workbook_bytes(quantity=1, total=150), "sr.xlsx")
        second = self.service_reports.upsert_service_report(report, parts)

        self.assertEqual(second["action"], "updated")
        conn = self.legacy_main.db()
        try:
            report_count = conn.execute("SELECT COUNT(*) AS c FROM service_reports WHERE sr_number='SR-1001'").fetchone()["c"]
            part_rows = [dict(r) for r in conn.execute("SELECT * FROM service_report_parts WHERE sr_number='SR-1001'").fetchall()]
        finally:
            conn.close()

        self.assertEqual(report_count, 1)
        self.assertEqual(len(part_rows), 1)
        self.assertEqual(part_rows[0]["quantity"], 1)
        self.assertEqual(part_rows[0]["total_price"], 150)

    def test_service_report_links_to_equipment_asset_by_serial_number(self):
        asset_rows = self.service_reports.parse_installed_base(self.installed_base_bytes(), "installed.xlsx")
        conn = self.legacy_main.db()
        try:
            self.service_reports.upsert_equipment_asset(conn, asset_rows[0])
            conn.commit()
        finally:
            conn.close()

        report, parts = self.service_reports.parse_service_report(self.workbook_bytes(), "sr.xlsx")
        result = self.service_reports.upsert_service_report(report, parts)

        self.assertTrue(result["equipment_asset_linked"])
        self.assertEqual(result["service_report"]["match_status"], "matched")
        self.assertIsNotNone(result["service_report"]["equipment_asset_id"])


if __name__ == "__main__":
    unittest.main()
