"""Static contracts for the repeated in-dashboard performance benchmark."""

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
        self.assertNotRegex(self.app_source, r"setTimeout\s*\(\s*fetchStatus\b")

    def test_suite_uses_existing_poll_and_three_measured_runs(self):
        self.assertIn("const STATUS_INTERVAL_MS = 200;", self.js)
        self.assertIn("const SAMPLES_PER_SCENARIO = 50;", self.js)
        self.assertIn("const RUNS_PER_SCENARIO = 3;", self.js)
        self.assertIn("const WARMUP_SAMPLES = 10;", self.js)
        self.assertIn("const REPORT_SCHEMA = 2;", self.js)
        self.assertIn("window.fetch = async function openMmiMeasuredFetch", self.js)
        self.assertNotRegex(self.js, r"setInterval\s*\(\s*fetchStatus")
        self.assertNotRegex(self.js, r"setTimeout\s*\(\s*fetchStatus")

    def test_scenarios_are_warmed_and_repeated_automatically(self):
        self.assertIn("captureScenarioRun(name, setup, 0, WARMUP_SAMPLES, true)", self.js)
        self.assertRegex(
            self.js,
            r"for \(let run = 1; run <= RUNS_PER_SCENARIO; run \+= 1\)",
        )
        self.assertIn('benchmarkScenario("home_idle"', self.js)
        self.assertIn('benchmarkScenario("media_jellyfin_browse"', self.js)
        self.assertIn('benchmarkScenario("media_radio_browse"', self.js)

    def test_aggregation_uses_run_medians_and_worst_run_guards(self):
        self.assertIn('benchmark_kind: "median_of_runs"', self.js)
        self.assertIn("result.worst_p95", self.js)
        self.assertIn("result.p95_spread", self.js)
        self.assertIn('aggregation: "median of run-level metrics with worst-run guard"', self.js)
        self.assertIn("check.worst_run", self.js)

    def test_unstable_runs_are_inconclusive_not_regressions(self):
        self.assertIn("stabilityForScenario", self.js)
        self.assertIn("passed: unstable ? null : !failed", self.js)
        self.assertIn("Run-to-run spread is too high", self.js)
        self.assertIn("Comparison is inconclusive", self.js)
        self.assertIn("is-warn", self.js)

    def test_only_stable_matching_reports_can_be_saved_or_compared(self):
        self.assertIn("reportIsStable", self.js)
        self.assertIn("if (!state.latest || !reportIsStable(state.latest)) return;", self.js)
        self.assertIn("baseline.disabled = !state.latest || state.running || !reportIsStable(state.latest)", self.js)
        self.assertIn("The saved baseline uses an older or different benchmark profile", self.js)
        self.assertIn("Saved baseline uses the older single-run format", self.js)

    def test_suite_restores_page_source_and_instrumentation(self):
        self.assertIn("const originalPage = currentPageId();", self.js)
        self.assertIn("const originalSource = activeSourceId();", self.js)
        self.assertIn("removeInstrumentation();", self.js)
        self.assertIn("setActiveSource?.(originalSource)", self.js)
        self.assertIn("showPage(originalPage);", self.js)
        self.assertRegex(self.js, r"finally\s*\{")

    def test_suite_does_not_start_media_or_use_document_observer(self):
        self.assertNotRegex(self.js, r"\.play\s*\(")
        self.assertNotIn("MutationObserver", self.js)

    def test_panel_is_accessible_and_before_live_refreshed_panel(self):
        self.assertIn('insertBefore(host, panel)', self.js)
        self.assertNotIn('insertAdjacentElement("afterend", host)', self.js)
        for control_id in (
            "openMmiPerformanceRun",
            "openMmiPerformanceDownload",
            "openMmiPerformanceSaveBaseline",
            "openMmiPerformanceClearBaseline",
            "openMmiPerformanceProgress",
        ):
            self.assertIn(control_id, self.js)
        self.assertIn('aria-live="polite"', self.js)
        self.assertIn("Run 3-pass suite", self.js)

    def test_report_remains_local_and_excludes_payloads(self):
        self.assertIn("localStorage.setItem(key, JSON.stringify(value))", self.js)
        self.assertIn("Status payloads, telltale values", self.js)
        self.assertNotIn("JSON.stringify(payload)", self.js)
        self.assertNotIn("/api/performance", self.js)

    def test_action_buttons_keep_readable_states(self):
        self.assertRegex(
            self.css,
            r"\.openmmi-perf-actions button\s*\{[^}]*border:\s*1px solid #fff",
        )
        self.assertRegex(
            self.css,
            r"\.openmmi-perf-actions button:hover,[^{]*\{[^}]*background:\s*#fff",
        )


if __name__ == "__main__":
    unittest.main()
