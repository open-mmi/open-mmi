import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "open_mmi_web_dashboard_server",
    ROOT / "ui" / "web_dashboard" / "server.py",
)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class JellyfinHardeningTests(unittest.TestCase):
    def config(self, **overrides):
        config = {
            "configured": True,
            "url": "https://jellyfin.test",
            "token": "test-token",
            "username": "",
            "password": "",
            "username_configured": False,
            "auth_mode": "token",
            "session_id": "",
            "device_name": "",
            "user_id": "user-1",
            "library_id": "library-1",
            "allow_global": False,
            "insecure_tls": False,
        }
        config.update(overrides)
        return config

    def test_config_reads_scope_controls(self):
        env = {
            "OPEN_MMI_JELLYFIN_URL": "https://jellyfin.test/",
            "OPEN_MMI_JELLYFIN_TOKEN": "token",
            "OPEN_MMI_JELLYFIN_USER_ID": "user-1",
            "OPEN_MMI_JELLYFIN_LIBRARY_ID": "library-1",
            "OPEN_MMI_JELLYFIN_ALLOW_GLOBAL": "0",
        }
        with patch.dict(os.environ, env, clear=True):
            config = server._jellyfin_config()
        self.assertTrue(config["configured"])
        self.assertEqual(config["url"], "https://jellyfin.test")
        self.assertEqual(config["user_id"], "user-1")
        self.assertEqual(config["library_id"], "library-1")
        self.assertEqual(config["auth_mode"], "token")
        self.assertFalse(config["allow_global"])

    def test_assigned_user_login_is_preserved_and_scoped(self):
        config = self.config(
            token="",
            username="open-mmi",
            password="secret",
            username_configured=True,
            auth_mode="username",
            user_id="",
        )
        with patch.object(
            server,
            "_jellyfin_login",
            return_value={"token": "login-token", "user_id": "assigned-1"},
        ):
            self.assertEqual(server._jellyfin_user_id(config), "assigned-1")
        self.assertEqual(config["user_id"], "assigned-1")

    def test_assigned_user_login_rejects_conflicting_user_override(self):
        config = self.config(
            token="",
            username="open-mmi",
            password="secret",
            username_configured=True,
            auth_mode="username",
            user_id="other-user",
        )
        with patch.object(
            server,
            "_jellyfin_login",
            return_value={"token": "login-token", "user_id": "assigned-1"},
        ):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                server._jellyfin_user_id(config)

    def test_user_scope_is_required_by_default(self):
        config = self.config(user_id="", allow_global=False)
        with patch.object(server, "_jellyfin_request_json", side_effect=RuntimeError("no /Users/Me")):
            with self.assertRaisesRegex(RuntimeError, "user scope is required"):
                server._jellyfin_user_id(config)

    def test_global_scope_is_explicit_opt_in(self):
        config = self.config(user_id="", allow_global=True)
        with patch.object(server, "_jellyfin_request_json", side_effect=RuntimeError("no /Users/Me")):
            self.assertIsNone(server._jellyfin_user_id(config))


    def test_api_key_can_resolve_exact_scope_username(self):
        config = self.config(user_id="", username="Open MMI")
        users = [
            {"Id": "other-1", "Name": "Other"},
            {"Id": "assigned-1", "Name": "open mmi"},
        ]
        with patch.object(server, "_jellyfin_request_json", return_value=users) as request:
            self.assertEqual(server._jellyfin_user_id(config), "assigned-1")
        request.assert_called_once_with(config, "/Users")
        self.assertEqual(config["user_id"], "assigned-1")

    def test_api_key_without_scope_has_clear_error(self):
        config = self.config(user_id="", username="", allow_global=False)
        with patch.object(server, "_jellyfin_request_json") as request:
            with self.assertRaisesRegex(RuntimeError, "API key"):
                server._jellyfin_user_id(config)
        request.assert_not_called()

    def test_auth_headers_include_jellyfin_compatibility_tokens(self):
        config = self.config()
        headers = server._jellyfin_auth_headers(config)
        self.assertEqual(headers["X-MediaBrowser-Token"], "test-token")
        self.assertEqual(headers["X-Emby-Token"], "test-token")

    def test_session_requires_exact_selector_and_matching_user(self):
        sessions = [
            {"Id": "one", "UserId": "other", "DeviceName": "Dashboard"},
            {"Id": "two", "UserId": "user-1", "DeviceName": "Dashboard Plus"},
            {"Id": "three", "UserId": "user-1", "DeviceName": "Dashboard"},
        ]
        config = self.config(device_name="dashboard")
        selected = server._pick_jellyfin_session(sessions, config, "user-1")
        self.assertEqual(selected["Id"], "three")
        self.assertIsNone(server._pick_jellyfin_session(sessions, self.config(), "user-1"))

    def test_search_scopes_and_filters_request(self):
        captured = {}

        def fake_request(config, path):
            captured["path"] = path
            return {
                "Items": [
                    {
                        "Id": "track-1",
                        "Type": "Audio",
                        "Name": "Track",
                        "Artists": ["Artist"],
                    }
                ]
            }

        with patch.object(server, "_jellyfin_config", return_value=self.config()), patch.object(
            server, "_jellyfin_request_json", side_effect=fake_request
        ):
            payload = server._jellyfin_search_payload("", 20, "favorites")

        params = parse_qs(urlparse(captured["path"]).query)
        self.assertEqual(params["UserId"], ["user-1"])
        self.assertEqual(params["ParentId"], ["library-1"])
        self.assertEqual(params["IsFavorite"], ["true"])
        self.assertEqual(params["SortBy"], ["SortName"])
        self.assertEqual(payload["filter"], "favorites")
        self.assertEqual(payload["items"][0]["id"], "track-1")

    def test_item_access_must_match_configured_scope(self):
        config = self.config()
        with patch.object(
            server,
            "_jellyfin_request_json",
            return_value={"Items": [{"Id": "track-1", "Type": "Audio"}]},
        ) as request:
            user_id = server._jellyfin_validate_item_access(config, "track-1")
        self.assertEqual(user_id, "user-1")
        path = request.call_args.args[1]
        params = parse_qs(urlparse(path).query)
        self.assertEqual(params["Ids"], ["track-1"])
        self.assertEqual(params["ParentId"], ["library-1"])

        with patch.object(server, "_jellyfin_request_json", return_value={"Items": []}):
            with self.assertRaises(PermissionError):
                server._jellyfin_validate_item_access(config, "track-2")

    def test_invalid_item_id_is_rejected(self):
        with self.assertRaises(ValueError):
            server._safe_jellyfin_id("../../etc/passwd")


if __name__ == "__main__":
    unittest.main()
