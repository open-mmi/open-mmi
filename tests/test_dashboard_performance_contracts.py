"""Performance baseline contracts for the Open MMI dashboard.

Normal test runs are deterministic and do not make network requests. An
optional live comparison runs only when OPEN_MMI_PERF_BASE_URL is set.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "tools" / "dashboard_benchmark.py"
APP_JS_PATH = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
STATUS_JS_PATH = ROOT / "ui" / "web_dashboard" / "static" / "status.js"

spec = importlib.util.spec_from_file_location("dashboard_benchmark", BENCHMARK_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load {BENCHMARK_PATH}")
benchmark = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = benchmark
spec.loader.exec_module(benchmark)


class BenchmarkMathTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertEqual(benchmark.percentile([0, 10], 0.5), 5.0)
        self.assertAlmostEqual(benchmark.percentile([1, 2, 3, 4], 0.95), 3.85)

    def test_describe_empty_input(self):
        summary = benchmark.describe([])
        self.assertEqual(summary["count"], 0)
        self.assertIsNone(summary["p95"])

    def test_comparison_accepts_improvement(self):
        baseline = {
            "summary": {
                "failed_requests": 0,
                "request_ms": {"p95": 20.0},
                "completion_gap_ms": {"p95": 210.0},
                "schedule_lag_ms": {"p95": 5.0},
            }
        }
        candidate = {
            "summary": {
                "failed_requests": 0,
                "request_ms": {"p95": 15.0},
                "completion_gap_ms": {"p95": 200.0},
                "schedule_lag_ms": {"p95": 4.0},
            }
        }
        self.assertEqual(benchmark.compare_reports(baseline, candidate), [])

    def test_comparison_detects_regression(self):
        baseline = {
            "summary": {
                "failed_requests": 0,
                "request_ms": {"p95": 20.0},
                "completion_gap_ms": {"p95": 210.0},
                "schedule_lag_ms": {"p95": 5.0},
            }
        }
        candidate = {
            "summary": {
                "failed_requests": 1,
                "request_ms": {"p95": 30.0},
                "completion_gap_ms": {"p95": 300.0},
                "schedule_lag_ms": {"p95": 9.0},
            }
        }
        violations = benchmark.compare_reports(baseline, candidate)
        self.assertGreaterEqual(len(violations), 4)


class CurrentStatusPollingContractTests(unittest.TestCase):
    def setUp(self):
        self.app_source = APP_JS_PATH.read_text(encoding="utf-8")
        self.status_source = STATUS_JS_PATH.read_text(encoding="utf-8")

    def test_status_poll_reference_is_fixed_200ms_interval(self):
        self.assertIn(
            "const DEFAULT_STATUS_INTERVAL_MS = 200;",
            self.status_source,
            "The known-good baseline polls status every 200 ms. Update this contract "
            "only after collecting and approving a new tablet baseline.",
        )
        self.assertIn(
            "intervalMs: openMmiStatusClient.DEFAULT_STATUS_INTERVAL_MS",
            self.app_source,
        )

    def test_status_poll_is_not_completion_delayed(self):
        self.assertRegex(
            self.status_source,
            r"setInterval\s*\(\s*fetchStatus\s*,\s*intervalMs\s*\)",
        )
        self.assertIsNone(
            re.search(r"setTimeout\s*\(\s*fetchStatus\b", self.status_source),
            "A completion-delayed fetchStatus loop changed the effective telltale cadence.",
        )


@unittest.skipUnless(
    os.getenv("OPEN_MMI_PERF_BASE_URL"),
    "Set OPEN_MMI_PERF_BASE_URL to run live dashboard performance checks.",
)
class LiveDashboardPerformanceTests(unittest.TestCase):
    def test_live_status_probe_has_no_failures_and_matches_optional_baseline(self):
        report = benchmark.run_probe(
            base_url=os.environ["OPEN_MMI_PERF_BASE_URL"],
            endpoint=os.getenv("OPEN_MMI_PERF_ENDPOINT", "/api/status"),
            samples=int(os.getenv("OPEN_MMI_PERF_SAMPLES", "30")),
            interval_ms=float(os.getenv("OPEN_MMI_PERF_INTERVAL_MS", "200")),
            timeout=float(os.getenv("OPEN_MMI_PERF_TIMEOUT", "3")),
            workers=int(os.getenv("OPEN_MMI_PERF_WORKERS", "8")),
            warmup=3,
        )
        self.assertEqual(report["summary"]["failed_requests"], 0, report["errors"])

        baseline_path = os.getenv("OPEN_MMI_PERF_BASELINE")
        if not baseline_path:
            return

        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
        violations = benchmark.compare_reports(
            baseline,
            report,
            max_p95_regression=float(
                os.getenv("OPEN_MMI_PERF_MAX_P95_REGRESSION", "0.10")
            ),
            max_gap_regression=float(
                os.getenv("OPEN_MMI_PERF_MAX_GAP_REGRESSION", "0.20")
            ),
        )
        self.assertEqual(violations, [], "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
