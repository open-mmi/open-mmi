from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard_contract_helpers import (
    implemented_source_ids,
    javascript_function_body,
    js_bool_property,
    js_object_with_id,
    js_string_property,
    marked_block,
    read_repo_text,
)


SERVER_PATH = Path(__file__).resolve().parents[1] / "ui" / "web_dashboard" / "server.py"
SPEC = importlib.util.spec_from_file_location("open_mmi_web_dashboard_server_usb", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


class UsbMediaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Road Music"
        self.album = self.root / "Artist" / "Album"
        self.album.mkdir(parents=True)
        (self.album / "Track_One.mp3").write_bytes(b"0123456789abcdef")
        (self.album / "Second.flac").write_bytes(b"flac-data")
        (self.album / "cover.jpg").write_bytes(b"jpeg-data")
        (self.album / ".hidden.mp3").write_bytes(b"hidden")
        (self.album / "notes.txt").write_text("not audio", encoding="utf-8")
        self.env = patch.dict(
            os.environ,
            {
                "OPEN_MMI_USB_MEDIA_ROOTS": str(self.root),
                "OPEN_MMI_USB_AUTO_DISCOVER": "0",
                "OPEN_MMI_USB_INCLUDE_HIDDEN": "0",
                "OPEN_MMI_USB_READ_METADATA": "0",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_status_exposes_labels_not_paths(self):
        payload = server._usb_status_payload()
        self.assertTrue(payload["configured"])
        self.assertEqual(payload["root_count"], 1)
        self.assertEqual(payload["roots"][0]["label"], "Road Music")
        self.assertNotIn(str(self.root), str(payload))
        self.assertTrue(payload["read_only"])

    def test_root_and_folder_browsing(self):
        roots = server._usb_browse_payload("", "", 60, "browse")
        self.assertEqual(len(roots["items"]), 1)
        root_item = roots["items"][0]
        self.assertEqual(root_item["kind"], "directory")

        first = server._usb_browse_payload(root_item["id"], "", 60, "browse")
        artist = next(item for item in first["items"] if item["name"] == "Artist")
        second = server._usb_browse_payload(artist["id"], "", 60, "browse")
        album = next(item for item in second["items"] if item["name"] == "Album")
        tracks = server._usb_browse_payload(album["id"], "", 60, "browse")
        names = [item["name"] for item in tracks["items"]]
        self.assertIn("Track One", names)
        self.assertIn("Second", names)
        self.assertNotIn(".hidden", " ".join(names))
        self.assertTrue(tracks["parent_id"])
        self.assertEqual(tracks["breadcrumbs"][-1]["label"], "Album")

    def test_recursive_search_sidecar_art_and_spaced_terms(self):
        (self.album / "Road Trip Anthem.mp3").write_bytes(b"road-trip")
        cases = {
            "track": "Track One",
            "track one": "Track One",
            "road trip": "Road Trip Anthem",
            "artist second": "Second",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                payload = server._usb_browse_payload("", query, 60, "az")
                names = [item["name"] for item in payload["items"]]
                self.assertIn(expected, names)
        item = server._usb_browse_payload("", "track one", 60, "az")["items"][0]
        self.assertEqual(item["source"], "usb")
        self.assertEqual(item["kind"], "audio")
        self.assertTrue(item["image_url"].startswith("/api/usb/art/"))
        self.assertNotIn(str(self.root), str(item))

    def test_ids_resolve_only_inside_current_root(self):
        root = server._usb_roots()[0]
        valid = server._usb_encode_id(root["id"], Path("Artist/Album/Track_One.mp3"))
        _root, relative, resolved = server._usb_resolve_id(valid)
        self.assertEqual(relative.as_posix(), "Artist/Album/Track_One.mp3")
        self.assertEqual(resolved, self.album / "Track_One.mp3")
        with self.assertRaises(ValueError):
            server._usb_encode_id(root["id"], Path("../outside.mp3"))
        with self.assertRaises(ValueError):
            server._usb_resolve_id("u" + "0" * 39 + "z")

    def test_symlink_components_are_rejected(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "escape.mp3").write_bytes(b"escape")
        link = self.root / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable")
        root = server._usb_roots()[0]
        item_id = server._usb_encode_id(root["id"], Path("link/escape.mp3"))
        with self.assertRaises(PermissionError):
            server._usb_resolve_id(item_id)
        payload = server._usb_browse_payload(server._usb_encode_id(root["id"]), "", 60, "browse")
        self.assertNotIn("link", [item["name"] for item in payload["items"]])

    def test_range_parsing(self):
        self.assertEqual(server._usb_parse_range("bytes=2-5", 10), (2, 5))
        self.assertEqual(server._usb_parse_range("bytes=7-", 10), (7, 9))
        self.assertEqual(server._usb_parse_range("bytes=-3", 10), (7, 9))
        with self.assertRaises(ValueError):
            server._usb_parse_range("bytes=20-30", 10)
        with self.assertRaises(ValueError):
            server._usb_parse_range("bytes=1-2,4-5", 10)

    def test_frontend_registration_and_routes_are_semantic(self):
        app = read_repo_text("ui/web_dashboard/static/app.js")
        source = read_repo_text("ui/web_dashboard/server.py")
        descriptor = js_object_with_id(app, "usb")
        self.assertEqual(js_string_property(descriptor, "label"), "USB")
        self.assertFalse(js_bool_property(descriptor, "planned"))
        self.assertIn("usb", implemented_source_ids(app))
        self.assertRegex(app, r"\badapters\.usb\s*=\s*usbAdapter\s*\(\s*\)")
        self.assertRegex(source, r"parsed\.path\s*==\s*['\"]/api/usb/status['\"]")
        self.assertRegex(source, r"parsed\.path\.startswith\(\s*['\"]/api/usb/stream/['\"]")

    def test_usb_navigation_is_scoped_and_missing_durations_are_hydrated(self):
        app = read_repo_text("ui/web_dashboard/static/app.js")
        block = marked_block(
            app,
            "// --- Open MMI USB media source start ---",
            "// --- Open MMI USB media source end ---",
        )
        chrome = javascript_function_body(block, "syncUsbSourceChrome")
        self.assertRegex(
            chrome,
            r"controls\.hidden\s*=\s*[A-Za-z_$][\w$]*\s*!==?\s*['\"]usb['\"]",
        )
        self.assertRegex(block, r"preload\s*=\s*['\"]metadata['\"]")
        self.assertIn("loadedmetadata", block)
        self.assertRegex(block, r"Math\.min\(\s*2\s*,")
        self.assertIn("durationCache", block)


if __name__ == "__main__":
    unittest.main()
