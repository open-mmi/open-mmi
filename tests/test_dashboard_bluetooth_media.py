from __future__ import annotations

import unittest
from unittest import mock

from dashboard_contract_helpers import (
    css_properties,
    implemented_source_ids,
    js_bool_property,
    js_object_with_id,
    js_string_property,
    read_repo_text,
)

from ui.web_dashboard import bluetooth, server


class BluetoothMediaTests(unittest.TestCase):
    def setUp(self):
        bluetooth._BLUETOOTH_ID_REGISTRY.clear()
        bluetooth._bluetooth_invalidate_cache()

    def test_busctl_scalar_and_track_parsing(self):
        self.assertEqual(bluetooth._bluetooth_parse_scalar('s "playing"'), "playing")
        self.assertEqual(bluetooth._bluetooth_parse_scalar("u 1234"), 1234)
        self.assertTrue(bluetooth._bluetooth_parse_scalar("b true"))
        track = bluetooth._bluetooth_parse_track(
            'a{sv} 4 "Title" s "Track One" "Artist" s "Artist Name" '
            '"Album" s "Album Name" "Duration" u 123456'
        )
        self.assertEqual(track["Title"], "Track One")
        self.assertEqual(track["Artist"], "Artist Name")
        self.assertEqual(track["Duration"], 123456)

    def test_player_paths_are_limited_to_bluez_media_players(self):
        tree = """/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0
/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/sep1
/org/other/player9
"""
        with mock.patch.object(bluetooth, "_bluetooth_busctl", return_value=tree):
            self.assertEqual(
                bluetooth._bluetooth_player_paths(),
                ["/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0"],
            )

    def test_status_uses_opaque_id_and_no_device_address(self):
        path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0"
        properties = {
            (path, "org.bluez.MediaPlayer1", "Status"): "playing",
            (path, "org.bluez.MediaPlayer1", "Position"): 12000,
            (path, "org.bluez.MediaPlayer1", "Track"): {
                "Title": "Track One",
                "Artist": "Artist",
                "Album": "Album",
                "Duration": 180000,
            },
            (path, "org.bluez.MediaPlayer1", "Device"): "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
            (path, "org.bluez.MediaPlayer1", "Name"): "Browser Player",
            ("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF", "org.bluez.Device1", "Alias"): "Pixel Phone",
        }

        def optional(candidate_path, interface, name, default=None):
            return properties.get((candidate_path, interface, name), default)

        with mock.patch.object(bluetooth, "_bluetooth_busctl_executable", return_value="/usr/bin/busctl"), \
             mock.patch.object(bluetooth, "_bluetooth_player_paths", return_value=[path]), \
             mock.patch.object(bluetooth, "_bluetooth_optional_property", side_effect=optional):
            payload = bluetooth._bluetooth_status_payload(force=True)

        self.assertTrue(payload["available"])
        self.assertRegex(payload["player_id"], r"^b[0-9a-f]{40}$")
        self.assertEqual(payload["track"]["name"], "Track One")
        self.assertEqual(payload["position_seconds"], 12.0)
        self.assertEqual(payload["duration_seconds"], 180.0)
        self.assertNotIn("AA_BB_CC", str(payload))
        self.assertFalse(payload["controls"]["seek"])

    def test_controls_are_allowlisted_revalidated_and_report_actual_action(self):
        path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0"
        player_id = bluetooth._bluetooth_player_id(path)
        calls: list[tuple] = []

        def busctl(*args):
            calls.append(args)
            return ""

        with mock.patch.object(bluetooth, "_bluetooth_player_paths", return_value=[path]), \
             mock.patch.object(bluetooth, "_bluetooth_busctl", side_effect=busctl):
            for action, method in (("play", "Play"), ("pause", "Pause"), ("next", "Next"), ("previous", "Previous"), ("stop", "Stop")):
                with self.subTest(action=action):
                    result = bluetooth._bluetooth_control(player_id, action)
                    self.assertTrue(result["ok"])
                    self.assertEqual(calls[-1][-1], method)
                    self.assertEqual(result.get("performed_action"), action)
            with self.assertRaises(ValueError):
                bluetooth._bluetooth_control(player_id, "delete_everything")

        with mock.patch.object(bluetooth, "_bluetooth_player_paths", return_value=[]):
            with self.assertRaises(FileNotFoundError):
                bluetooth._bluetooth_control(player_id, "play")

    def test_play_pause_uses_current_remote_status_and_reports_result(self):
        path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0"
        player_id = bluetooth._bluetooth_player_id(path)
        calls: list[tuple] = []
        with mock.patch.object(bluetooth, "_bluetooth_player_paths", return_value=[path]), \
             mock.patch.object(bluetooth, "_bluetooth_optional_property", return_value="playing"), \
             mock.patch.object(bluetooth, "_bluetooth_busctl", side_effect=lambda *args: calls.append(args) or ""):
            result = bluetooth._bluetooth_control(player_id, "play_pause")
        self.assertEqual(calls[-1][-1], "Pause")
        self.assertEqual(result.get("performed_action"), "pause")
        self.assertEqual(result.get("playback_status"), "paused")

    def test_frontend_registration_and_public_control_contract(self):
        bluetooth_frontend = read_repo_text("ui/web_dashboard/static/media-bluetooth.js")
        media = read_repo_text("ui/web_dashboard/static/media.js")
        descriptor = js_object_with_id(media, "bluetooth")
        self.assertEqual(js_string_property(descriptor, "label"), "Bluetooth")
        self.assertFalse(js_bool_property(descriptor, "planned"))
        self.assertIn("bluetooth", implemented_source_ids(media))

        self.assertIn("/api/bluetooth/control", bluetooth_frontend)
        self.assertRegex(bluetooth_frontend, r"['\"]pause['\"]")
        self.assertRegex(bluetooth_frontend, r"['\"]play['\"]")

    def test_routes_origin_json_and_readonly_progress_contract(self):
        bluetooth_frontend = read_repo_text("ui/web_dashboard/static/media-bluetooth.js")
        server_source = read_repo_text("ui/web_dashboard/server.py")
        provider_source = read_repo_text("ui/web_dashboard/bluetooth.py")
        styles = read_repo_text("ui/web_dashboard/static/styles.css")
        self.assertRegex(server_source, r"parsed\.path\s*==\s*['\"]/api/bluetooth/status['\"]")
        self.assertRegex(server_source, r"parsed\.path\s*!=\s*['\"]/api/bluetooth/control['\"]")
        self.assertRegex(provider_source, r"content_type\s*!=\s*['\"]application/json['\"]")
        self.assertIn("bluetooth_backend._bluetooth_same_origin", server_source)
        self.assertIn("_BLUETOOTH_ACTION_METHODS", provider_source)
        self.assertIn("apiClient.postJson(", bluetooth_frontend)
        self.assertIn('"/api/bluetooth/control"', bluetooth_frontend)
        props = css_properties(
            styles,
            "#openMmiMediaRoot #ommiMediaProgressTrack.is-bluetooth-readonly",
        )
        cursor = props.get("cursor", "").replace("!important", "").strip()
        self.assertEqual(cursor, "default")

if __name__ == "__main__":
    unittest.main()
