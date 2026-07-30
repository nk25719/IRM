import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StaticLayoutRegressionTest(unittest.TestCase):
    def test_dashboard_section_tabs_are_owned_by_shared_layout(self):
        dashboard_html = (ROOT / "app/static/dashboard.html").read_text()
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()

        self.assertNotIn("dashboard-tabs", dashboard_html)
        self.assertIn('"/dashboard": [', app_layout_js)
        self.assertEqual(app_layout_js.count('["By Customer", "/dashboard#customer"]'), 1)
        self.assertEqual(app_layout_js.count('["Aftermarket", "/dashboard#after-sales"]'), 1)
        self.assertIn('tabs.dataset.sectionTabs = slugify(module.label);', app_layout_js)

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

    def test_procurement_has_department_nav_and_one_page_tabs_container(self):
        procurement_html = (ROOT / "app/static/procurement.html").read_text()
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()

        self.assertIn('tabs.dataset.departmentNav = slugify(module.label);', app_layout_js)
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

    def test_aftermarket_navigation_uses_ten_primary_tabs(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()
        expected_tabs = [
            '["Dashboard", "/aftersales/dashboard"]',
            '["Service Calls", "/aftersales/service-calls"]',
            '["Quotations", "/aftersales/quotations"]',
            '["Preventive Maintenance", "/aftersales/preventive-maintenance"]',
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

    def test_after_sales_contract_routes_stay_owned_by_contracts(self):
        app_layout_js = (ROOT / "app/static/app_layout.js").read_text()
        pm_app = (ROOT / "pm-frontend/src/App.jsx").read_text()
        contract_view = (ROOT / "pm-frontend/src/components/ContractTrackerView.jsx").read_text()
        served_index = (ROOT / "app/static/pm/index.html").read_text()

        self.assertIn('["Contracts", "/aftersales/contracts"]', app_layout_js)
        self.assertIn('currentPath.includes("/contracts")', app_layout_js)
        self.assertIn('return "/aftersales/contracts";', app_layout_js)
        self.assertIn("function getBreadcrumb", app_layout_js)
        self.assertIn("ERM / ${module.label} / ${sectionLabel}", app_layout_js)
        self.assertIn('path.endsWith("/contracts/dashboard")', pm_app)
        self.assertIn('href="/aftersales/contracts/dashboard"', contract_view)
        self.assertIn("Manage Contracts", contract_view)
        self.assertIn("After Sales Contracts", served_index)
        self.assertNotIn('data-page-title="Preventive Maintenance"', served_index)


if __name__ == "__main__":
    unittest.main()
