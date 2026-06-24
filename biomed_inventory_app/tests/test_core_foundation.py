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
        self.assertIn("service_follow_up", dashboard)

    def test_service_hospital_follow_up_tracks_service_department_buckets(self):
        m = self.main
        client = m.create_crm_client(m.CRMClient(name="Service Hospital"), self.request)
        equipment = m.create_equipment(
            {
                "client_id": client["id"],
                "asset_tag": "SVC-EQ-1",
                "serial_number": "SVC-SN-1",
                "manufacturer": "GE",
                "model": "Monitor",
                "next_pm_date": "2026-06-25",
                "contract_no": "CT-SVC-1",
                "contract_end_date": "2026-07-20",
            },
            self.request,
        )
        request = m.create_customer_request(
            m.CustomerRequestIn(
                client_hospital="Service Hospital",
                department="ICU",
                contact_person="Head Nurse",
                request_source="email",
                lines=[m.CustomerRequestLineIn(requested_item="Delivery Item", quantity=2, item_type="new_equipment")],
            ),
            self.request,
        )

        conn = m.db()
        try:
            conn.execute(
                "INSERT INTO service_calls (client_id, equipment_id, call_no, status, engineer, issue, opened_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client["id"], equipment["id"], "CALL-SVC-1", "open", "Engineer A", "Follow-up call", "2026-06-20", "2026-06-20", "2026-06-20"),
            )
            conn.execute(
                "INSERT INTO quotations (client_id, equipment_id, quotation_no, quote_date, status, amount, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (client["id"], equipment["id"], "Q-SVC-1", "2026-06-21", "sent", 1250, "2026-06-21", "2026-06-21"),
            )
            conn.execute(
                "INSERT INTO equipment_recall_notices (client_id, equipment_id, notice_type, notice_no, manufacturer, affected_serial_numbers, completion_status, corrective_actions, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (client["id"], equipment["id"], "FMI", "FMI-SVC-1", "GE", "SVC-SN-1", "open", "Replace kit", "2026-06-22", "2026-06-22"),
            )
            conn.commit()
            follow_up = m.service_hospital_follow_up_data(conn, client["id"])
            after_sales = m.after_sales_dashboard_data(conn)
        finally:
            conn.close()

        self.assertEqual(follow_up["summary"]["upcoming_sales_deliveries"], 1)
        self.assertEqual(follow_up["summary"]["calls_pending"], 1)
        self.assertEqual(follow_up["summary"]["offers_pending"], 1)
        self.assertEqual(follow_up["summary"]["contract_renewals_pending"], 1)
        self.assertEqual(follow_up["summary"]["fmi_impacted_equipment"], 1)
        self.assertEqual(follow_up["summary"]["pm_due"], 1)
        hospital_row = next(row for row in after_sales["hospital_crm"] if row["id"] == client["id"])
        self.assertEqual(hospital_row["service_follow_up_score"], 4)

    def test_unified_sales_flow_creates_stock_only_after_quotation_approval(self):
        m = self.main
        client = m.create_crm_client(m.CRMClient(name="Unified Sales Hospital"), self.request)
        product = m.create_product(
            {
                "ref": "USF-MON-001",
                "description": "Patient monitor",
                "category": "equipment",
                "product_type": "equipment",
                "brand": "GE",
                "model": "B105",
                "unit_price": 1200,
            }
        )
        quotation = m.create_commercial_quotation(
            client["id"],
            [{"product_id": product["id"], "qty": 2}],
            quotation_no="QT-USF-001",
        )

        conn = m.db()
        try:
            stock_before = conn.execute("SELECT COUNT(*) AS c FROM stock_items").fetchone()["c"]
            quotation_items = conn.execute("SELECT COUNT(*) AS c FROM quotation_items WHERE quotation_id=?", (quotation["quotation"]["id"],)).fetchone()["c"]
        finally:
            conn.close()

        self.assertEqual(quotation_items, 1)
        self.assertEqual(stock_before, 0)

        approved = m.approve_quotation(quotation["quotation"]["id"])
        self.assertEqual(approved["customer_order"]["status"], "open")
        self.assertEqual(len(approved["items"]), 1)
        self.assertEqual(len(approved["stock_items"]), 1)
        self.assertEqual(approved["stock_items"][0]["status"], "pending_procurement")
        self.assertEqual(approved["stock_items"][0]["qty"], 2)

        po = m.create_purchase_order_from_stock_items(44, [approved["stock_items"][0]["id"]])
        self.assertEqual(po["purchase_order"]["supplier_id"], 44)
        self.assertEqual(po["items"][0]["status"], "ordered")

        shipment = m.create_shipment_from_purchase_order_items([po["items"][0]["id"]], supplier_id=44, shipment_no="SH-USF-001")
        self.assertEqual(shipment["shipment"]["status"], "shipped")

        reception = m.receive_shipment(shipment["shipment"]["id"])
        self.assertEqual(reception["reception"]["status"], "received")

        conn = m.db()
        try:
            stock_item = dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (approved["stock_items"][0]["id"],)).fetchone())
        finally:
            conn.close()
        self.assertEqual(stock_item["status"], "in_stock")

        delivery = m.create_delivery_order(client["id"], approved["customer_order"]["id"], [stock_item["id"]], notes="Deliver approved quotation")
        self.assertEqual(delivery["delivery_order"]["status"], "delivered")

        conn = m.db()
        try:
            final_stock = dict(conn.execute("SELECT * FROM stock_items WHERE id=?", (stock_item["id"],)).fetchone())
            final_order = dict(conn.execute("SELECT * FROM customer_orders WHERE id=?", (approved["customer_order"]["id"],)).fetchone())
        finally:
            conn.close()

        self.assertEqual(final_stock["status"], "delivered")
        self.assertEqual(final_order["status"], "delivered")

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

    def test_procurement_assigns_unassigned_client_order_items_to_po(self):
        m = self.main
        request = m.create_customer_request(
            m.CustomerRequestIn(
                client_hospital="Hospital Procurement",
                department="ICU",
                contact_person="Purchasing Lead",
                request_source="email",
                lines=[m.CustomerRequestLineIn(requested_item="ECG-CABLE-001", quantity=3, item_type="spare_part")],
            ),
            self.request,
        )
        m.convert_customer_request_to_order(request["id"])

        unassigned = m.unassigned_client_order_items()
        self.assertEqual(len(unassigned), 1)
        self.assertEqual(unassigned[0]["client_order_no"][:3], "CO-")

        po_no = "PO-TEST-001"
        m.create_po(
            m.PurchaseOrder(
                po_no=po_no,
                supplier="Supplier A",
                po_date="2026-05-26",
                contact_person="Supplier Contact",
                payment_terms="30 days",
                expected_date="2026-06-10",
            )
        )
        assigned = m.assign_client_order_items_to_po(
            po_no,
            {"client_order_item_ids": [unassigned[0]["client_order_item_id"]]},
        )
        self.assertEqual(assigned["assigned"], 1)
        self.assertEqual(m.unassigned_client_order_items(), [])

        conn = m.db()
        try:
            po = conn.execute("SELECT * FROM purchase_orders WHERE po_no=?", (po_no,)).fetchone()
            line = conn.execute("SELECT * FROM purchase_order_items WHERE po_no=?", (po_no,)).fetchone()
            request_line = conn.execute("SELECT * FROM customer_request_items WHERE id=?", (line["request_item_id"],)).fetchone()
        finally:
            conn.close()

        self.assertEqual(po["payment_terms"], "30 days")
        self.assertEqual(line["client_order_no"], unassigned[0]["client_order_no"])
        self.assertEqual(request_line["linked_purchase_order"], po_no)
        self.assertEqual(request_line["procurement_status"], "po_draft")

        received = m.receive_po_now(po_no)
        self.assertEqual(received["auto_received_items"], 1)

    def test_procurement_tracks_duplicate_refs_as_separate_rows(self):
        m = self.main
        request_ids = []
        for hospital in ["Hospital One", "Hospital Two"]:
            request = m.create_customer_request(
                m.CustomerRequestIn(
                    client_hospital=hospital,
                    department="ICU",
                    contact_person="Procurement Lead",
                    request_source="email",
                    lines=[m.CustomerRequestLineIn(requested_item="ECG-CABLE-001", quantity=1, item_type="spare_part")],
                ),
                self.request,
            )
            m.convert_customer_request_to_order(request["id"])
            request_ids.append(request["id"])

        unassigned = m.unassigned_client_order_items()
        self.assertEqual(len(unassigned), 2)
        self.assertEqual({row["ref"] for row in unassigned}, {"ECG-CABLE-001"})
        self.assertEqual({row["description"] for row in unassigned}, {"ECG-CABLE-001"})
        self.assertEqual(len({row["co_no"] for row in unassigned}), 2)

        for idx, row in enumerate(unassigned, start=1):
            po_no = f"PO-DUP-{idx:03d}"
            m.create_po(m.PurchaseOrder(po_no=po_no, supplier=f"Supplier {idx}"))
            result = m.assign_client_order_items_to_po(po_no, {"client_order_item_ids": [row["client_order_item_id"]]})
            self.assertEqual(result["assigned"], 1)

        tracked = [row for row in m.procurement_tracked_items() if row["ref"] == "ECG-CABLE-001"]
        assigned = [row for row in tracked if row["source"] == "purchase_order"]
        self.assertEqual(len(assigned), 2)
        self.assertEqual({row["description"] for row in assigned}, {"ECG-CABLE-001"})
        self.assertEqual(len({row["co_no"] for row in assigned}), 2)
        self.assertEqual({row["po_no"] for row in assigned}, {"PO-DUP-001", "PO-DUP-002"})
        self.assertEqual({row["supplier"] for row in assigned}, {"Supplier 1", "Supplier 2"})
        self.assertEqual({row["customer"] for row in assigned}, {"Hospital One", "Hospital Two"})

    def test_inventory_split_and_equipment_database_fields(self):
        m = self.main
        part = m.create_item(
            m.InventoryItem(
                pn="SPARE-001",
                description="Monitor spare cable",
                location="C1",
                system_qty=2,
                physical_qty=2,
                item_category="spare_parts",
            )
        )
        accessory = m.create_item(
            m.InventoryItem(
                pn="ACC-001",
                description="Monitor accessory bracket",
                location="A1",
                system_qty=1,
                physical_qty=1,
                item_category="accessories",
            )
        )

        spare_rows = m.list_inventory_category("spare-parts")
        accessory_rows = m.list_inventory_category("accessories")
        self.assertTrue(any(row["id"] == part["id"] for row in spare_rows))
        self.assertFalse(any(row["id"] == accessory["id"] for row in spare_rows))
        self.assertTrue(any(row["id"] == accessory["id"] for row in accessory_rows))

        client = m.create_crm_client(m.CRMClient(name="Hospital Equipment"), self.request)
        department = m.save_department({"client_id": client["id"], "department_name": "NICU"}, self.request)
        equipment = m.create_equipment(
            {
                "client_id": client["id"],
                "department_id": department["id"],
                "asset_tag": "EQ-SYS-1",
                "serial_number": "SN-SYS-1",
                "manufacturer": "GE",
                "model": "B450",
                "equipment_name": "Patient Monitor",
                "equipment_family": "Monitoring",
                "system_name": "Monitoring System",
                "subsystem_name": "Bedside Monitor",
                "end_user": "NICU Nurse Station",
                "installation_date": "2026-05-20",
                "installation_data": "Installed with network and power validation",
                "warranty_expiration": "2028-05-20",
                "delivery_doc": "DN-2026-001",
                "supplies": "ECG leads, NIBP cuff",
            },
            self.request,
        )
        rows = m.list_equipment(q="EQ-SYS-1")
        row = rows[0]
        self.assertEqual(row["system_name"], "Monitoring System")
        self.assertEqual(row["subsystem_name"], "Bedside Monitor")
        self.assertEqual(row["end_user"], "NICU Nurse Station")
        self.assertEqual(row["warranty_expiration"], "2028-05-20")
        self.assertEqual(row["delivery_doc"], "DN-2026-001")
        self.assertEqual(row["supplies"], "ECG leads, NIBP cuff")

        detail = m.get_equipment(equipment["id"])
        self.assertEqual(detail["installation_data"], "Installed with network and power validation")


if __name__ == "__main__":
    unittest.main()
