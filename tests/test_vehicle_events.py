import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from canbusd import event_registry as vehicle_events
from ui import config_cli, vehicle_setup


class VehicleEventRegistryTests(unittest.TestCase):
    def test_bundled_registry_freezes_current_universal_events(self):
        registry = vehicle_events.registry_payload()
        self.assertEqual(registry["schema_version"], 1)
        self.assertEqual(registry["registry_id"], "open-mmi.vehicle-events")
        self.assertEqual(
            set(registry["events"]),
            {
                "arrow_left",
                "arrow_right",
                "brightness_level",
                "mute_toggle",
                "next_track",
                "play_pause",
                "previous_track",
                "stop_playback",
                "vehicle_present:off",
                "vehicle_present:on",
                "volume_down",
                "volume_up",
            },
        )
        self.assertEqual(
            registry["events"]["brightness_level"]["payload"],
            {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "unit": "percent",
            },
        )
        self.assertIn(
            "never means mute-on or mute-off",
            registry["events"]["mute_toggle"]["description"],
        )

    def test_event_lookup_distinguishes_canonical_alias_and_unknown(self):
        registry = vehicle_events.registry_payload()
        registry["aliases"]["legacy_mute"] = {
            "event": "mute_toggle",
            "description": "Historical private synonym.",
            "status": "deprecated",
        }
        self.assertEqual(
            vehicle_events.event_status("mute_toggle", registry),
            ("canonical", "mute_toggle"),
        )
        self.assertEqual(
            vehicle_events.event_status("legacy_mute", registry),
            ("alias", "mute_toggle"),
        )
        self.assertEqual(
            vehicle_events.event_status("vauxhall_volume_off", registry),
            ("unknown", None),
        )
        self.assertEqual(
            vehicle_events.event_status("../../mute", registry),
            ("invalid", None),
        )

    def test_registry_loader_rejects_duplicate_keys_and_unsupported_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.json"
            path.write_text(
                '{"schema_version":1,"schema_version":1,'
                '"registry_id":"open-mmi.vehicle-events",'
                '"events":{},"aliases":{}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                vehicle_events.VehicleEventRegistryError,
                "duplicate JSON key",
            ):
                vehicle_events.load_registry(path)

        registry = vehicle_events.registry_payload()
        registry["events"]["mute_toggle"]["vehicle"] = "seat"
        with self.assertRaisesRegex(
            vehicle_events.VehicleEventRegistryError,
            "unsupported fields",
        ):
            vehicle_events.normalize_registry(registry)

    def test_profiles_and_bindings_require_registered_canonical_events(self):
        profile = {
            "rules": [
                {
                    "id": "0x231",
                    "byte": 3,
                    "value": 30,
                    "event": "vauxhall_steering_volume_off",
                }
            ]
        }
        profile_validation = vehicle_setup.validate_profile(profile)
        self.assertFalse(profile_validation["valid"])
        self.assertIn(
            "unregistered-event",
            {issue["code"] for issue in profile_validation["errors"]},
        )

        bindings_validation = vehicle_setup.validate_bindings(
            {
                "vauxhall_steering_volume_off": {
                    "module": "audio",
                    "func": "mute_toggle",
                }
            }
        )
        self.assertFalse(bindings_validation["valid"])
        self.assertIn(
            "unregistered-event",
            {issue["code"] for issue in bindings_validation["errors"]},
        )

    def test_deprecated_alias_is_diagnostic_not_a_valid_profile_contract(self):
        registry = vehicle_events.registry_payload()
        registry["aliases"]["legacy_mute"] = {
            "event": "mute_toggle",
            "description": "Historical private synonym.",
            "status": "deprecated",
        }
        validation = vehicle_setup.validate_profile(
            {
                "rules": [
                    {
                        "id": "0x231",
                        "byte": 3,
                        "value": 30,
                        "event": "legacy_mute",
                    }
                ]
            },
            event_registry=registry,
        )
        self.assertFalse(validation["valid"])
        error = next(
            issue
            for issue in validation["errors"]
            if issue["code"] == "deprecated-event-alias"
        )
        self.assertIn("mute_toggle", error["message"])

    def test_rule_payload_delivery_matches_registry_contract(self):
        unexpected = vehicle_setup.validate_profile(
            {
                "rules": [
                    {
                        "id": "0x100",
                        "byte": 0,
                        "value": "any",
                        "event": "play_pause",
                    }
                ]
            }
        )
        self.assertIn(
            "unexpected-event-payload",
            {issue["code"] for issue in unexpected["errors"]},
        )

        missing = vehicle_setup.validate_profile(
            {
                "rules": [
                    {
                        "id": "0x470",
                        "byte": 2,
                        "value": 50,
                        "event": "brightness_level",
                    }
                ]
            }
        )
        self.assertIn(
            "missing-event-payload",
            {issue["code"] for issue in missing["errors"]},
        )

        valid = vehicle_setup.validate_profile(
            {
                "rules": [
                    {
                        "id": "0x470",
                        "byte": 2,
                        "value": "any",
                        "event": "brightness_level",
                    }
                ]
            }
        )
        self.assertTrue(valid["valid"])

    def test_maintained_catalogue_conforms_to_registry(self):
        root = Path(__file__).resolve().parents[1]
        profile = json.loads(
            (root / "vehicles/seat_1p/config.json").read_text(encoding="utf-8")
        )
        bindings = json.loads(
            (root / "bindings/default.json").read_text(encoding="utf-8")
        )
        self.assertTrue(vehicle_setup.validate_profile(profile)["valid"])
        self.assertTrue(vehicle_setup.validate_bindings(bindings)["valid"])

    def test_cli_exposes_registry_and_one_definition(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = config_cli.main(["vehicle-setup", "events", "mute_toggle"])
        self.assertEqual(result, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["event"], "mute_toggle")
        self.assertEqual(payload["payload"], {"type": "none"})

    def test_generated_documentation_matches_registry(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "tools/generate_vehicle_event_docs.py",
                "--check",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
