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

        self.assertIn('document.body.dataset.appLayoutInitialized === "true"', app_layout_js)
        self.assertIn('document.body.dataset.appLayoutInitialized = "true"', app_layout_js)

    def test_page_filter_tabs_do_not_mix_sales_section_links(self):
        sales_html = (ROOT / "app/static/sales.html").read_text()
        render_tabs = re.search(r"function renderTabs\(\)\{(?P<body>.*?)\}\n", sales_html)

        self.assertIsNotNone(render_tabs)
        self.assertNotIn("viewLinks", render_tabs.group("body"))
        self.assertIn("categories.map", render_tabs.group("body"))


if __name__ == "__main__":
    unittest.main()
