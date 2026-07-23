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


if __name__ == "__main__":
    unittest.main()
