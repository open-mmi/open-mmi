import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from ui.web_dashboard import jellyfin



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
            config = jellyfin._jellyfin_config()
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
            jellyfin,
            "_jellyfin_login",
            return_value={"token": "login-token", "user_id": "assigned-1"},
        ):
            self.assertEqual(jellyfin._jellyfin_user_id(config), "assigned-1")
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
            jellyfin,
            "_jellyfin_login",
            return_value={"token": "login-token", "user_id": "assigned-1"},
        ):
            with self.assertRaisesRegex(RuntimeError, "does not match"):
                jellyfin._jellyfin_user_id(config)

    def test_user_scope_is_required_by_default(self):
        config = self.config(user_id="", allow_global=False)
        with patch.object(jellyfin, "_jellyfin_request_json", side_effect=RuntimeError("no /Users/Me")):
            with self.assertRaisesRegex(RuntimeError, "user scope is required"):
                jellyfin._jellyfin_user_id(config)

    def test_global_scope_is_explicit_opt_in(self):
        config = self.config(user_id="", allow_global=True)
        with patch.object(jellyfin, "_jellyfin_request_json", side_effect=RuntimeError("no /Users/Me")):
            self.assertIsNone(jellyfin._jellyfin_user_id(config))


    def test_api_key_can_resolve_exact_scope_username(self):
        config = self.config(user_id="", username="Open MMI")
        users = [
            {"Id": "other-1", "Name": "Other"},
            {"Id": "assigned-1", "Name": "open mmi"},
        ]
        with patch.object(jellyfin, "_jellyfin_request_json", return_value=users) as request:
            self.assertEqual(jellyfin._jellyfin_user_id(config), "assigned-1")
        request.assert_called_once_with(config, "/Users")
        self.assertEqual(config["user_id"], "assigned-1")

    def test_api_key_without_scope_has_clear_error(self):
        config = self.config(user_id="", username="", allow_global=False)
        with patch.object(jellyfin, "_jellyfin_request_json") as request:
            with self.assertRaisesRegex(RuntimeError, "API key"):
                jellyfin._jellyfin_user_id(config)
        request.assert_not_called()

    def test_auth_headers_include_jellyfin_compatibility_tokens(self):
        config = self.config()
        headers = jellyfin._jellyfin_auth_headers(config)
        self.assertEqual(headers["X-MediaBrowser-Token"], "test-token")
        self.assertEqual(headers["X-Emby-Token"], "test-token")

    def test_session_requires_exact_selector_and_matching_user(self):
        sessions = [
            {"Id": "one", "UserId": "other", "DeviceName": "Dashboard"},
            {"Id": "two", "UserId": "user-1", "DeviceName": "Dashboard Plus"},
            {"Id": "three", "UserId": "user-1", "DeviceName": "Dashboard"},
        ]
        config = self.config(device_name="dashboard")
        selected = jellyfin._pick_jellyfin_session(sessions, config, "user-1")
        self.assertEqual(selected["Id"], "three")
        self.assertIsNone(jellyfin._pick_jellyfin_session(sessions, self.config(), "user-1"))

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

        with patch.object(jellyfin, "_jellyfin_config", return_value=self.config()), patch.object(
            jellyfin, "_jellyfin_request_json", side_effect=fake_request
        ):
            payload = jellyfin._jellyfin_search_payload("", 20, "favorites")

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
            jellyfin,
            "_jellyfin_request_json",
            return_value={"Items": [{"Id": "track-1", "Type": "Audio"}]},
        ) as request:
            user_id = jellyfin._jellyfin_validate_item_access(config, "track-1")
        self.assertEqual(user_id, "user-1")
        path = request.call_args.args[1]
        params = parse_qs(urlparse(path).query)
        self.assertEqual(params["Ids"], ["track-1"])
        self.assertEqual(params["ParentId"], ["library-1"])

        with patch.object(jellyfin, "_jellyfin_request_json", return_value={"Items": []}):
            with self.assertRaises(PermissionError):
                jellyfin._jellyfin_validate_item_access(config, "track-2")

    def test_invalid_item_id_is_rejected(self):
        with self.assertRaises(ValueError):
            jellyfin._safe_jellyfin_id("../../etc/passwd")


    def test_status_classifies_unreachable_provider_as_retryable_reconnection(self):
        from urllib.error import URLError

        failure = RuntimeError("Jellyfin connection failed")
        failure.__cause__ = URLError("offline")
        with patch.object(jellyfin, "_jellyfin_config", return_value=self.config()), patch.object(
            jellyfin, "_jellyfin_user_id", side_effect=failure
        ):
            payload = jellyfin._jellyfin_status_payload()

        self.assertEqual(payload["connection_state"], "reconnecting")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["error_code"], "unreachable")

    def test_status_classifies_authentication_failure_without_retry(self):
        from urllib.error import HTTPError

        cause = HTTPError("https://jellyfin.test", 401, "Unauthorized", {}, None)
        failure = RuntimeError("Jellyfin HTTP 401")
        failure.__cause__ = cause
        with patch.object(jellyfin, "_jellyfin_config", return_value=self.config()), patch.object(
            jellyfin, "_jellyfin_user_id", side_effect=failure
        ):
            payload = jellyfin._jellyfin_status_payload()

        self.assertEqual(payload["connection_state"], "authentication-error")
        self.assertFalse(payload["retryable"])
        self.assertEqual(payload["error_code"], "authentication")

    def test_search_payload_exposes_recovery_state_without_secrets(self):
        from urllib.error import URLError

        failure = RuntimeError("Jellyfin connection failed")
        failure.__cause__ = URLError("offline")
        with patch.object(jellyfin, "_jellyfin_config", return_value=self.config()), patch.object(
            jellyfin, "_jellyfin_scope_params", side_effect=failure
        ):
            payload = jellyfin._jellyfin_search_payload()

        self.assertEqual(payload["connection_state"], "reconnecting")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["items"], [])
        self.assertNotIn("test-token", str(payload))

    def test_audio_proxy_treats_client_disconnect_as_normal_stream_end(self):
        class FakeResponse:
            status = 206
            headers = {
                "Content-Type": "audio/mpeg",
                "Content-Length": "5",
                "Content-Range": "bytes 0-4/5",
            }

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, _size):
                return b"audio"

        for disconnect_error in (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            with self.subTest(disconnect_error=disconnect_error.__name__):
                handler = MagicMock()
                handler.headers = {}
                handler.wfile.write.side_effect = disconnect_error("client disconnected")

                with patch.object(jellyfin, "_jellyfin_config", return_value=self.config()), patch.object(
                    jellyfin, "_jellyfin_validate_item_access", return_value="user-1"
                ), patch.object(
                    jellyfin, "_jellyfin_authenticated_urlopen", return_value=FakeResponse()
                ):
                    jellyfin._jellyfin_proxy_audio(handler, "track-1")

                handler.send_response.assert_called_once_with(206)
                handler.send_error.assert_not_called()
                handler.wfile.write.assert_called_once_with(b"audio")


if __name__ == "__main__":
    unittest.main()
