from __future__ import annotations

import hashlib
import unittest

from dashboard_contract_helpers import read_dashboard_styles
from tools.verify_css_split import (
    CSS_MODULES,
    EXPECTED_COMBINED_SHA256,
    INDEX,
    LEGACY_STYLESHEET,
    expected_legacy_manifest,
    verify,
)


class FrontendStylesheetTests(unittest.TestCase):
    def test_css_split_verifier_accepts_current_tree(self):
        verify()

    def test_combined_styles_preserve_original_content(self):
        combined = read_dashboard_styles().encode("utf-8")
        self.assertEqual(hashlib.sha256(combined).hexdigest(), EXPECTED_COMBINED_SHA256)
        self.assertIn("/* open-mmi dashboard ui pass 2: digital rpm gauge */", combined.decode())
        self.assertIn("/* --- Open MMI vehicle UI corrections end --- */", combined.decode())

    def test_index_loads_modules_once_in_cascade_order(self):
        html = INDEX.read_text(encoding="utf-8")
        positions = [
            html.index(f'<link rel="stylesheet" href="/{name}">')
            for name in CSS_MODULES
        ]
        self.assertEqual(positions, sorted(positions))
        for name in CSS_MODULES:
            self.assertEqual(html.count(f'href="/{name}"'), 1)
        self.assertNotIn('href="/styles.css"', html)

    def test_legacy_stylesheet_remains_a_compatible_manifest(self):
        self.assertEqual(
            LEGACY_STYLESHEET.read_text(encoding="utf-8"),
            expected_legacy_manifest(),
        )


if __name__ == "__main__":
    unittest.main()
