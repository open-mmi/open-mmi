from __future__ import annotations

import importlib.util
import io
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from ui.web_dashboard import jellyfin, radio, usb

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "ui" / "web_dashboard" / "server.py"
SPEC = importlib.util.spec_from_file_location(
    "open_mmi_web_dashboard_external_boundaries", SERVER_PATH
)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


class FakeResponse:
    def __init__(self, body=b"", *, status=200, headers=None, reason="OK"):
        self._body = io.BytesIO(body)
        self.status = status
        self.headers = dict(headers or {})
        self.reason = reason
        self.closed = False

    def read(self, size=-1):
        return self._body.read(size)

    def close(self):
        self.closed = True
        self._body.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.requests = []
        self.closed = False

    def request(self, method, path, headers=None):
        self.requests.append((method, path, dict(headers or {})))

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class FakeHandler:
    def __init__(self, *, range_header=None):
        self.headers = {}
        if range_header is not None:
            self.headers["Range"] = range_header
        self.responses = []
        self.sent_headers = []
        self.errors = []
        self.wfile = io.BytesIO()
        self.ended = False

    def send_response(self, status):
        self.responses.append(status)

    def send_header(self, name, value):
        self.sent_headers.append((name, str(value)))

    def end_headers(self):
        self.ended = True

    def send_error(self, status, message=None):
        self.errors.append((status, str(message or "")))


class RadioPinnedConnectionTests(unittest.TestCase):
    def config(self):
        return {
            "allow_private_streams": False,
            "stream_timeout": 1.0,
            "user_agent": "Open-MMI-Test",
        }

    def test_stream_connection_uses_the_validated_address_without_second_dns_lookup(self):
        public = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))
        ]
        connection = FakeConnection(
            FakeResponse(b"audio", headers={"Content-Type": "audio/mpeg"})
        )
        with patch.object(radio, "_radio_config", return_value=self.config()), patch(
            "socket.getaddrinfo", return_value=public
        ) as resolve, patch.object(
            radio, "_radio_connection", return_value=connection
        ) as connect:
            response = radio._radio_open_stream("http://radio.example/live?quality=high")

        self.assertEqual(resolve.call_count, 1)
        target, address, timeout = connect.call_args.args
        self.assertEqual(address[2], ("93.184.216.34", 80))
        self.assertEqual(target["hostname"], "radio.example")
        self.assertEqual(target["path"], "/live?quality=high")
        self.assertEqual(timeout, 1.0)
        self.assertEqual(connection.requests[0][0:2], ("GET", "/live?quality=high"))
        response.close()
        self.assertTrue(connection.closed)

    def test_redirect_target_is_resolved_and_rejected_before_connecting(self):
        public = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))
        ]
        private = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 80))
        ]
        redirect = FakeConnection(
            FakeResponse(
                status=302,
                headers={"Location": "http://private.example/live"},
                reason="Found",
            )
        )
        with patch.object(radio, "_radio_config", return_value=self.config()), patch(
            "socket.getaddrinfo", side_effect=[public, private]
        ) as resolve, patch.object(
            radio, "_radio_connection", return_value=redirect
        ) as connect:
            with self.assertRaises(PermissionError):
                radio._radio_open_stream("http://radio.example/live")

        self.assertEqual(resolve.call_count, 2)
        self.assertEqual(connect.call_count, 1)
        self.assertTrue(redirect.closed)

    def test_invalid_redirects_fail_as_upstream_errors(self):
        public = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))
        ]
        missing_location = FakeConnection(FakeResponse(status=302, headers={}))
        with patch.object(radio, "_radio_config", return_value=self.config()), patch(
            "socket.getaddrinfo", return_value=public
        ), patch.object(radio, "_radio_connection", return_value=missing_location):
            with self.assertRaisesRegex(RuntimeError, "no Location"):
                radio._radio_open_stream("http://radio.example/live")

        redirects = [
            FakeConnection(
                FakeResponse(
                    status=302,
                    headers={"Location": "http://radio.example/live"},
                )
            )
            for _ in range(6)
        ]
        with patch.object(radio, "_radio_config", return_value=self.config()), patch(
            "socket.getaddrinfo", return_value=public
        ), patch.object(radio, "_radio_connection", side_effect=redirects):
            with self.assertRaisesRegex(RuntimeError, "redirect limit"):
                radio._radio_open_stream("http://radio.example/live")

    def test_mixed_public_and_private_dns_answers_are_rejected(self):
        mixed = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 80)),
        ]
        with patch("socket.getaddrinfo", return_value=mixed):
            with self.assertRaises(PermissionError):
                radio._radio_resolve_stream_target("http://radio.example/live")

    def test_pinned_http_connection_connects_to_numeric_sockaddr(self):
        target = {
            "scheme": "http",
            "hostname": "radio.example",
            "port": 80,
        }
        address = (socket.AF_INET, socket.IPPROTO_TCP, ("93.184.216.34", 80))
        fake_socket = Mock()
        with patch("socket.socket", return_value=fake_socket), patch(
            "socket.getaddrinfo"
        ) as resolve:
            connection = radio._radio_connection(target, address, 2.5)
            connection.connect()

        resolve.assert_not_called()
        fake_socket.settimeout.assert_called_once_with(2.5)
        fake_socket.connect.assert_called_once_with(("93.184.216.34", 80))
        self.assertIs(connection.sock, fake_socket)

    def test_pinned_https_connection_preserves_hostname_for_tls_sni(self):
        target = {
            "scheme": "https",
            "hostname": "secure-radio.example",
            "port": 443,
        }
        address = (socket.AF_INET, socket.IPPROTO_TCP, ("93.184.216.34", 443))
        fake_socket = Mock()
        wrapped_socket = Mock()
        context = Mock()
        context.wrap_socket.return_value = wrapped_socket
        with patch("socket.socket", return_value=fake_socket):
            connection = radio._radio_connection(target, address, 3.0)
            connection._context = context
            connection.connect()

        context.wrap_socket.assert_called_once_with(
            fake_socket, server_hostname="secure-radio.example"
        )
        self.assertIs(connection.sock, wrapped_socket)


