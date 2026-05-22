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
        self.assertRegex(request["parent_case_reference"], r"^AS-\d{4}-\d{4}$")
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


if __name__ == "__main__":
    unittest.main()
