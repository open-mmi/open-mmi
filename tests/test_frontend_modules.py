from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "ui" / "web_dashboard" / "static"
INDEX = STATIC / "index.html"
APP = STATIC / "app.js"
API = STATIC / "api.js"
PREFERENCES = STATIC / "preferences.js"


class FrontendModuleBoundaryTests(unittest.TestCase):
    def test_modules_load_before_application(self):
        html = INDEX.read_text(encoding="utf-8")
        api_index = html.index('<script src="/api.js"></script>')
        preferences_index = html.index('<script src="/preferences.js"></script>')
        app_index = html.index('<script src="/app.js"></script>')
        self.assertLess(api_index, preferences_index)
        self.assertLess(preferences_index, app_index)

    def test_application_uses_frontend_modules(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("window.openMmiApi", source)
        self.assertIn("window.openMmiPreferences", source)
        self.assertIn('openMmiApiClient.getJson("/api/status"', source)
        self.assertIn("openMmiApiClient.postJson(", source)
        self.assertNotIn("localStorage.", source)

    def test_modules_are_browser_and_commonjs_compatible(self):
        api = API.read_text(encoding="utf-8")
        preferences = PREFERENCES.read_text(encoding="utf-8")
        for source, global_name in (
            (api, "openMmiApi"),
            (preferences, "openMmiPreferences"),
        ):
            self.assertIn("typeof module === \"object\"", source)
            self.assertIn(f"root.{global_name}", source)
            self.assertNotIn("document.", source)

    def test_api_reads_fetch_at_call_time_for_instrumentation(self):
        source = API.read_text(encoding="utf-8")
        self.assertIn("const fetchImpl = root && root.fetch", source)
        self.assertNotIn("const fetchImpl = root.fetch.bind", source)


if __name__ == "__main__":
    unittest.main()
