from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ui import vehicle_configuration


class VehicleConfigurationTests(unittest.TestCase):
    def selection(self):
        return {
            "vehicle": {
                "source": "maintained",
                "id": "seat_1p",
                "revision": "sha256:" + "a" * 64,
            },
            "bindings": {
                "source": "custom",
                "id": "my_controls",
                "revision": "sha256:" + "b" * 64,
            },
            "runtime": {
                "mode": "single",
                "active_bus": "comfort",
                "buses": {"comfort": {"interface": "can0"}},
            },
        }

    def test_selection_is_normalized_and_revision_is_deterministic(self):
        selection = self.selection()
        normalized = vehicle_configuration.normalize_selection(selection)
        self.assertEqual(normalized, selection)
        first = vehicle_configuration.selection_revision(selection)
        reordered = {
            "runtime": selection["runtime"],
            "bindings": selection["bindings"],
            "vehicle": selection["vehicle"],
        }
        self.assertEqual(first, vehicle_configuration.selection_revision(reordered))
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")

    def test_selection_rejects_paths_unknown_fields_and_multiple_buses(self):
        cases = []
        invalid_id = self.selection()
        invalid_id["vehicle"] = {**invalid_id["vehicle"], "id": "../seat"}
        cases.append(invalid_id)
        unknown = self.selection()
        unknown["command"] = "manage.sh"
        cases.append(unknown)
        invalid_field = self.selection()
        invalid_field[1] = "not-a-JSON-field"
        cases.append(invalid_field)
        multiple = self.selection()
        multiple["runtime"] = {
            **multiple["runtime"],
            "buses": {
                "comfort": {"interface": "can0"},
                "powertrain": {"interface": "can1"},
            },
        }
        cases.append(multiple)
        invalid_interface = self.selection()
        invalid_interface["runtime"] = {
            **invalid_interface["runtime"],
            "buses": {"comfort": {"interface": "../../can0"}},
        }
        cases.append(invalid_interface)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(
                vehicle_configuration.VehicleConfigurationError
            ):
                vehicle_configuration.normalize_selection(case)

    def test_descriptor_requires_schema_timezone_and_exact_shape(self):
        descriptor = vehicle_configuration.descriptor_for_selection(
            self.selection(),
            applied_at="2026-07-20T12:00:00+00:00",
        )
        self.assertEqual(
            vehicle_configuration.validate_descriptor(descriptor), descriptor
        )
        for value in (
            {**descriptor, "schema_version": True},
            {**descriptor, "schema_version": 2},
            {**descriptor, "applied_at": "2026-07-20T12:00:00"},
            {**descriptor, "path": "/tmp/config"},
        ):
            with self.subTest(value=value), self.assertRaises(
                vehicle_configuration.VehicleConfigurationError
            ):
                vehicle_configuration.validate_descriptor(value)

    def test_descriptor_loader_is_missing_safe_and_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "vehicle-configuration.json"
            self.assertIsNone(vehicle_configuration.load_descriptor(path))
            descriptor = vehicle_configuration.descriptor_for_selection(
                self.selection(),
                applied_at="2026-07-20T12:00:00Z",
            )
            path.write_text(json.dumps(descriptor), encoding="utf-8")
            path.chmod(0o644)
            self.assertEqual(
                vehicle_configuration.load_descriptor(
                    path,
                    expected_uid=path.stat().st_uid,
                ),
                descriptor,
            )
            path.chmod(0o666)
            with self.assertRaisesRegex(
                vehicle_configuration.VehicleConfigurationError,
                "group or world writable",
            ):
                vehicle_configuration.load_descriptor(
                    path,
                    expected_uid=path.stat().st_uid,
                )
            path.chmod(0o644)
            path.unlink()
            target = root / "target.json"
            target.write_text(json.dumps(descriptor), encoding="utf-8")
            path.symlink_to(target)
            with self.assertRaisesRegex(
                vehicle_configuration.VehicleConfigurationError,
                "regular file",
            ):
                vehicle_configuration.load_descriptor(
                    path,
                    expected_uid=target.stat().st_uid,
                )

    def test_descriptor_loader_rejects_duplicate_keys_and_non_finite_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "vehicle-configuration.json"
            for content in (
                '{"schema_version":1,"schema_version":1}',
                '{"schema_version":NaN}',
            ):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(
                    vehicle_configuration.VehicleConfigurationError
                ):
                    vehicle_configuration.load_descriptor(
                        path,
                        expected_uid=path.stat().st_uid,
                    )


if __name__ == "__main__":
    unittest.main()
