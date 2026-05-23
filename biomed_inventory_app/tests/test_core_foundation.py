import os
import tempfile
import types
import unittest


class CoreFoundationSmokeTest(unittest.TestCase):
    def setUp(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(db_path)
        self.db_path = db_path
        self.excel_path = tempfile.mktemp(suffix=".xlsx")
        os.environ["DB_PATH"] = db_path
        os.environ["EXCEL_PATH"] = self.excel_path

        import importlib
        import app.main as main

        self.main = importlib.reload(main)
        self.main.init_db()
        self.request = types.SimpleNamespace(session={"username": "admin", "role": "admin"})

    def test_core_relationships_and_master_reference(self):
        m = self.main
        client = m.create_crm_client(m.CRMClient(name="Hospital A"), self.request)
        department = m.save_department({"client_id": client["id"], "department_name": "ICU"}, self.request)
        equipment = m.create_equipment(
            {
                "client_id": client["id"],
                "department_id": department["id"],
                "asset_tag": "EQ-1",
                "serial_number": "SN-1",
                "manufacturer": "GE",
                "model": "B105",
            },
            self.request,
        )
        request = m.create_customer_request(
            m.CustomerRequestIn(
                client_hospital="Hospital A",
                department="ICU",
                contact_person="Nurse Lead",
                request_source="call",
                lines=[m.CustomerRequestLineIn(requested_item="PN-1", quantity=1, item_type="spare_part")],
            ),
            self.request,
        )
        quoted = m.generate_customer_request_document(request["id"], "quotation")

        self.assertEqual(department["department_name"], "ICU")
        self.assertEqual(equipment["asset_tag"], "EQ-1")
        self.assertRegex(request["parent_case_reference"], r"^AS-\d{4}-\d{5}$")
        self.assertEqual(quoted["documents"][0]["document_reference"], f"OF-{request['parent_case_reference']}")

        conn = m.db()
        try:
            trace = m.traceability_data(conn, request["parent_case_reference"])
            dashboard = m.crm_client_dashboard_data(conn, client["id"])
        finally:
            conn.close()

        self.assertEqual(trace["parent_case_reference"], request["parent_case_reference"])
        self.assertEqual(len(dashboard["departments"]), 1)
        self.assertEqual(len(dashboard["equipment"]), 1)
        self.assertEqual(len(dashboard["parent_timelines"]), 1)

    def test_pending_offer_import_department_progress_search_and_bulk_edit(self):
        m = self.main
        df = m.pd.DataFrame(
            [
                {"Hospital": "Hospital A", "Offer Ref": "OFF-2026-001", "Status": "Pending", "Requirement": "2 ECG cables", "Department": "ICU"},
                {"Hospital": "Hospital A", "Offer Ref": "OFF-2026-002", "Status": "Blocked", "Requirement": "Ventilator PM", "Department": "ICU", "Blocked By": "customer_availability"},
                {"Hospital": "Hospital B", "Offer Ref": "OFF-2026-003", "Status": "In Progress", "Requirement": "Monitor installation", "Department": "ER"},
            ]
        )
        rows = m.parse_pending_offer_dataframe(df)
        conn = m.db()
        try:
            results = m.commit_pending_offer_rows(conn, rows, user="admin")
            conn.commit()
            hospital_a = conn.execute("SELECT * FROM clients WHERE name='Hospital A'").fetchone()
            hospital_b = conn.execute("SELECT * FROM clients WHERE name='Hospital B'").fetchone()
            icu = conn.execute("SELECT * FROM departments WHERE client_id=? AND department_name='ICU'", (hospital_a["id"],)).fetchone()
            er = conn.execute("SELECT * FROM departments WHERE client_id=? AND department_name='ER'", (hospital_b["id"],)).fetchone()
            cases = [dict(r) for r in conn.execute("SELECT * FROM cases ORDER BY external_reference").fetchall()]
            dashboard_a = m.crm_client_dashboard_data(conn, hospital_a["id"])
            progress_a = m.department_progress_rows(conn, hospital_a["id"])
        finally:
            conn.close()

        self.assertEqual(len([r for r in results if r["status"] == "imported"]), 3)
        self.assertIsNotNone(icu)
        self.assertIsNotNone(er)
        self.assertEqual(cases[0]["external_reference"], "OFF-2026-001")
        self.assertRegex(cases[0]["parent_case_reference"], r"^AS-\d{4}-\d{5}$")
        self.assertEqual(cases[1]["blocked_reason"], "customer_availability")
        self.assertGreaterEqual(dashboard_a["counts"]["blocked_items"], 1)
        self.assertEqual(progress_a[0]["department_name"], "ICU")
        self.assertGreaterEqual(progress_a[0]["blocked_items"], 1)

        search = m.global_search("OFF-2026-001")
        self.assertTrue(any(item["label"] == "OFF-2026-001" for item in search["results"]))

        edit = m.bulk_edit({"target": "cases", "ids": [cases[0]["id"]], "updates": {"priority": "urgent"}}, self.request)
        self.assertEqual(edit["requested"], 1)


if __name__ == "__main__":
    unittest.main()
