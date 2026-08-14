import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StaticLayoutRegressionTest(unittest.TestCase):
    def test_dashboard_hash_tabs_are_owned_by_shared_layout(self):
        dashboard_html = (ROOT / "app/static/dashboard.html").read_text()
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()

        self.assertNotIn("dashboard-tabs", dashboard_html)
        self.assertIn('"/dashboard": [', app_layout_js)
        self.assertEqual(app_layout_js.count('["By Customer", "/dashboard#customer"]'), 1)
        self.assertEqual(app_layout_js.count('["Aftermarket", "/dashboard#after-sales"]'), 1)
        self.assertIn('tabs.dataset.sectionTabs = slugify(module.label);', app_layout_js)
        self.assertIn("module.links?.length", app_layout_js)

    def test_shared_layout_initialization_is_idempotent(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()

        self.assertIn('document.documentElement.dataset.irmLayoutInitialized === "true"', app_layout_js)
        self.assertIn('document.documentElement.dataset.irmLayoutInitialized = "true"', app_layout_js)

    def test_shared_layout_contains_one_sidebar_and_toggle(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()

        self.assertEqual(app_layout_js.count("data-app-sidebar"), 1)
        self.assertEqual(app_layout_js.count("erp-sidebar-collapse"), 2)
        self.assertIn('const SIDEBAR_STORAGE_KEY = "irm.sidebar.collapsed";', app_layout_js)
        self.assertIn("readSidebarPreference()", app_layout_js)

    def test_procurement_uses_sidebar_department_nav_and_one_page_tabs_container(self):
        procurement_html = (ROOT / "app/static/procurement.html").read_text()
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()

        self.assertIn('tabs.dataset.departmentNav = slugify(module.label);', app_layout_js)
        self.assertIn("if (!links || isHome || module.links?.length) return;", app_layout_js)
        self.assertEqual(procurement_html.count('data-page-tabs="procurement-dashboard"'), 1)
        self.assertNotIn('data-tab="purchaseOrders">Purchase Orders</button>', procurement_html)
        self.assertNotIn('data-tab="suppliers">Suppliers</button>', procurement_html)
        self.assertNotIn('data-tab="shipping">Shipping</button>', procurement_html)
        self.assertNotIn('data-tab="reports">Reports</button>', procurement_html)

    def test_collapsed_sidebar_width_is_defined_in_shared_css(self):
        theme_css = (ROOT / "app/static/theme.css").read_text()

        self.assertIn("--sidebar-expanded-width: 260px;", theme_css)
        self.assertIn("--sidebar-collapsed-width: 72px;", theme_css)
        self.assertIn("body.sidebar-collapsed", theme_css)
        self.assertIn("padding-left: var(--sidebar-collapsed-width);", theme_css)

    def test_page_filter_tabs_do_not_mix_sales_section_links(self):
        sales_html = (ROOT / "app/static/sales.html").read_text()
        render_tabs = re.search(r"function renderTabs\(\)\{(?P<body>.*?)\}\n", sales_html)

        self.assertIsNotNone(render_tabs)
        self.assertNotIn("viewLinks", render_tabs.group("body"))
        self.assertIn("categories.map", render_tabs.group("body"))

    def test_shared_data_actions_are_centralized_and_specific(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()
        theme_css = (ROOT / "app/static/theme.css").read_text()

        self.assertIn("const dataActions = [", app_layout_js)
        self.assertIn("strip.dataset.irmDataActions = slugify(config.title);", app_layout_js)
        self.assertIn("if (isAftermarketPath(currentPath)) return;", app_layout_js)
        self.assertEqual(app_layout_js.count('match: ["/crm/contacts"]'), 1)
        self.assertLess(app_layout_js.index('match: ["/crm/contacts"]'), app_layout_js.index('match: ["/clients", "/crm"]'))
        self.assertIn('exportHref: "/api/contacts/export"', app_layout_js)
        self.assertIn(".irm-data-actions", theme_css)

    def test_after_sales_dashboard_uses_operational_summary(self):
        after_sales_html = (ROOT / "app/static/after_sales.html").read_text()

        for marker in [
            "opsScoreboard",
            "activityCards",
            "workflowPipeline",
            "agingBar",
            "blockedWork",
            "engineerWorkload",
            "priorityAlerts",
            "upcomingList",
        ]:
            self.assertIn(marker, after_sales_html)
        self.assertIn("/api/aftermarket/dashboard/summary", after_sales_html)
        self.assertNotIn("dashboardMetrics", after_sales_html)
        self.assertNotIn("dashboardLinks", after_sales_html)
        self.assertNotIn("workspace-links", after_sales_html)
        self.assertNotIn("page-hero", after_sales_html)
        self.assertIn("utility-menu", after_sales_html)
        self.assertIn('id="viewTitle"', after_sales_html)
        self.assertIn("viewMeta", after_sales_html)

    def test_aftermarket_navigation_uses_ten_primary_tabs(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()
        expected_tabs = [
            '["Dashboard", "/aftersales/dashboard"]',
            '["Service Calls", "/aftersales/service-calls"]',
            '["Quotations", "/aftersales/quotations"]',
            '["Preventive Maintenance", "/aftersales/preventivemaintenance"]',
            '["Installations", "/aftersales/installations"]',
            '["Deliveries", "/aftersales/deliveries"]',
            '["Trainings", "/aftersales/trainings"]',
            '["Contracts", "/aftersales/contracts"]',
            '["Spare Parts Requests", "/aftersales/spare-parts"]',
            '["FMI / Technical Cases", "/aftersales/technical-cases"]',
        ]

        for tab in expected_tabs:
            self.assertEqual(app_layout_js.count(tab), 2)
        self.assertNotIn('["Cases", "/aftersales/service-cases"]', app_layout_js)
        self.assertNotIn('["Installed Base", "/aftersales/installed-base"]', app_layout_js)
        self.assertNotIn('["Reports", "/aftersales/reports"]', app_layout_js)
        self.assertIn('return "/aftersales/technical-cases";', app_layout_js)

    def test_aftermarket_views_have_compact_import_export_utilities(self):
        after_sales_html = (ROOT / "app/static/after_sales.html").read_text()

        self.assertIn('id="contextImportButton"', after_sales_html)
        self.assertIn('id="contextExportButton"', after_sales_html)
        self.assertIn("function importCurrentView()", after_sales_html)
        self.assertIn("function exportCurrentView()", after_sales_html)
        self.assertIn("function exportAftermarketWorkbook()", after_sales_html)
        self.assertIn("downloadCsv(`aftermarket-${id}-export.csv`", after_sales_html)
        self.assertIn('onclick="exportAftermarketWorkbook()"', after_sales_html)
        for route_token in [
            "/service-calls",
            "/spare-parts",
            "/contracts",
            "/quotations",
            "/installations",
            "/deliveries",
            "/trainings",
            "/technical-cases",
        ]:
            self.assertIn(route_token, after_sales_html)

    def test_clients_reports_and_training_demo_are_owned_by_correct_departments(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()
        module_page = (ROOT / "app/static/module_page.html").read_text()
        web_pages = (ROOT / "app/routers/web_pages.py").read_text()
        firebase_json = (ROOT / "firebase.json").read_text()

        self.assertNotIn('label: "Clients",\n      href: "/clients"', app_layout_js)
        self.assertNotIn('label: "Training & Demo",', app_layout_js)
        self.assertNotIn('label: "Reports",\n      href: "/reports"', app_layout_js)
        self.assertIn('["Clients", "/administration/clients"]', app_layout_js)
        self.assertIn('["Reports", "/administration/reports"]', app_layout_js)
        self.assertEqual(app_layout_js.count('["Trainings", "/aftersales/trainings"]'), 2)
        self.assertIn('value.replace("/clients", "/administration/clients")', app_layout_js)
        self.assertIn('value.replace("/reports", "/administration/reports")', app_layout_js)
        self.assertIn('value.replace("/training-demo", "/aftersales/trainings")', app_layout_js)
        self.assertIn('if (currentPath.startsWith("/equipment")) return "/administration/clients";', app_layout_js)
        self.assertIn('"/administration/reports":{title:"Reports"', module_page)
        self.assertIn('["Clients","/administration/clients"', module_page)
        self.assertIn('["Reports","/administration/reports"', module_page)
        self.assertNotIn('"/training-demo":{title:"Training & Demo"', module_page)
        self.assertNotIn('["Training & Demo","/training-demo"', module_page)
        self.assertNotIn('["After Sales Operations Training","/aftersales/training-demo"', module_page)
        self.assertNotIn('["Clients","/clients"', module_page)
        self.assertIn('@router.get("/clients/{section:path}", include_in_schema=False)', web_pages)
        self.assertIn('target = f"/administration/clients/{section}".rstrip("/")', web_pages)
        self.assertIn('return _redirect_with_query(request, "/aftersales/trainings")', web_pages)
        self.assertIn('return FileResponse(legacy_main.BASE_DIR / "static" / "crm.html")', web_pages)
        self.assertIn('"source": "/clients"', firebase_json)
        self.assertIn('"destination": "/administration/clients"', firebase_json)
        self.assertIn('"source": "/training-demo"', firebase_json)
        self.assertIn('"destination": "/aftersales/trainings"', firebase_json)

    def test_after_sales_contract_routes_and_pm_dashboard_mapping(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()
        pm_app = (ROOT / "pm-frontend/src/App.jsx").read_text()
        contract_view = (ROOT / "pm-frontend/src/components/ContractTrackerView.jsx").read_text()
        import_export_bar = (ROOT / "pm-frontend/src/components/ImportExportBar.jsx").read_text()
        hospital_status_view = (ROOT / "pm-frontend/src/components/HospitalContractStatusView.jsx").read_text()
        served_index = (ROOT / "app/static/pm/index.html").read_text()
        pm_css = (ROOT / "pm-frontend/src/App.css").read_text()
        web_pages = (ROOT / "app/routers/web_pages.py").read_text()
        firebase_json = (ROOT / "firebase.json").read_text()

        self.assertIn('["Contracts", "/aftersales/contracts"]', app_layout_js)
        self.assertIn('["Preventive Maintenance", "/aftersales/preventivemaintenance"]', app_layout_js)
        self.assertIn('currentPath.includes("/contracts")', app_layout_js)
        self.assertIn('return "/aftersales/contracts";', app_layout_js)
        self.assertIn('return "/aftersales/preventivemaintenance";', app_layout_js)
        self.assertIn("function getBreadcrumb", app_layout_js)
        self.assertIn("ERM / ${module.label} / ${sectionLabel}", app_layout_js)
        self.assertLess(web_pages.index('@router.get("/aftersales/contracts"'), web_pages.index('@router.get("/aftersales/pm"'))
        self.assertIn('return FileResponse(legacy_main.BASE_DIR / "static" / "pm" / "index.html")', web_pages)
        self.assertIn('return _redirect_with_query(request, "/aftersales/preventivemaintenance")', web_pages)
        self.assertIn('@router.get("/aftersales/preventivemaintenance"', web_pages)
        self.assertNotIn('"source": "/aftersales/contracts/dashboard"', firebase_json)
        self.assertNotIn('"source": "/after-sales/contracts/dashboard"', firebase_json)
        self.assertIn('"destination": "/aftersales/preventivemaintenance"', firebase_json)
        self.assertIn('"destination": "/pm/index.html"', firebase_json)
        self.assertIn('path.endsWith("/preventivemaintenance")', pm_app)
        self.assertNotIn('path.endsWith("/contracts/dashboard")', pm_app)
        self.assertIn("isPreventiveMaintenanceRoute", pm_app)
        self.assertIn("isContractsRoute", pm_app)
        self.assertIn("showViewSwitcher", pm_app)
        self.assertIn('title: "Preventive Maintenance"', pm_app)
        self.assertIn("PM schedule, due work, reminders, and completion tracking.", pm_app)
        self.assertIn('href="/aftersales/preventivemaintenance"', contract_view)
        self.assertIn("Manage Contracts", contract_view)
        self.assertIn("utility-menu", contract_view)
        self.assertIn("contracts-toolbar", contract_view)
        self.assertNotIn("<h2 className=\"section-title\">Hospital Contracts</h2>", contract_view)
        self.assertIn("utility-menu", import_export_bar)
        self.assertIn("Export visible rows", hospital_status_view)
        self.assertIn("Manage Contracts", pm_app)
        self.assertNotIn('href="/">Home</a>', pm_app)
        self.assertNotIn('href="/warehouse">Warehouse</a>', pm_app)
        self.assertIn(".topbar { display: flex; gap: 12px;", pm_css)
        self.assertIn(".contracts-view-card { padding: 8px; }", pm_css)
        self.assertIn(".contracts-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }", pm_css)
        self.assertIn(".contract-tab { min-height: 36px;", pm_css)
        self.assertIn(".filters-card { padding: 8px; }", pm_css)
        self.assertIn(".metric-value { font-size: 24px;", pm_css)
        self.assertIn("After Sales Contracts", served_index)
        self.assertNotIn('data-page-title="Preventive Maintenance"', served_index)


if __name__ == "__main__":
    unittest.main()
