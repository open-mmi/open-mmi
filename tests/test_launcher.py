from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ui import launcher


class LauncherConfigTests(unittest.TestCase):
    def test_missing_config_uses_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = launcher.load_config(Path(directory) / "missing.json")
        self.assertEqual(config["default_ui"], "web")
        self.assertEqual(config["web_url"], "http://127.0.0.1:8765")

    def test_user_config_merges_over_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.json"
            path.write_text(json.dumps({"browser_mode": "window"}), encoding="utf-8")
            config = launcher.load_config(path)
        self.assertEqual(config["browser_mode"], "window")
        self.assertEqual(config["default_ui"], "web")

    def test_unknown_config_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.json"
            path.write_text(json.dumps({"surprise": True}), encoding="utf-8")
            with self.assertRaises(launcher.LauncherError):
                launcher.load_config(path)

    def test_save_default_ui_preserves_other_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.json"
            path.write_text(json.dumps({"browser_mode": "window"}), encoding="utf-8")
            launcher.save_default_ui("tui", path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload, {"browser_mode": "window", "default_ui": "tui"})


class LauncherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = dict(launcher.DEFAULT_CONFIG)
        self.config["startup_timeout_seconds"] = 0.2
        self.config["health_poll_interval_seconds"] = 0.1

    @staticmethod
    def result(returncode: int = 0, stdout: str = "", stderr: str = "") -> SimpleNamespace:
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_healthy_dashboard_is_not_restarted(self) -> None:
        commands: list[list[str]] = []

        def runner(args, *, capture_output=False):
            commands.append(list(args))
            return self.result()

        launcher.ensure_dashboard_ready(
            self.config,
            health_checker=lambda _url, _timeout: True,
            command_runner=runner,
            sleeper=lambda _seconds: None,
        )
        self.assertEqual(commands, [])

    def test_inactive_dashboard_is_started(self) -> None:
        checks = iter((False, True))
        commands: list[list[str]] = []

        def runner(args, *, capture_output=False):
            commands.append(list(args))
            if "is-active" in args:
                return self.result(returncode=3)
            return self.result()

        launcher.ensure_dashboard_ready(
            self.config,
            health_checker=lambda _url, _timeout: next(checks),
            command_runner=runner,
            sleeper=lambda _seconds: None,
        )
        self.assertIn(["systemctl", "--user", "start", launcher.SERVICE_NAME], commands)

    def test_active_unhealthy_dashboard_is_restarted(self) -> None:
        checks = iter((False, True))
        commands: list[list[str]] = []

        def runner(args, *, capture_output=False):
            commands.append(list(args))
            return self.result()

        launcher.ensure_dashboard_ready(
            self.config,
            health_checker=lambda _url, _timeout: next(checks),
            command_runner=runner,
            sleeper=lambda _seconds: None,
        )
        self.assertIn(["systemctl", "--user", "restart", launcher.SERVICE_NAME], commands)

    def test_startup_timeout_is_reported(self) -> None:
        def runner(args, *, capture_output=False):
            if "is-active" in args:
                return self.result(returncode=3)
            return self.result()

        with self.assertRaises(launcher.LauncherError):
            launcher.ensure_dashboard_ready(
                self.config,
                health_checker=lambda _url, _timeout: False,
                command_runner=runner,
                sleeper=lambda _seconds: None,
            )


class BrowserCommandTests(unittest.TestCase):
    def test_health_url_is_derived_without_fallback(self) -> None:
        self.assertEqual(
            launcher.health_url("http://127.0.0.1:8765"),
            "http://127.0.0.1:8765/api/health",
        )

    def test_chromium_kiosk_command(self) -> None:
        command = launcher.build_browser_command(
            ["/usr/bin/chromium"],
            "http://127.0.0.1:8765",
            "kiosk",
        )
        self.assertIn("--kiosk", command)
        self.assertIn("--app=http://127.0.0.1:8765", command)

    def test_explicit_placeholder_is_respected(self) -> None:
        command = launcher.build_browser_command(
            ["/custom/browser", "--open={url}"],
            "http://127.0.0.1:8765",
            "window",
        )
        self.assertEqual(command, ["/custom/browser", "--open=http://127.0.0.1:8765"])

    @patch("ui.launcher.shutil.which")
    def test_auto_browser_uses_first_available_candidate(self, which) -> None:
        which.side_effect = lambda name: "/usr/bin/chromium" if name == "chromium" else None
        self.assertEqual(launcher.resolve_browser("auto"), ["/usr/bin/chromium"])


if __name__ == "__main__":
    unittest.main()
