import importlib.util
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


SERVER_PATH = Path(__file__).resolve().parents[1] / "ui" / "web_dashboard" / "server.py"
SPEC = importlib.util.spec_from_file_location("open_mmi_web_dashboard_server_radio", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


class RadioSourceTests(unittest.TestCase):
    def test_station_id_must_be_uuid(self):
        value = "b5f9f7e7-8b6a-4f9e-a471-521fb85c1784"
        self.assertEqual(server._safe_radio_station_id(value), value)
        with self.assertRaises(ValueError):
            server._safe_radio_station_id("../../metadata")

    def test_stream_url_rejects_private_address(self):
        private = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
        with patch("socket.getaddrinfo", return_value=private):
            with self.assertRaises(PermissionError):
                server._radio_validate_stream_url("http://radio.example/live")

    def test_stream_url_accepts_public_address(self):
        public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("socket.getaddrinfo", return_value=public):
            self.assertEqual(
                server._radio_validate_stream_url("https://radio.example/live"),
                "https://radio.example/live",
            )

    def test_stream_url_rejects_credentials_and_non_http(self):
        with self.assertRaises(ValueError):
            server._radio_validate_stream_url("file:///etc/passwd")
        with self.assertRaises(ValueError):
            server._radio_validate_stream_url("https://user:pass@example.com/live")

    def test_search_uses_bounded_broken_station_filter(self):
        captured = {}
        station_id = "b5f9f7e7-8b6a-4f9e-a471-521fb85c1784"

        def fake_catalog(path, params=None):
            captured["path"] = path
            captured["params"] = params
            return [{
                "stationuuid": station_id,
                "name": "Example FM",
                "country": "United Kingdom",
                "countrycode": "GB",
                "language": "english",
                "languagecodes": "eng",
                "codec": "mp3",
                "bitrate": 128,
                "tags": "rock,alternative",
                "url": "https://stream.example/live",
            }]

        with patch.object(server, "_radio_catalog_json", side_effect=fake_catalog):
            payload = server._radio_search_payload(
                "example", 999, "votes", country_code="gb", language="english"
            )

        self.assertEqual(captured["path"], "/json/stations/search")
        self.assertEqual(captured["params"]["hidebroken"], "true")
        self.assertEqual(captured["params"]["limit"], "60")
        self.assertEqual(captured["params"]["name"], "example")
        self.assertEqual(captured["params"]["countrycode"], "GB")
        self.assertEqual(captured["params"]["language"], "english")
        self.assertEqual(payload["items"][0]["id"], station_id)
        self.assertEqual(payload["items"][0]["country_code"], "GB")
        self.assertEqual(payload["items"][0]["language"], "english")
        self.assertTrue(payload["items"][0]["is_live"])
        self.assertNotIn("url", payload["items"][0])
        self.assertNotIn("stream_url", payload["items"][0])

    def test_browse_filter_changes_catalog_order(self):
        captured = {}

        def fake_catalog(path, params=None):
            captured.update(params or {})
            return []

        with patch.object(server, "_radio_catalog_json", side_effect=fake_catalog):
            payload = server._radio_search_payload("", 12, "recent")
        self.assertEqual(payload["filter"], "recent")
        self.assertEqual(captured["order"], "clicktimestamp")
        self.assertEqual(captured["reverse"], "true")


    def test_invalid_country_and_control_language_are_ignored(self):
        captured = {}

        def fake_catalog(path, params=None):
            captured.update(params or {})
            return []

        with patch.object(server, "_radio_catalog_json", side_effect=fake_catalog):
            server._radio_search_payload("", 10, "popular", "admin", "english\nother")
        self.assertNotIn("countrycode", captured)
        self.assertNotIn("language", captured)

    def test_filter_options_are_normalized(self):
        responses = {
            "/json/countrycodes": [
                {"name": "gb", "stationcount": "123"},
                {"name": "not-a-code", "stationcount": "9"},
            ],
            "/json/languages": [
                {"name": "english", "iso_639": "en", "stationcount": "321"},
                {"name": "", "stationcount": "2"},
            ],
        }

        def fake_catalog(path, params=None):
            self.assertEqual(params["hidebroken"], "true")
            self.assertEqual(params["order"], "stationcount")
            return responses[path]

        with patch.object(server, "_radio_catalog_json", side_effect=fake_catalog):
            payload = server._radio_filter_options_payload()
        self.assertEqual(payload["countries"], [{"code": "GB", "station_count": 123}])
        self.assertEqual(
            payload["languages"],
            [{"name": "english", "code": "en", "station_count": 321}],
        )

    def test_stream_resolution_prefers_resolved_url_and_counts_click(self):
        station_id = "b5f9f7e7-8b6a-4f9e-a471-521fb85c1784"
        station = {
            "stationuuid": station_id,
            "url": "http://old.example/live",
            "url_resolved": "https://stream.example/live",
        }
        with patch.object(server, "_radio_station_by_uuid", return_value=station), patch.object(
            server, "_radio_validate_stream_url", side_effect=lambda value, **_: value
        ) as validate, patch.object(server, "_radio_catalog_json", return_value={}) as click:
            self.assertEqual(
                server._radio_stream_url(station_id),
                "https://stream.example/live",
            )
        validate.assert_called_once()
        click.assert_called_once_with(f"/json/url/{station_id}")


if __name__ == "__main__":
    unittest.main()
