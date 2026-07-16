import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BrowserTestContracts(unittest.TestCase):
    def test_playwright_dependency_is_exactly_pinned(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        version = package["devDependencies"]["@playwright/test"]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertEqual(package["scripts"]["test:browser"], "playwright test")

    def test_playwright_configuration_keeps_failure_diagnostics(self) -> None:
        config = (ROOT / "playwright.config.js").read_text(encoding="utf-8")
        self.assertIn('screenshot: "only-on-failure"', config)
        self.assertIn('trace: "retain-on-failure"', config)
        self.assertIn('name: "dashboard-800x480"', config)
        self.assertIn('viewport: { width: 800, height: 480 }', config)

    def test_browser_suite_covers_driver_workflows_and_responsive_layouts(self) -> None:
        suite = (ROOT / "tests" / "browser" / "dashboard.spec.js").read_text(encoding="utf-8")
        for contract in (
            "buttons and keyboard",
            "door and reverse overlays",
            "settings persist",
            "media source selection persists",
            "narrow portrait",
            "captureRuntimeFailures",
        ):
            self.assertIn(contract, suite)

    def test_ci_installs_and_runs_managed_chromium(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("name: Playwright browser coverage", workflow)
        self.assertIn("run: npm ci", workflow)
        self.assertIn("npx playwright install --with-deps chromium", workflow)
        self.assertIn("run: npm run test:browser", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)

    def test_browser_outputs_are_ignored(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for path in ("node_modules/", "playwright-report/", "test-results/"):
            self.assertIn(path, ignored)


if __name__ == "__main__":
    unittest.main()
