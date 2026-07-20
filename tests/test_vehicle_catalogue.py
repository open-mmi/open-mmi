from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from ui import vehicle_catalogue, vehicle_setup


class VehicleCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.maintained = self.root / "installed"
        self.custom = self.root / "user" / "open-mmi"
        self.roots = vehicle_setup.CatalogueRoots(
            maintained=self.maintained,
            custom=self.custom,
        )
        self.profile_document = {
            "default_bus": "comfort",
            "can_buses": {
                "comfort": {
                    "interface": "can0",
                    "bitrate": 100000,
                    "provisioning": "udev",
                    "bring_up": False,
                }
            },
            "rules": [
                {"id": "0x100", "byte": 0, "value": 1, "event": "play_pause"}
            ],
            "presence": [],
            "status": [],
        }
        self.bindings_document = {
            "play_pause": {"module": "audio", "func": "play_pause", "args": []}
        }
        self.profile_path = self._write_json(
            self.maintained / "vehicles" / "seat_1p" / "config.json",
            self.profile_document,
        )
        self.bindings_path = self._write_json(
            self.maintained / "bindings" / "default.json",
            self.bindings_document,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _write_json(self, path: Path, document: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        directory = path.parent
        while directory != self.root:
            directory.chmod(0o700)
            directory = directory.parent
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o644)
        return path

    @staticmethod
    def _revision(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def request(self, kind: str, template_id: str, revision: str, custom_id: str):
        return {
            "kind": kind,
            "id": custom_id,
            "template_source": "maintained",
            "template_id": template_id,
            "template_revision": revision,
        }


    def _copy_custom(self, kind: str, identifier: str) -> Path:
        if kind == "profile":
            template_id = "seat_1p"
            template_path = self.profile_path
            destination = self.custom / "vehicles" / identifier / "config.json"
        else:
            template_id = "default"
            template_path = self.bindings_path
            destination = self.custom / "bindings" / f"{identifier}.json"
        vehicle_catalogue.copy_maintained_template(
            self.request(kind, template_id, self._revision(template_path), identifier),
            roots=self.roots,
        )
        return destination

    def edit_request(
        self,
        kind: str,
        identifier: str,
        revision: str,
        content: str,
    ) -> dict[str, str]:
        return {
            "kind": kind,
            "source": "custom",
            "id": identifier,
            "expected_revision": revision,
            "content": content,
        }

    def test_profile_copy_preserves_maintained_bytes_and_writes_only_user_catalogue(self):
        maintained_before = self.profile_path.read_bytes()
        result = vehicle_catalogue.copy_maintained_template(
            self.request(
                "profile",
                "seat_1p",
                self._revision(self.profile_path),
                "my-seat",
            ),
            roots=self.roots,
        )

        destination = self.custom / "vehicles" / "my-seat" / "config.json"
        self.assertEqual(destination.read_bytes(), maintained_before)
        self.assertEqual(self.profile_path.read_bytes(), maintained_before)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(destination.parent.stat().st_mode), 0o700)
        self.assertEqual(result["action"], "copy-maintained-template")
        self.assertEqual(result["custom"], {
            "source": "custom",
            "id": "my-seat",
            "revision": self._revision(destination),
        })
        provenance_path = (
            self.custom
            / ".open-mmi-provenance"
            / "profile"
            / "my-seat.json"
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(provenance_path.stat().st_mode), 0o600)
        self.assertEqual(provenance["kind"], "profile")
        self.assertEqual(provenance["id"], "my-seat")
        self.assertEqual(provenance["template"]["source"], "maintained")
        self.assertEqual(provenance["template"]["id"], "seat_1p")
        self.assertEqual(
            provenance["template"]["revision"],
            self._revision(self.profile_path),
        )
        self.assertTrue(provenance["template"]["open_mmi_version"])
        catalogue = vehicle_setup.catalogue_payload(self.roots)
        self.assertIn(
            ("custom", "my-seat"),
            [(entry["source"], entry["id"]) for entry in catalogue["profiles"]],
        )

    def test_bindings_copy_is_revision_bound_and_private(self):
        result = vehicle_catalogue.copy_maintained_template(
            self.request(
                "bindings",
                "default",
                self._revision(self.bindings_path),
                "my-controls",
            ),
            roots=self.roots,
        )
        destination = self.custom / "bindings" / "my-controls.json"
        self.assertEqual(destination.read_bytes(), self.bindings_path.read_bytes())
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(result["kind"], "bindings")
        provenance_path = (
            self.custom
            / ".open-mmi-provenance"
            / "bindings"
            / "my-controls.json"
        )
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        self.assertEqual(provenance["template"]["id"], "default")
        self.assertEqual(stat.S_IMODE(provenance_path.stat().st_mode), 0o600)


    def test_custom_profile_load_returns_exact_private_content_and_revision(self):
        destination = self._copy_custom("profile", "my-seat")
        result = vehicle_catalogue.load_custom_item(
            {"kind": "profile", "source": "custom", "id": "my-seat"},
            roots=self.roots,
        )
        self.assertEqual(result["action"], "load-custom-item")
        self.assertEqual(result["content"].encode("utf-8"), destination.read_bytes())
        self.assertEqual(result["custom"], {
            "source": "custom",
            "id": "my-seat",
            "revision": self._revision(destination),
        })
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_custom_save_is_revision_bound_validated_atomic_and_unapplied(self):
        destination = self._copy_custom("profile", "my-seat")
        provenance = self.custom / ".open-mmi-provenance" / "profile" / "my-seat.json"
        maintained_before = self.profile_path.read_bytes()
        provenance_before = provenance.read_bytes()
        previous_inode = destination.stat().st_ino
        updated = dict(self.profile_document)
        updated["rules"] = [
            {"id": "0x100", "byte": 0, "value": 2, "event": "play_pause"}
        ]
        content = json.dumps(updated, indent=2) + "\n"

        result = vehicle_catalogue.save_custom_item(
            self.edit_request(
                "profile",
                "my-seat",
                self._revision(destination),
                content,
            ),
            roots=self.roots,
        )

        self.assertEqual(destination.read_text(encoding="utf-8"), content)
        self.assertNotEqual(destination.stat().st_ino, previous_inode)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(self.profile_path.read_bytes(), maintained_before)
        self.assertEqual(provenance.read_bytes(), provenance_before)
        self.assertEqual(result["action"], "save-custom-item")
        self.assertFalse(result["applied"] )
        self.assertEqual(result["custom"]["revision"], self._revision(destination))
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual(
            list(destination.parent.glob(".open-mmi-save-*.tmp")),
            [],
        )

    def test_stale_custom_save_is_a_conflict_without_overwrite(self):
        destination = self._copy_custom("bindings", "my-controls")
        stale_revision = self._revision(destination)
        external = {
            "play_pause": {"module": "audio", "func": "stop", "args": []}
        }
        destination.write_text(json.dumps(external) + "\n", encoding="utf-8")
        destination.chmod(0o600)
        before = destination.read_bytes()

        with self.assertRaises(
            vehicle_catalogue.VehicleCatalogueConflictError
        ) as raised:
            vehicle_catalogue.save_custom_item(
                self.edit_request(
                    "bindings",
                    "my-controls",
                    stale_revision,
                    json.dumps(self.bindings_document) + "\n",
                ),
                roots=self.roots,
            )
        self.assertEqual(raised.exception.code, "custom-stale")
        self.assertEqual(destination.read_bytes(), before)

    def test_invalid_custom_content_is_never_written(self):
        destination = self._copy_custom("profile", "my-seat")
        revision = self._revision(destination)
        before = destination.read_bytes()
        for content, message in (
            ('{"rules":[', "valid UTF-8 JSON"),
            ('{"rules":[{"id":"bad"}]}\n', "not valid"),
            ('{"rules":[],"rules":[]}\n', "Duplicate"),
        ):
            with self.subTest(content=content), self.assertRaisesRegex(
                vehicle_catalogue.VehicleCatalogueError,
                message,
            ):
                vehicle_catalogue.save_custom_item(
                    self.edit_request(
                        "profile", "my-seat", revision, content
                    ),
                    roots=self.roots,
                )
            self.assertEqual(destination.read_bytes(), before)

    def test_custom_edit_routes_never_accept_maintained_or_path_shaped_identity(self):
        for payload in (
            {"kind": "profile", "source": "maintained", "id": "seat_1p"},
            {"kind": "profile", "source": "custom", "id": "../seat"},
        ):
            with self.subTest(payload=payload), self.assertRaises(
                vehicle_catalogue.VehicleCatalogueError
            ):
                vehicle_catalogue.load_custom_item(payload, roots=self.roots)
        self.assertFalse(self.custom.exists())

    def test_custom_edit_rejects_hardlinks_and_nonprivate_directories(self):
        destination = self._copy_custom("bindings", "my-controls")
        alias = destination.parent / "alias.json"
        os.link(destination, alias)
        request = {"kind": "bindings", "source": "custom", "id": "my-controls"}
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueError, "untrusted"
        ):
            vehicle_catalogue.load_custom_item(request, roots=self.roots)
        alias.unlink()
        self.custom.chmod(0o755)
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueError, "untrusted"
        ):
            vehicle_catalogue.load_custom_item(request, roots=self.roots)

    def test_untrusted_custom_file_is_not_loaded_or_saved(self):
        destination = self._copy_custom("bindings", "my-controls")
        destination.chmod(0o644)
        request = {"kind": "bindings", "source": "custom", "id": "my-controls"}
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueError, "untrusted"
        ):
            vehicle_catalogue.load_custom_item(request, roots=self.roots)
        destination.chmod(0o600)
        outside = self.root / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        outside.chmod(0o600)
        destination.unlink()
        destination.symlink_to(outside)
        with self.assertRaises(
            (vehicle_catalogue.VehicleCatalogueError, vehicle_setup.VehicleSetupError)
        ):
            vehicle_catalogue.load_custom_item(request, roots=self.roots)
        self.assertEqual(outside.read_text(encoding="utf-8"), "{}\n")

    def test_copy_rejects_custom_or_incomplete_source_identity(self):
        revision = self._revision(self.profile_path)
        for payload in (
            {
                "kind": "profile",
                "id": "copy",
                "template_source": "custom",
                "template_id": "seat_1p",
                "template_revision": revision,
            },
            {
                "kind": "profile",
                "id": "copy",
                "template_source": "maintained",
                "template_id": "seat_1p",
            },
            {
                "kind": "profile",
                "id": "../copy",
                "template_source": "maintained",
                "template_id": "seat_1p",
                "template_revision": revision,
            },
        ):
            with self.subTest(payload=payload), self.assertRaises(
                vehicle_catalogue.VehicleCatalogueError
            ):
                vehicle_catalogue.copy_maintained_template(payload, roots=self.roots)
        self.assertFalse(self.custom.exists())

    def test_stale_template_revision_is_a_conflict_without_destination(self):
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueConflictError,
            "template changed",
        ) as raised:
            vehicle_catalogue.copy_maintained_template(
                self.request(
                    "profile",
                    "seat_1p",
                    "sha256:" + "0" * 64,
                    "my-seat",
                ),
                roots=self.roots,
            )
        self.assertEqual(raised.exception.code, "template-stale")
        self.assertFalse((self.custom / "vehicles" / "my-seat").exists())

    def test_existing_custom_item_is_never_overwritten(self):
        destination = self._write_json(
            self.custom / "vehicles" / "my-seat" / "config.json",
            {"rules": []},
        )
        before = destination.read_bytes()
        with self.assertRaises(
            vehicle_catalogue.VehicleCatalogueConflictError
        ) as raised:
            vehicle_catalogue.copy_maintained_template(
                self.request(
                    "profile",
                    "seat_1p",
                    self._revision(self.profile_path),
                    "my-seat",
                ),
                roots=self.roots,
            )
        self.assertEqual(raised.exception.code, "custom-exists")
        self.assertEqual(destination.read_bytes(), before)

    def test_untrusted_custom_root_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.custom.parent.mkdir(parents=True)
        self.custom.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueError,
            "untrusted",
        ):
            vehicle_catalogue.copy_maintained_template(
                self.request(
                    "bindings",
                    "default",
                    self._revision(self.bindings_path),
                    "my-controls",
                ),
                roots=self.roots,
            )
        self.assertEqual(list(outside.iterdir()), [])

    def test_writable_maintained_template_is_not_trusted(self):
        self.profile_path.chmod(0o666)
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueError,
            "untrusted",
        ):
            vehicle_catalogue.copy_maintained_template(
                self.request(
                    "profile",
                    "seat_1p",
                    self._revision(self.profile_path),
                    "my-seat",
                ),
                roots=self.roots,
            )
        self.assertFalse(self.custom.exists())

    def test_invalid_maintained_template_is_not_copied(self):
        self.profile_path.write_text('{"rules":[{"id":"bad"}]}\n', encoding="utf-8")
        with self.assertRaisesRegex(
            vehicle_catalogue.VehicleCatalogueError,
            "not valid",
        ):
            vehicle_catalogue.copy_maintained_template(
                self.request(
                    "profile",
                    "seat_1p",
                    self._revision(self.profile_path),
                    "my-seat",
                ),
                roots=self.roots,
            )
        self.assertFalse(self.custom.exists())


if __name__ == "__main__":
    unittest.main()
