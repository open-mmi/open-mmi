from __future__ import annotations

import unittest

from dashboard_contract_helpers import at_rule_block, css_properties, marked_block, read_repo_text


class DashboardMediaControlVisualConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.styles = read_repo_text("ui/web_dashboard/static/styles.css")
        cls.block = marked_block(
            cls.styles,
            "/* --- Open MMI media control visual consistency start --- */",
            "/* --- Open MMI media control visual consistency end --- */",
        )

    def assertCssValue(self, source: str, selector: str, name: str, expected: str):
        properties = css_properties(source, selector)
        self.assertEqual(properties.get(name), expected.lower())

    def test_radio_facets_use_a_wide_second_row_and_narrow_fallback(self):
        selector = (
            "#openMmiMediaRoot.openmmi-media-source-radio "
            ".input-group:has(#ommiMediaFilter) > .ommi-radio-facets"
        )
        wide = self.block.split("@media", 1)[0]
        self.assertCssValue(wide, selector, "grid-row", "2")
        self.assertCssValue(wide, selector, "padding-inline-start", "10.88rem")
        narrow = at_rule_block(self.block, r"@media\s*\(\s*max-width\s*:\s*760px\s*\)")
        self.assertCssValue(narrow, selector, "grid-row", "3")
        self.assertCssValue(narrow, selector, "padding-inline-start", "0")

    def test_radio_selects_use_white_text_and_keylines(self):
        props = css_properties(
            self.block,
            "#openMmiMediaRoot.openmmi-media-source-radio .ommi-radio-facet-select",
        )
        self.assertEqual(props.get("-webkit-text-fill-color"), "#fff")
        self.assertIn(props.get("border-color"), {"#fff", "#fff !important"})

    def test_favourite_and_search_actions_use_white_keylines(self):
        for selector in ("#openMmiMediaRoot #ommiMediaFavoriteBtn", "#openMmiMediaRoot #ommiMediaSearchBtn"):
            with self.subTest(selector=selector):
                props = css_properties(self.block, selector)
                self.assertIn(props.get("border-color"), {"#fff", "#fff !important"})

    def test_disabled_favourite_mutes_only_the_icon(self):
        button = css_properties(self.block, "#openMmiMediaRoot #ommiMediaFavoriteBtn:disabled")
        icon = css_properties(self.block, "#openMmiMediaRoot #ommiMediaFavoriteBtn:disabled svg")
        self.assertIn(button.get("border-color"), {"#fff", "#fff !important"})
        self.assertIn(button.get("opacity"), {"1", "1 !important"})
        self.assertEqual(icon.get("opacity"), "0.55")

    def test_selected_favourite_changes_icon_not_button_surface(self):
        selected = css_properties(
            self.block,
            '#openMmiMediaRoot #ommiMediaFavoriteBtn[aria-pressed="true"]',
        )
        self.assertIn(
            selected.get("background-color"),
            {"transparent", "transparent !important"},
        )

    def test_transport_buttons_share_the_same_hover_surface(self):
        expected = "rgba(255, 255, 255, 0.12) !important"
        for control in ("Prev", "Next", "Stop"):
            selector = f"#openMmiMediaRoot #ommiMedia{control}:hover"
            with self.subTest(selector=selector):
                self.assertEqual(css_properties(self.block, selector).get("background-color"), expected)


if __name__ == "__main__":
    unittest.main()
