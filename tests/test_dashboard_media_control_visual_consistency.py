from __future__ import annotations

import unittest
from pathlib import Path


class DashboardMediaControlVisualConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.styles = (
            Path(__file__).resolve().parents[1]
            / "ui"
            / "web_dashboard"
            / "static"
            / "styles.css"
        ).read_text(encoding="utf-8")
        start = cls.styles.index(
            "/* --- Open MMI media control visual consistency start --- */"
        )
        end = cls.styles.index(
            "/* --- Open MMI media control visual consistency end --- */",
            start,
        )
        cls.block = cls.styles[start:end]

    def test_radio_facets_share_second_row_on_wide_layouts(self):
        self.assertIn("> .ommi-radio-facets", self.block)
        self.assertIn("grid-row: 2;", self.block)
        self.assertIn("padding-inline-start: 10.88rem;", self.block)

    def test_radio_facets_wrap_on_narrow_layouts(self):
        self.assertIn("@media (max-width: 760px)", self.block)
        self.assertIn("grid-row: 3;", self.block)
        self.assertIn("padding-inline-start: 0;", self.block)

    def test_radio_select_text_and_keylines_are_explicitly_white(self):
        self.assertIn(".ommi-radio-facet-select", self.block)
        self.assertIn("-webkit-text-fill-color: #fff;", self.block)
        self.assertIn("border-color: #fff !important;", self.block)

    def test_favourite_and_search_actions_use_white_keylines(self):
        self.assertIn("#ommiMediaFavoriteBtn", self.block)
        self.assertIn("#ommiMediaSearchBtn", self.block)
        self.assertIn("outline-color: #fff !important;", self.block)

    def test_disabled_favourite_mutes_only_its_icon(self):
        disabled = self.block.index("#openMmiMediaRoot #ommiMediaFavoriteBtn:disabled {")
        icon = self.block.index("#openMmiMediaRoot #ommiMediaFavoriteBtn:disabled svg", disabled)
        excerpt = self.block[disabled:icon]
        self.assertIn("border-color: #fff !important;", excerpt)
        self.assertIn("opacity: 1 !important;", excerpt)
        self.assertIn("opacity: 0.55;", self.block[icon:])

    def test_selected_favourite_does_not_fill_the_button(self):
        selected = self.block.index(
            '#openMmiMediaRoot #ommiMediaFavoriteBtn[aria-pressed="true"] {'
        )
        hover = self.block.index(
            '#openMmiMediaRoot #ommiMediaFavoriteBtn[aria-pressed="true"]:hover',
            selected,
        )
        self.assertIn("background-color: transparent !important;", self.block[selected:hover])

    def test_transport_hover_surface_is_shared(self):
        self.assertIn("#openMmiMediaRoot #ommiMediaPrev:hover", self.block)
        self.assertIn("#openMmiMediaRoot #ommiMediaNext:hover", self.block)
        self.assertIn("#openMmiMediaRoot #ommiMediaStop:hover", self.block)
        self.assertIn("background-color: rgba(255, 255, 255, 0.12) !important;", self.block)


if __name__ == "__main__":
    unittest.main()
