"""Regression tests for the in-dashboard browser benchmark methodology."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
DOCS = ROOT / "docs" / "performance-testing.md"

JS_START = "// --- Open MMI browser performance diagnostics start ---"
JS_END = "// --- Open MMI browser performance diagnostics end ---"


def marked_block(source: str, start: str, end: str) -> str:
    left = source.find(start)
    right = source.find(end)
    if left < 0 or right < left:
        raise AssertionError(f"Missing marked block: {start} ... {end}")
    return source[left:right + len(end)]


class BrowserPerformanceMethodologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP.read_text(encoding="utf-8")
        cls.js = marked_block(cls.app_source, JS_START, JS_END)
        cls.docs = DOCS.read_text(encoding="utf-8")

    def test_known_good_status_poll_is_unchanged(self):
        self.assertRegex(
            self.app_source,
            r"setInterval\s*\(\s*fetchStatus\s*,\s*200\s*\)",
        )
        self.assertNotRegex(
            self.app_source,
            r"setTimeout\s*\(\s*fetchStatus\b",
        )

    def test_schema_uses_one_cold_activation_and_five_warm_runs(self):
        self.assertIn("const REPORT_SCHEMA = 3;", self.js)
        self.assertIn("const RUNS_PER_SCENARIO = 5;", self.js)
        self.assertIn("const REQUIRED_PASSING_RUNS = 4;", self.js)
        self.assertIn("const WARMUP_SAMPLES = 10;", self.js)
        self.assertIn("const SAMPLES_PER_SCENARIO = 50;", self.js)
        self.assertIn(
            'benchmark_kind: "cold_activation_plus_five_warm_runs"',
            self.js,
        )

    def test_source_activation_is_not_repeated_for_each_measured_run(self):
        benchmark = re.search(
            r"async function benchmarkScenario\(name, setup\)\s*\{(?P<body>.*?)\n  \}",
            self.js,
            re.S,
        )
        self.assertIsNotNone(benchmark)
        body = benchmark.group("body")
        self.assertEqual(body.count("const coldSetup = await setup();"), 1)
        self.assertIn("const settledSetup = async () => ({", body)
        self.assertIn("captureScenarioRun(\n        name,\n        settledSetup,", body)
        self.assertNotIn("captureScenarioRun(name, setup,", body)

    def test_cold_readiness_is_reported_separately(self):
        self.assertIn("availability:", self.js)
        self.assertIn('category: "availability"', self.js)
        self.assertIn("Source did not become ready", self.js)
        self.assertIn("A source failed its cold activation check", self.js)
        self.assertIn("<dt>Cold activation</dt>", self.js)

    def test_comparison_requires_four_of_five_runs(self):
        self.assertIn("passed_runs: passedRuns", self.js)
        self.assertIn("required_runs: REQUIRED_PASSING_RUNS", self.js)
        self.assertIn("passedRuns >= REQUIRED_PASSING_RUNS", self.js)
        self.assertIn(
            'aggregation: "one cold activation plus five warm runs; four-of-five agreement"',
            self.js,
        )
        self.assertIn(
            "At least four of five runs are within the saved baseline",
            self.js,
        )
        self.assertIn(
            "Fewer than four of five runs met the saved baseline",
            self.js,
        )

    def test_self_comparison_uses_fourth_best_baseline_run(self):
        self.assertIn(
            "const sortedBaselineRuns = [...baselineRuns].sort",
            self.js,
        )
        self.assertIn(
            "const baselineAcceptanceAnchor = sortedBaselineRuns[REQUIRED_PASSING_RUNS - 1];",
            self.js,
        )
        self.assertIn(
            "baseline_acceptance_anchor: round(baselineAcceptanceAnchor)",
            self.js,
        )
        self.assertIn(
            "baselineAcceptanceAnchor * (1 + allowedRatio)",
            self.js,
        )
        self.assertNotIn(
            "const limit = Math.max(oldValue * (1 + allowedRatio)",
            self.js,
        )

        # Representative report from the regression: the median is 12, but
        # four-of-five acceptance must anchor at the fourth-best value, 14.55.
        baseline_runs = sorted([12, 11, 15.55, 11, 14.55])
        anchor = baseline_runs[4 - 1]
        limit = max(anchor * 1.10, anchor + 5)
        self.assertEqual(anchor, 14.55)
        self.assertGreaterEqual(
            sum(value <= limit for value in baseline_runs),
            4,
        )

    def test_low_latency_metrics_use_absolute_tolerance_floor(self):
        self.assertIn("absoluteToleranceMs = 0", self.js)
        self.assertIn(
            "const relativeLimit = baselineAcceptanceAnchor * (1 + allowedRatio);",
            self.js,
        )
        self.assertIn(
            "const absoluteLimit = baselineAcceptanceAnchor",
            self.js,
        )
        self.assertIn("const limit = Math.max(relativeLimit, absoluteLimit);", self.js)
        self.assertIn("absolute_tolerance_ms: round(absoluteToleranceMs)", self.js)
        self.assertIn(
            'compareMetric(old, scenario, "request_ms", "p95", 0.10, 5)',
            self.js,
        )
        self.assertIn(
            'compareMetric(old, scenario, "response_to_paint_ms", "p95", 0.10, 5)',
            self.js,
        )
        self.assertIn(
            'compareMetric(old, scenario, "paint_gap_ms", "p95", 0.20, 0)',
            self.js,
        )

        # The independent comparison that exposed the calibration problem:
        # a 13 ms baseline anchor and 15 ms candidate should remain acceptable.
        anchor = 13
        limit = max(anchor * 1.10, anchor + 5)
        candidate_runs = [16, 15, 15.55, 13, 12.55]
        self.assertEqual(limit, 18)
        self.assertGreaterEqual(sum(value <= limit for value in candidate_runs), 4)

    def test_inconclusive_requires_insufficient_valid_runs(self):
        self.assertIn("valid_run_count", self.js)
        self.assertIn("Only ${Number(scenario.valid_run_count || 0)}", self.js)
        self.assertIn(
            "Comparison is inconclusive because fewer than four warm runs were valid",
            self.js,
        )
        self.assertNotIn(
            "Run-to-run spread is too high for a reliable comparison",
            self.js,
        )

    def test_baseline_profile_must_match_methodology(self):
        self.assertIn(
            "Number(baseline.configuration?.required_passing_runs) === REQUIRED_PASSING_RUNS",
            self.js,
        )
        self.assertIn("reportIsStable", self.js)
        self.assertIn(
            "scenario.valid_run_count >= REQUIRED_PASSING_RUNS",
            self.js,
        )

    def test_settings_copy_describes_robust_suite(self):
        self.assertIn("Run robust suite", self.js)
        self.assertIn(
            "One cold activation and five warm runs per scenario",
            self.js,
        )
        self.assertIn("Four matching runs are required", self.js)
        self.assertIn("Allow about three minutes", self.js)

    def test_runner_remains_non_invasive(self):
        self.assertNotRegex(self.js, r"\.play\s*\(")
        self.assertNotIn("MutationObserver", self.js)
        self.assertIn("showPage(originalPage);", self.js)
        self.assertIn("setActiveSource?.(originalSource)", self.js)
        self.assertIn("insertBefore(host, panel)", self.js)

    def test_docs_explain_cold_and_warm_measurements(self):
        self.assertIn("one **cold activation** measurement", self.docs)
        self.assertIn("**five warm measured runs", self.docs)
        self.assertIn("four of five", self.docs.lower())
        self.assertIn("availability failure", self.docs.lower())


if __name__ == "__main__":
    unittest.main()
