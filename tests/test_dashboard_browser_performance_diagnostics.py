"""Static contracts for the in-dashboard browser performance diagnostics."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
STYLES = ROOT / "ui" / "web_dashboard" / "static" / "styles.css"
JS_START = "// --- Open MMI browser performance diagnostics start ---"
JS_END = "// --- Open MMI browser performance diagnostics end ---"
CSS_START = "/* --- Open MMI browser performance diagnostics start --- */"
CSS_END = "/* --- Open MMI browser performance diagnostics end --- */"


def marked_block(source: str, start: str, end: str) -> str:
    start_index = source.find(start)
    end_index = source.find(end)
    if start_index < 0 or end_index < start_index:
        raise AssertionError(f"Could not find marked block {start!r} ... {end!r}")
    return source[start_index : end_index + len(end)]


class BrowserPerformanceDiagnosticsContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_JS.read_text(encoding="utf-8")
        cls.style_source = STYLES.read_text(encoding="utf-8")
        cls.js = marked_block(cls.app_source, JS_START, JS_END)
        cls.css = marked_block(cls.style_source, CSS_START, CSS_END)

    def test_known_good_status_cadence_is_not_changed(self):
        self.assertRegex(
            self.app_source,
            r"setInterval\s*\(\s*fetchStatus\s*,\s*200\s*\)",
        )
        self.assertNotRegex(
            self.app_source,
            r"setTimeout\s*\(\s*fetchStatus\b",
        )

    def test_suite_uses_existing_status_poll_without_starting_a_second_poll(self):
        self.assertIn('const STATUS_INTERVAL_MS = 200;', self.js)
        self.assertIn('const SAMPLES_PER_SCENARIO = 50;', self.js)
        self.assertIn('window.fetch = async function openMmiMeasuredFetch', self.js)
        self.assertNotRegex(self.js, r"setInterval\s*\(\s*fetchStatus")
        self.assertNotRegex(self.js, r"setTimeout\s*\(\s*fetchStatus")

    def test_suite_automates_pages_and_enabled_sources(self):
        self.assertIn('captureScenario("home_idle"', self.js)
        self.assertIn('captureScenario("media_jellyfin_browse"', self.js)
        self.assertIn('captureScenario("media_radio_browse"', self.js)
        self.assertIn('sourceEnabled("radio")', self.js)
        self.assertIn('activateSource("jellyfin")', self.js)
        self.assertIn('activateSource("radio")', self.js)

    def test_suite_restores_page_source_and_instrumentation(self):
        self.assertIn('const originalPage = currentPageId();', self.js)
        self.assertIn('const originalSource = activeSourceId();', self.js)
        self.assertIn('removeInstrumentation();', self.js)
        self.assertIn('setActiveSource?.(originalSource)', self.js)
        self.assertIn('showPage(originalPage);', self.js)
        self.assertRegex(self.js, r"finally\s*\{")

    def test_suite_does_not_start_media_or_use_a_document_observer(self):
        self.assertNotRegex(self.js, r"\.play\s*\(")
        self.assertNotIn("MutationObserver", self.js)

    def test_report_is_local_and_does_not_store_status_payloads(self):
        self.assertIn('localStorage.setItem(key, JSON.stringify(value))', self.js)
        self.assertIn('Status payloads, telltale values', self.js)
        self.assertNotIn('JSON.stringify(payload)', self.js)
        self.assertNotIn('/api/performance', self.js)


    def test_diagnostics_panel_is_before_live_refreshed_panel(self):
        self.assertIn('insertBefore(host, panel)', self.js)
        self.assertNotIn('insertAdjacentElement("afterend", host)', self.js)

    def test_settings_panel_has_accessible_actions_and_progress(self):
        for control_id in (
            "openMmiPerformanceRun",
            "openMmiPerformanceDownload",
            "openMmiPerformanceSaveBaseline",
            "openMmiPerformanceClearBaseline",
            "openMmiPerformanceProgress",
        ):
            self.assertIn(control_id, self.js)
        self.assertIn('aria-live="polite"', self.js)

    def test_action_buttons_have_explicit_readable_states(self):
        self.assertRegex(
            self.css,
            r"\.openmmi-perf-actions button\s*\{[^}]*border:\s*1px solid #fff",
        )
        self.assertRegex(
            self.css,
            r"\.openmmi-perf-actions button:hover,[^{]*\{[^}]*background:\s*#fff",
        )
        self.assertRegex(
            self.css,
            r"\.openmmi-perf-actions button:hover,[^{]*\{[^}]*color:\s*#10151d",
        )


if __name__ == "__main__":
    unittest.main()
