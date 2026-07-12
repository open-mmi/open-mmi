from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "ui" / "web_dashboard" / "static" / "index.html"
APP = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
STYLES = ROOT / "ui" / "web_dashboard" / "static" / "styles.css"


class _ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._current = None
        self.articles = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article" and self._depth == 0:
            self._depth = 1
            self._current = {"text": [], "data_fields": set(), "data_bools": set()}
        elif self._depth:
            self._depth += 1
        if self._current is not None:
            if "data-field" in attrs:
                self._current["data_fields"].add(attrs["data-field"])
            if "data-bool" in attrs:
                self._current["data_bools"].add(attrs["data-bool"])

    def handle_endtag(self, tag):
        if not self._depth:
            return
        self._depth -= 1
        if self._depth == 0 and self._current is not None:
            self._current["text"] = " ".join(" ".join(self._current["text"]).split())
            self.articles.append(self._current)
            self._current = None

    def handle_data(self, data):
        if self._current is not None and data.strip():
            self._current["text"].append(data)


class DashboardVehicleUiContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text(encoding="utf-8")
        cls.app = APP.read_text(encoding="utf-8")
        cls.styles = STYLES.read_text(encoding="utf-8")
        parser = _ArticleParser()
        parser.feed(cls.index)
        cls.articles = parser.articles

    def test_climate_page_uses_recirculation_and_omits_inactive_air_intake(self):
        recirculation = [
            article for article in self.articles
            if "recirculation" in article["data_bools"]
        ]
        self.assertEqual(len(recirculation), 1)
        self.assertIn("Re-circulation", recirculation[0]["text"])
        self.assertFalse(any("front_demist" in item["data_bools"] for item in self.articles))
        self.assertFalse(any("air_intake" in item["data_fields"] for item in self.articles))

    def test_range_field_is_kept_unknown_until_the_frame_is_verified(self):
        self.assertTrue(any("range_mi" in item["data_fields"] for item in self.articles))
        self.assertRegex(
            self.app,
            r"setField\(\s*['\"]range_mi['\"]\s*,\s*['\"]--['\"]\s*\)",
        )

    def test_rpm_fill_clips_a_fixed_track_gradient(self):
        self.assertIn('setProperty("--rpm-fill"', self.app)
        start = self.styles.index("/* --- Open MMI vehicle UI corrections start --- */")
        end = self.styles.index("/* --- Open MMI vehicle UI corrections end --- */", start)
        block = self.styles[start:end]
        self.assertIn("clip-path: inset", block)
        self.assertIn("var(--rpm-fill)", block)
        self.assertIn("rgba(255, 60, 56, 1) 86% 100%", block)
        self.assertIn("transform: none !important", block)

    def test_blower_panel_uses_rectangular_card_geometry(self):
        start = self.styles.index("/* --- Open MMI vehicle UI corrections start --- */")
        end = self.styles.index("/* --- Open MMI vehicle UI corrections end --- */", start)
        block = self.styles[start:end]
        rule = re.search(r"\.blower-card\s*\{(?P<body>.*?)\}", block, re.S)
        self.assertIsNotNone(rule)
        body = rule.group("body")
        self.assertIn("width: 100% !important", body)
        self.assertIn("aspect-ratio: auto !important", body)
        self.assertIn("border-radius: 16px !important", body)
        self.assertNotIn("border-radius: 50%", body)


if __name__ == "__main__":
    unittest.main()
