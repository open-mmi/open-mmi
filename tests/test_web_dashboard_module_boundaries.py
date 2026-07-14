from __future__ import annotations

import inspect
import subprocess
import sys
import unittest
from pathlib import Path

from ui.web_dashboard import radio, server


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "ui" / "web_dashboard" / "server.py"


class DashboardModuleBoundaryTests(unittest.TestCase):
    def test_radio_provider_does_not_depend_on_dashboard_handler(self):
        self.assertFalse(hasattr(radio, "DashboardHandler"))
        source = inspect.getsource(radio)
        self.assertNotIn("from ui.web_dashboard.server", source)
        self.assertNotIn("import server", source)

    def test_radio_can_import_without_importing_server(self):
        command = (
            "import sys; "
            "import ui.web_dashboard.radio; "
            "assert 'ui.web_dashboard.server' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_server_routes_delegate_to_radio_provider(self):
        source = inspect.getsource(server.DashboardHandler.do_GET)
        self.assertIn("radio_backend._radio_status_payload()", source)
        self.assertIn("radio_backend._radio_filter_options_payload()", source)
        self.assertIn("radio_backend._radio_search_payload(", source)
        self.assertIn("radio_backend._radio_proxy_audio(self, station_id)", source)

    def test_private_server_aliases_remain_compatible_during_extraction(self):
        self.assertIs(server._safe_radio_station_id, radio._safe_radio_station_id)
        self.assertIs(server._radio_open_stream, radio._radio_open_stream)
        self.assertIs(server._radio_proxy_audio, radio._radio_proxy_audio)

    def test_dashboard_still_runs_as_a_direct_script(self):
        result = subprocess.run(
            [sys.executable, str(SERVER_PATH), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Open MMI factory-style web dashboard", result.stdout)


if __name__ == "__main__":
    unittest.main()
