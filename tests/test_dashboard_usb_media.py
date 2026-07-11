import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_recursive_search_and_sidecar_art(self):
        payload = server._usb_browse_payload("", "track", 60, "az")
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
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
        root_payload = server._usb_browse_payload(server._usb_encode_id(root["id"]), "", 60, "browse")
        self.assertNotIn("link", [item["name"] for item in root_payload["items"]])

    def test_range_parsing(self):
        self.assertEqual(server._usb_parse_range("bytes=2-5", 10), (2, 5))
        self.assertEqual(server._usb_parse_range("bytes=7-", 10), (7, 9))
        self.assertEqual(server._usb_parse_range("bytes=-3", 10), (7, 9))
        with self.assertRaises(ValueError):
            server._usb_parse_range("bytes=20-30", 10)
        with self.assertRaises(ValueError):
            server._usb_parse_range("bytes=1-2,4-5", 10)

    def test_frontend_and_routes_are_present(self):
        root = SERVER_PATH.parents[2]
        app = (root / "ui/web_dashboard/static/app.js").read_text(encoding="utf-8")
        source = SERVER_PATH.read_text(encoding="utf-8")
        self.assertIn('id: "usb", label: "USB", note: "read-only local media", planned: false', app)
        self.assertIn('api.adapters.usb = usbAdapter()', app)
        self.assertRegex(app, r'return\s*\[[^\]]*"usb"[^\]]*\]\.includes\(active\)')
        self.assertIn('if parsed.path == "/api/usb/status":', source)
        self.assertIn('if parsed.path.startswith("/api/usb/stream/"):', source)


    def test_frontend_hydrates_missing_usb_durations(self):
        root = SERVER_PATH.parents[2]
        app = (root / "ui/web_dashboard/static/app.js").read_text(encoding="utf-8")
        self.assertIn("durationCache: new Map()", app)
        self.assertIn('audio.preload = "metadata";', app)
        self.assertIn("Math.min(2, entries.length)", app)
        self.assertIn('duration.textContent = "…";', app)
        self.assertIn("commitUsbDuration(index, item, cached, generation)", app)
        self.assertIn("playerAudio.addEventListener(\"loadedmetadata\"", app)


    def test_usb_search_accepts_spaces_and_path_terms(self):
        spaced = self.album / "Road Trip Anthem.mp3"
        spaced.write_bytes(b"road-trip")
        payload = server._usb_browse_payload("", "road trip", 60, "az")
        self.assertIn("Road Trip Anthem", [item["name"] for item in payload["items"]])

        separated = server._usb_browse_payload("", "track one", 60, "az")
        self.assertIn("Track One", [item["name"] for item in separated["items"]])

        across_path = server._usb_browse_payload("", "artist second", 60, "az")
        self.assertIn("Second", [item["name"] for item in across_path["items"]])

    def test_usb_navigation_chrome_is_source_scoped(self):
        root = SERVER_PATH.parents[2]
        app = (root / "ui/web_dashboard/static/app.js").read_text(encoding="utf-8")
        self.assertIn("function syncUsbSourceChrome(sourceId = null)", app)
        self.assertIn('const sourceButton = event.target.closest?.("[data-openmmi-media-source]");', app)
        self.assertIn('syncUsbSourceChrome(sourceId);', app)
        self.assertIn('if (sourceId !== "usb") return;', app)
        self.assertIn('syncUsbSourceChrome(usbIsActive ? "usb" : null);', app)

if __name__ == "__main__":
    unittest.main()
