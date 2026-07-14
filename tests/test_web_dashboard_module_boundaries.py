from __future__ import annotations

import inspect
import subprocess
import sys
import unittest
from pathlib import Path

from ui.web_dashboard import jellyfin, radio, server, usb


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


    def test_jellyfin_provider_does_not_depend_on_dashboard_handler(self):
        self.assertFalse(hasattr(jellyfin, "DashboardHandler"))
        source = inspect.getsource(jellyfin)
        self.assertNotIn("from ui.web_dashboard.server", source)
        self.assertNotIn("import server", source)

    def test_jellyfin_can_import_without_importing_server(self):
        command = (
            "import sys; "
            "import ui.web_dashboard.jellyfin; "
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

    def test_server_routes_delegate_to_jellyfin_provider(self):
        source = inspect.getsource(server.DashboardHandler.do_GET)
        self.assertIn("jellyfin_backend._jellyfin_status_payload(self.demo_mode)", source)
        self.assertIn("jellyfin_backend._jellyfin_search_payload(", source)
        self.assertIn("jellyfin_backend._jellyfin_proxy_audio(self, item_id)", source)
        self.assertIn("jellyfin_backend._jellyfin_proxy_image(self, item_id)", source)

    def test_private_jellyfin_server_aliases_remain_compatible_during_extraction(self):
        self.assertIs(server._jellyfin_config, jellyfin._jellyfin_config)
        self.assertIs(server._jellyfin_request_json, jellyfin._jellyfin_request_json)
        self.assertIs(server._jellyfin_proxy_audio, jellyfin._jellyfin_proxy_audio)
        self.assertIs(server._jellyfin_proxy_image, jellyfin._jellyfin_proxy_image)
        self.assertIs(server._JELLYFIN_LOGIN_CACHE, jellyfin._JELLYFIN_LOGIN_CACHE)


    def test_usb_provider_does_not_depend_on_dashboard_handler(self):
        self.assertFalse(hasattr(usb, "DashboardHandler"))
        source = inspect.getsource(usb)
        self.assertNotIn("from ui.web_dashboard.server", source)
        self.assertNotIn("import server", source)

    def test_usb_can_import_without_importing_server(self):
        command = (
            "import sys; "
            "import ui.web_dashboard.usb; "
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

    def test_server_routes_delegate_to_usb_provider(self):
        source = inspect.getsource(server.DashboardHandler.do_GET)
        self.assertIn("usb_backend._usb_status_payload()", source)
        self.assertIn("usb_backend._usb_browse_payload(", source)
        self.assertIn("usb_backend._usb_send_file(self, item_id)", source)
        self.assertIn(
            "usb_backend._usb_send_file(self, item_id, artwork=True)", source
        )

    def test_private_usb_server_aliases_remain_compatible_during_extraction(self):
        self.assertIs(server._usb_browse_payload, usb._usb_browse_payload)
        self.assertIs(server._usb_open_file, usb._usb_open_file)
        self.assertIs(server._usb_send_file, usb._usb_send_file)
        self.assertIs(server._USB_ID_REGISTRY, usb._USB_ID_REGISTRY)

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
