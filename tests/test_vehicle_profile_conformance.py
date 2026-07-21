from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from ui import vehicle_profile_conformance, vehicle_setup


class VehicleProfileConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "vehicles").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "docs" / "qualification.md").write_text(
            "# Qualification\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def metadata(
        identifier: str = "example_car",
        *,
        maturity: str = "qualified",
        level: str = "hardware",
    ) -> dict[str, object]:
        if level == "none":
            last_tested = None
            scope: list[str] = []
            evidence: list[dict[str, str]] = []
        else:
            last_tested = "2026-07-20"
            scope = ["Passive CAN receive and canonical mappings"]
            evidence = [
                {
                    "kind": "hardware" if level == "hardware" else "replay",
                    "path": "docs/qualification.md",
                    "description": "Reviewable qualification evidence.",
                }
            ]
        return {
            "id": identifier,
            "display_name": "Example Car",
            "manufacturer": "Example",
            "model": "Car",
            "generation": "One",
            "platform": "Example Platform",
            "model_years": {"from": 2010, "to": 2014},
            "maturity": maturity,
            "license": "GPL-3.0-only",
            "maintainers": ["Open MMI contributors"],
            "qualification": {
                "level": level,
                "last_tested": last_tested,
                "scope": scope,
                "evidence": evidence,
            },
            "limitations": ["Example qualification scope only."],
        }

    def profile(
        self,
        identifier: str = "example_car",
        *,
        maturity: str = "qualified",
        level: str = "hardware",
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "metadata": self.metadata(identifier, maturity=maturity, level=level),
            "default_bus": "comfort",
            "can_buses": {
                "comfort": {
                    "interface": "can0",
                    "bitrate": 100000,
                    "provisioning": "manual",
                    "bring_up": False,
                }
            },
            "rules": [
                {
                    "id": "0x100",
                    "byte": 0,
                    "value": 1,
                    "event": "play_pause",
                }
            ],
            "presence": [],
            "status": [
                {
                    "id": "0x101",
                    "byte": 0,
                    "type": "bool",
                    "path": "doors.front_right",
                    "true": "0x01",
                    "false": "0x00",
                }
            ],
        }

    def write_profile(self, identifier: str, document: dict[str, object]) -> Path:
        path = self.root / "vehicles" / identifier / "config.json"
        path.parent.mkdir()
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        return path

    def test_qualified_profile_requires_hardware_evidence(self) -> None:
        valid = vehicle_profile_conformance.validate_metadata(
            self.profile(), expected_id="example_car"
        )
        self.assertTrue(valid["valid"], valid)

        invalid = self.profile(level="replay")
        result = vehicle_profile_conformance.validate_metadata(
            invalid, expected_id="example_car"
        )
        self.assertFalse(result["valid"])
        self.assertIn(
            "qualified-without-hardware",
            {issue["code"] for issue in result["errors"]},
        )

    def test_candidate_requires_replay_or_hardware_evidence(self) -> None:
        result = vehicle_profile_conformance.validate_metadata(
            self.profile(maturity="candidate", level="none"),
            expected_id="example_car",
        )
        codes = {issue["code"] for issue in result["errors"]}
        self.assertIn("candidate-without-qualification", codes)
        self.assertIn("candidate-without-test-evidence", codes)

        valid = vehicle_profile_conformance.validate_metadata(
            self.profile(maturity="candidate", level="replay"),
            expected_id="example_car",
        )
        self.assertTrue(valid["valid"], valid)

    def test_experimental_profile_may_have_no_qualification(self) -> None:
        result = vehicle_profile_conformance.validate_metadata(
            self.profile(maturity="experimental", level="none"),
            expected_id="example_car",
        )
        self.assertTrue(result["valid"], result)

    def test_profile_id_must_match_maintained_directory(self) -> None:
        result = vehicle_profile_conformance.validate_metadata(
            self.profile("other_car"), expected_id="example_car"
        )
        self.assertIn(
            "profile-id-mismatch",
            {issue["code"] for issue in result["errors"]},
        )

    def test_maintained_schema_rejects_unknown_top_level_fields(self) -> None:
        document = self.profile()
        document["private_decoder_language"] = True
        result = vehicle_profile_conformance.validate_metadata(
            document, expected_id="example_car"
        )
        self.assertIn(
            "unsupported-profile-field",
            {issue["code"] for issue in result["errors"]},
        )

    def test_normal_custom_profile_validation_does_not_require_admission_metadata(self) -> None:
        custom = {
            "default_bus": "comfort",
            "can_buses": {"comfort": {"interface": "can0"}},
            "rules": [],
            "presence": [],
            "status": [],
        }
        result = vehicle_setup.validate_profile(custom)
        self.assertTrue(result["valid"], result)

    def test_catalogue_report_checks_evidence_and_lists_capabilities(self) -> None:
        self.write_profile("example_car", self.profile())
        report = vehicle_profile_conformance.catalogue_report(self.root)
        self.assertTrue(report["valid"], report)
        self.assertEqual(report["summary"]["maturity"], {"qualified": 1})
        profile = report["profiles"][0]
        self.assertEqual(profile["capabilities"]["events"], ["play_pause"])
        self.assertEqual(profile["capabilities"]["statuses"], ["doors.front_right"])

        (self.root / "docs" / "qualification.md").unlink()
        report = vehicle_profile_conformance.catalogue_report(self.root)
        self.assertFalse(report["valid"])
        self.assertIn(
            "missing-evidence-file",
            {
                issue["code"]
                for issue in report["profiles"][0]["validation"]["errors"]
            },
        )

    def test_catalogue_report_rejects_duplicate_json_keys(self) -> None:
        path = self.root / "vehicles" / "example_car" / "config.json"
        path.parent.mkdir()
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        report = vehicle_profile_conformance.catalogue_report(self.root)
        self.assertFalse(report["valid"])
        self.assertIn(
            "unreadable-profile",
            {
                issue["code"]
                for issue in report["profiles"][0]["validation"]["errors"]
            },
        )

    def test_repository_seat_profile_conforms(self) -> None:
        root = Path(__file__).resolve().parents[1]
        report = vehicle_profile_conformance.catalogue_report(
            root, identifiers=["seat_1p"]
        )
        self.assertTrue(report["valid"], report)
        profile = report["profiles"][0]
        self.assertEqual(profile["metadata"]["maturity"], "qualified")
        self.assertEqual(profile["metadata"]["qualification"]["level"], "hardware")


if __name__ == "__main__":
    unittest.main()
