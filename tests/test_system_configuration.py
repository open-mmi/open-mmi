from __future__ import annotations

import contextlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import config_cli, configuration
from ui.web_dashboard import jellyfin, system_settings


class SystemConfigurationTests(unittest.TestCase):
    def test_environment_file_round_trip_is_private_and_omits_secrets_from_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config" / "dashboard.env"
            values = {
                "OPEN_MMI_JELLYFIN_URL": "https://jellyfin.test:8096",
                "OPEN_MMI_JELLYFIN_USERNAME": "driver",
                "OPEN_MMI_JELLYFIN_PASSWORD": 'secret "value"',
                "OPEN_MMI_JELLYFIN_LIBRARY_ID": "music-1",
            }
            configuration.write_environment_file(values, path)
            self.assertEqual(configuration.read_environment_file(path), values)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            with patch.object(configuration, "dashboard_env_path", return_value=path):
                status = configuration.jellyfin_environment_status(values, {})
            self.assertTrue(status["configured"])
            self.assertTrue(status["password_configured"])
            self.assertNotIn("password", json.dumps(status).lower().replace("password_configured", ""))
            self.assertNotIn("secret", json.dumps(status))

    def test_environment_writer_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "real"
            target.write_text("x", encoding="utf-8")
            link = root / "dashboard.env"
            link.symlink_to(target)
            with self.assertRaises(configuration.ConfigurationError):
                configuration.write_environment_file({"OPEN_MMI_JELLYFIN_URL": "https://x.test"}, link)

    def test_payload_preserves_existing_secret_and_switches_auth_modes(self):
        existing = {
            "OPEN_MMI_JELLYFIN_URL": "https://old.test",
            "OPEN_MMI_JELLYFIN_USERNAME": "driver",
            "OPEN_MMI_JELLYFIN_PASSWORD": "saved",
        }
        values = configuration.jellyfin_values_from_payload(
            {
                "url": "https://new.test/",
                "auth_mode": "username",
                "username": "driver",
                "password": "",
                "insecure_tls": False,
                "allow_global": False,
            },
            existing,
        )
        self.assertEqual(values["OPEN_MMI_JELLYFIN_PASSWORD"], "saved")
        self.assertEqual(values["OPEN_MMI_JELLYFIN_URL"], "https://new.test")

        token_values = configuration.jellyfin_values_from_payload(
            {"url": "https://new.test", "auth_mode": "token", "token": "abc", "username": "driver"},
            existing,
        )
        self.assertEqual(token_values["OPEN_MMI_JELLYFIN_TOKEN"], "abc")
        self.assertNotIn("OPEN_MMI_JELLYFIN_PASSWORD", token_values)

    def test_jellyfin_mapping_config_and_connection_test(self):
        config = jellyfin._jellyfin_config_from_mapping(
            {
                "OPEN_MMI_JELLYFIN_URL": "https://jellyfin.test",
                "OPEN_MMI_JELLYFIN_TOKEN": "token",
                "OPEN_MMI_JELLYFIN_USER_ID": "user-1",
            }
        )
        self.assertTrue(config["configured"])
        with patch.object(jellyfin, "_jellyfin_request_json", return_value={"ServerName": "Media", "Version": "10.9"}), patch.object(
            jellyfin, "_jellyfin_user_id", return_value="user-1"
        ):
            result = jellyfin._jellyfin_test_connection(config)
        self.assertEqual(result["server_name"], "Media")
        self.assertEqual(result["user_id"], "user-1")

    def test_system_requests_require_loopback_and_same_origin(self):
        class Handler:
            client_address = ("192.0.2.10", 1234)
            headers = {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}

        self.assertFalse(system_settings._request_allowed(Handler()))
        Handler.client_address = ("127.0.0.1", 1234)
        self.assertTrue(system_settings._request_allowed(Handler()))
        Handler.headers = {"Host": "127.0.0.1:8765", "Origin": "https://evil.test"}
        self.assertFalse(system_settings._request_allowed(Handler()))

    def test_launcher_update_uses_shared_launcher_configuration(self):
        with patch.object(system_settings.launcher, "save_preferences") as save, patch.object(
            system_settings.launcher, "configure_start_at_login"
        ) as configure, patch.object(system_settings, "_launcher_status", return_value={"default_ui": "tui"}):
            result = system_settings._update_launcher({"default_ui": "tui", "start_at_login": False})
        configure.assert_called_once_with(False)
        save.assert_called_once_with({"default_ui": "tui", "start_at_login": False})
        self.assertTrue(result["ok"])

    def test_cli_setup_writes_credentials_without_printing_secrets(self):
        values = {
            "OPEN_MMI_JELLYFIN_URL": "https://jellyfin.test",
            "OPEN_MMI_JELLYFIN_USERNAME": "driver",
            "OPEN_MMI_JELLYFIN_PASSWORD": "never-print-this",
        }
        output = io.StringIO()
        with patch.object(config_cli, "_setup_jellyfin", return_value=values), patch.object(
            config_cli, "_jellyfin_test", return_value={"connected": True}
        ), patch.object(config_cli, "write_environment_file") as write, patch.object(
            config_cli, "jellyfin_environment_status", return_value={
                "configured": True,
                "password_configured": True,
                "token_configured": False,
            }
        ), contextlib.redirect_stdout(output):
            result = config_cli.main(["jellyfin", "setup"])
        self.assertEqual(result, 0)
        write.assert_called_once_with(values)
        rendered = output.getvalue()
        self.assertIn('"configured": true', rendered.lower())
        self.assertNotIn("never-print-this", rendered)

    def test_cli_launcher_startup_uses_shared_launcher_helpers(self):
        output = io.StringIO()
        with patch.object(config_cli.launcher, "configure_start_at_login") as configure, patch.object(
            config_cli.launcher, "save_start_at_login"
        ) as save, patch.object(
            config_cli.launcher, "default_config_path", return_value=Path("/tmp/launcher.json")
        ), contextlib.redirect_stdout(output):
            result = config_cli.main(["launcher", "startup", "disable"])
        self.assertEqual(result, 0)
        configure.assert_called_once_with(False)
        save.assert_called_once_with(False, Path("/tmp/launcher.json"))
        self.assertIn('"start_at_login": false', output.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
