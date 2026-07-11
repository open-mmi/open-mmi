from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVER_PATH = Path(__file__).resolve().parents[1] / "ui/web_dashboard/server.py"
SPEC = importlib.util.spec_from_file_location("open_mmi_dashboard_server_bluetooth_test", SERVER_PATH)
server = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(server)


class BluetoothMediaTests(unittest.TestCase):
    def setUp(self):
        server._BLUETOOTH_ID_REGISTRY.clear()
        server._bluetooth_invalidate_cache()

    def test_busctl_scalar_and_track_parsing(self):
        self.assertEqual(server._bluetooth_parse_scalar('s "playing"'), "playing")
        self.assertEqual(server._bluetooth_parse_scalar("u 1234"), 1234)
        self.assertTrue(server._bluetooth_parse_scalar("b true"))
        track = server._bluetooth_parse_track(
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
        with mock.patch.object(server, "_bluetooth_busctl", return_value=tree):
            self.assertEqual(
                server._bluetooth_player_paths(),
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
            (path, "org.bluez.MediaPlayer1", "Name"): "Remote Player",
            ("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF", "org.bluez.Device1", "Alias"): "Pixel Phone",
        }

        def optional(candidate_path, interface, name, default=None):
            return properties.get((candidate_path, interface, name), default)

        with mock.patch.object(server, "_bluetooth_busctl_executable", return_value="/usr/bin/busctl"), \
             mock.patch.object(server, "_bluetooth_player_paths", return_value=[path]), \
             mock.patch.object(server, "_bluetooth_optional_property", side_effect=optional):
            payload = server._bluetooth_status_payload(force=True)

        self.assertTrue(payload["available"])
        self.assertRegex(payload["player_id"], r"^b[0-9a-f]{40}$")
        self.assertEqual(payload["track"]["name"], "Track One")
        self.assertEqual(payload["position_seconds"], 12.0)
        self.assertEqual(payload["duration_seconds"], 180.0)
        self.assertNotIn("AA_BB_CC", str(payload))
        self.assertFalse(payload["controls"]["seek"])

    def test_control_is_allowlisted_and_revalidates_current_player(self):
        path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0"
        player_id = server._bluetooth_player_id(path)
        calls = []

        def busctl(*args):
            calls.append(args)
            return ""

        with mock.patch.object(server, "_bluetooth_player_paths", return_value=[path]), \
             mock.patch.object(server, "_bluetooth_busctl", side_effect=busctl):
            result = server._bluetooth_control(player_id, "next")
            self.assertTrue(result["ok"])
            self.assertEqual(calls[-1][-1], "Next")
            with self.assertRaises(ValueError):
                server._bluetooth_control(player_id, "delete_everything")

        with mock.patch.object(server, "_bluetooth_player_paths", return_value=[]):
            with self.assertRaises(FileNotFoundError):
                server._bluetooth_control(player_id, "play")

    def test_play_pause_uses_current_remote_status(self):
        path = "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF/player0"
        player_id = server._bluetooth_player_id(path)
        calls = []
        with mock.patch.object(server, "_bluetooth_player_paths", return_value=[path]), \
             mock.patch.object(server, "_bluetooth_optional_property", return_value="playing"), \
             mock.patch.object(server, "_bluetooth_busctl", side_effect=lambda *args: calls.append(args) or ""):
            result = server._bluetooth_control(player_id, "play_pause")
        self.assertEqual(calls[-1][-1], "Pause")
        self.assertEqual(result["performed_action"], "pause")
        self.assertEqual(result["playback_status"], "paused")

    def test_frontend_routes_and_security_contract(self):
        root = SERVER_PATH.parents[2]
        app = (root / "ui/web_dashboard/static/app.js").read_text(encoding="utf-8")
        source = SERVER_PATH.read_text(encoding="utf-8")
        styles = (root / "ui/web_dashboard/static/styles.css").read_text(encoding="utf-8")
        self.assertIn('id: "bluetooth", label: "Bluetooth", note: "connected phone playback controls", planned: false', app)
        self.assertIn("api.adapters.bluetooth = bluetoothAdapter()", app)
        self.assertIn('fetch("/api/bluetooth/control"', app)
        self.assertIn('if parsed.path == "/api/bluetooth/status":', source)
        self.assertIn('if parsed.path != "/api/bluetooth/control":', source)
        self.assertIn('content_type != "application/json"', source)
        self.assertIn("_bluetooth_same_origin", source)
        self.assertIn("is-bluetooth-readonly", styles)
        self.assertIn('progress.classList.remove("is-bluetooth-readonly")', app)
        self.assertIn('selected_action not in _BLUETOOTH_ACTION_METHODS', source)
        self.assertIn('function effectivePlaybackStatus(', app)
        self.assertIn('function currentBluetoothPosition(', app)
        self.assertIn('function applyOptimisticControlState(', app)
        self.assertIn('function scheduleProgressTicker(', app)
        self.assertIn('applyOptimisticControlState(performedAction);', app)
        self.assertIn('clearProgressTicker();', app)
        self.assertIn('performed_action": method.lower()', source)
        self.assertIn('const performedAction = String(payload?.performed_action || action).toLowerCase();', app)
        self.assertIn('Dashboard-issued Bluetooth transport state is authoritative', app)
        self.assertNotIn("Release the pause latch only when playback", app)
        self.assertNotIn(
            "state.playbackOverridePosition = Math.max(state.playbackOverridePosition, serverPosition);",
            app,
        )
        self.assertIn('if (overrideStatus === "playing")', app)
        self.assertIn('(performance.now() - Number(state.playbackOverrideStartedAt', app)
        self.assertIn('function bluetoothPlayButtonAction()', app)
        self.assertIn('action = bluetoothPlayButtonAction();', app)
        self.assertNotIn('action = "play_pause";', app)
        self.assertIn('state.playbackOverride !== "playing"', app)
        self.assertIn('const remoteSeek = (', app)
        self.assertIn('serverDelta < -1.5', app)
        self.assertIn('serverDelta >= observedSeconds + 1.5', app)
        self.assertIn('Math.abs(drift) >= 4', app)
        self.assertIn('state.playbackOverridePosition = serverPosition;', app)


if __name__ == "__main__":
    unittest.main()