class JellyfinBoundaryTests(unittest.TestCase):
    def setUp(self):
        jellyfin._JELLYFIN_LOGIN_CACHE.clear()

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

    def test_bounded_reader_rejects_declared_and_streamed_oversize_responses(self):
        declared = FakeResponse(
            b"small", headers={"Content-Length": str(jellyfin.JELLYFIN_JSON_MAX_BYTES + 1)}
        )
        with self.assertRaisesRegex(RuntimeError, "exceeded"):
            jellyfin._read_bounded_response(
                declared, jellyfin.JELLYFIN_JSON_MAX_BYTES, "Jellyfin JSON response"
            )

        streamed = FakeResponse(b"x" * 17)
        with self.assertRaisesRegex(RuntimeError, "exceeded"):
            jellyfin._read_bounded_response(streamed, 16, "response")

    def test_login_cache_identity_changes_when_password_changes(self):
        first = self.config(
            token="",
            username="open-mmi",
            password="first-secret",
            username_configured=True,
            auth_mode="username",
        )
        second = dict(first, password="second-secret")
        first_key = jellyfin._jellyfin_login_cache_key(first)
        second_key = jellyfin._jellyfin_login_cache_key(second)
        self.assertNotEqual(first_key, second_key)
        self.assertNotIn("first-secret", first_key)
        self.assertNotIn("second-secret", second_key)

    def test_expired_login_entries_are_pruned(self):
        jellyfin._JELLYFIN_LOGIN_CACHE.update(
            {
                "expired": {"token": "old", "cached_at": 0.0},
                "current": {"token": "new", "cached_at": 950.0},
            }
        )
        jellyfin._jellyfin_prune_login_cache(1000.0)
        self.assertNotIn("expired", jellyfin._JELLYFIN_LOGIN_CACHE)
        self.assertIn("current", jellyfin._JELLYFIN_LOGIN_CACHE)

    def test_expired_login_cache_is_replaced(self):
        config = self.config(
            token="",
            username="open-mmi",
            password="secret",
            username_configured=True,
            auth_mode="username",
        )
        key = jellyfin._jellyfin_login_cache_key(config)
        jellyfin._JELLYFIN_LOGIN_CACHE[key] = {
            "token": "expired-token",
            "user_id": "user-1",
            "user_name": "Open MMI",
            "cached_at": 0.0,
        }
        body = b'{"AccessToken":"fresh-token","User":{"Id":"user-1","Name":"Open MMI"}}'
        response = FakeResponse(body, headers={"Content-Length": str(len(body))})
        with patch.object(jellyfin.time, "monotonic", return_value=1000.0), patch.object(
            jellyfin, "_jellyfin_urlopen", return_value=response
        ) as open_url:
            login = jellyfin._jellyfin_login(config)

        self.assertEqual(login["token"], "fresh-token")
        self.assertNotIn("cached_at", login)
        self.assertEqual(jellyfin._JELLYFIN_LOGIN_CACHE[key]["token"], "fresh-token")
        open_url.assert_called_once()

    def test_username_auth_retries_once_after_unauthorized_response(self):
        config = self.config(
            token="cached-token",
            username="open-mmi",
            password="secret",
            username_configured=True,
            auth_mode="username",
        )
        unauthorized = HTTPError(
            "https://jellyfin.test/Users/Me",
            401,
            "Unauthorized",
            {},
            io.BytesIO(b"expired"),
        )
        response = FakeResponse(b'{"Id":"user-1"}', headers={"Content-Length": "15"})
        with patch.object(
            jellyfin,
            "_jellyfin_auth_headers",
            side_effect=[{"Authorization": "old"}, {"Authorization": "new"}],
        ), patch.object(
            jellyfin, "_jellyfin_urlopen", side_effect=[unauthorized, response]
        ) as open_url, patch.object(
            jellyfin, "_jellyfin_invalidate_login", wraps=jellyfin._jellyfin_invalidate_login
        ) as invalidate:
            payload = jellyfin._jellyfin_request_json(config, "/Users/Me")

        self.assertEqual(payload["Id"], "user-1")
        self.assertEqual(open_url.call_count, 2)
        invalidate.assert_called_once_with(config)

    def test_image_proxy_rejects_non_image_and_oversized_upstream_content(self):
        config = self.config()
        for response, phrase in [
            (
                FakeResponse(b"<html>", headers={"Content-Type": "text/html"}),
                "unsupported image type",
            ),
            (
                FakeResponse(
                    b"",
                    headers={
                        "Content-Type": "image/jpeg",
                        "Content-Length": str(jellyfin.JELLYFIN_IMAGE_MAX_BYTES + 1),
                    },
                ),
                "exceeded",
            ),
        ]:
            handler = FakeHandler()
            with self.subTest(phrase=phrase), patch.object(
                jellyfin, "_jellyfin_config", return_value=dict(config)
            ), patch.object(
                jellyfin, "_jellyfin_validate_item_access", return_value="user-1"
            ), patch.object(
                jellyfin, "_jellyfin_authenticated_urlopen", return_value=response
            ):
                jellyfin._jellyfin_proxy_image(handler, "track-1")
            self.assertEqual(handler.errors[0][0], 502)
            self.assertIn(phrase, handler.errors[0][1])
            self.assertEqual(handler.wfile.getvalue(), b"")

    def test_image_proxy_accepts_allowlisted_bounded_image(self):
        handler = FakeHandler()
        response = FakeResponse(
            b"image-data",
            headers={"Content-Type": "image/webp; charset=binary", "Content-Length": "10"},
        )
        with patch.object(jellyfin, "_jellyfin_config", return_value=self.config()), patch.object(
            jellyfin, "_jellyfin_validate_item_access", return_value="user-1"
        ), patch.object(
            jellyfin, "_jellyfin_authenticated_urlopen", return_value=response
        ):
            jellyfin._jellyfin_proxy_image(handler, "track-1")

        self.assertEqual(handler.responses, [200])
        self.assertIn(("Content-Type", "image/webp"), handler.sent_headers)
        self.assertEqual(handler.wfile.getvalue(), b"image-data")


class UsbDescriptorSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Music"
        self.album = self.root / "Album"
        self.album.mkdir(parents=True)
        self.track = self.album / "track.mp3"
        self.track.write_bytes(b"0123456789")
        self.env = patch.dict(
            os.environ,
            {
                "OPEN_MMI_USB_MEDIA_ROOTS": str(self.root),
                "OPEN_MMI_USB_AUTO_DISCOVER": "0",
            },
            clear=False,
        )
        self.env.start()
        usb._USB_ID_REGISTRY.clear()
        root = usb._usb_roots()[0]
        self.item_id = usb._usb_encode_id(root["id"], Path("Album/track.mp3"))

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_descriptor_relative_open_reads_regular_file(self):
        _root, relative, source, opened = usb._usb_open_file(self.item_id)
        with source:
            self.assertEqual(source.read(), b"0123456789")
        self.assertEqual(relative, Path("Album/track.mp3"))
        self.assertEqual(opened.st_size, 10)

    def test_symlink_swap_between_lookup_and_open_is_rejected(self):
        outside = Path(self.temp.name) / "outside.mp3"
        outside.write_bytes(b"private")
        real_open = os.open
        swapped = False

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            if path == "track.mp3" and dir_fd is not None and not swapped:
                swapped = True
                self.track.unlink()
                self.track.symlink_to(outside)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with patch.object(usb.os, "open", side_effect=racing_open):
            with self.assertRaises(PermissionError):
                usb._usb_open_file(self.item_id)
        self.assertTrue(swapped)

    def test_streaming_range_uses_descriptor_opened_file(self):
        handler = FakeHandler(range_header="bytes=2-5")
        usb._usb_send_file(handler, self.item_id)
        self.assertEqual(handler.responses, [206])
        self.assertIn(("Content-Range", "bytes 2-5/10"), handler.sent_headers)
        self.assertEqual(handler.wfile.getvalue(), b"2345")

    def test_invalid_range_closes_open_descriptor(self):
        source = io.BytesIO(b"data")
        handler = FakeHandler(range_header="bytes=99-100")
        with patch.object(
            usb,
            "_usb_open_file",
            return_value=(
                {"path": self.root},
                Path("track.mp3"),
                source,
                SimpleNamespace(st_size=4),
            ),
        ):
            usb._usb_send_file(handler, self.item_id)

        self.assertTrue(source.closed)
        self.assertEqual(handler.responses, [416])
        self.assertEqual(handler.errors, [])


class DeadStateModuleTests(unittest.TestCase):
    def test_obsolete_parallel_state_module_is_removed(self):
        self.assertFalse((ROOT / "canbusd" / "state.py").exists())
        for path in (ROOT / "canbusd").glob("*.py"):
            self.assertNotIn("canbusd.state", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
