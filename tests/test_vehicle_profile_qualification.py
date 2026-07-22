from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from ui import (
    config_cli,
    vehicle_profile_conformance,
    vehicle_profile_qualification,
    vehicle_profile_scaffold,
)


ROOT = Path(__file__).resolve().parents[1]


class VehicleProfileQualificationTests(unittest.TestCase):
    def make_profile(self, base: Path) -> tuple[Path, Path]:
        root = base / "open-mmi"
        vehicles = root / "vehicles"
        vehicles.mkdir(parents=True)
        template = ROOT / "vehicles" / "_template"
        import shutil

        shutil.copytree(template, vehicles / "_template")
        existing = vehicles / "existing/model/one-platform/config.json"
        existing.parent.mkdir(parents=True)
        existing_document = json.loads(
            (template / "config.template.json").read_text(encoding="utf-8")
        )
        existing_document["metadata"].update(
            {
                "id": "existing-profile",
                "display_name": "Existing Profile",
                "manufacturer": "Existing",
                "model": "Profile",
                "generation": "One",
                "platform": "Platform",
            }
        )
        existing.write_text(
            json.dumps(existing_document, indent=2) + "\n",
            encoding="utf-8",
        )
        existing_record = existing.parent / "evidence/qualification.v1.json"
        existing_record.parent.mkdir()
        existing_record.write_text(
            json.dumps(
                vehicle_profile_qualification.default_record("existing-profile"),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (vehicles / "catalogue.v1.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "catalogue_id": "open-mmi.maintained-vehicles",
                    "profiles": {
                        "existing-profile": {
                            "path": "existing/model/one-platform/config.json",
                            "aliases": [],
                        }
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        vehicle_profile_scaffold.scaffold_profile(
            root,
            brand="Example",
            model="Car",
            generation="One",
            platform="Platform",
            year_from=2010,
            year_to=2014,
        )
        profile = vehicles / "example/car/one-platform/config.json"
        document = json.loads(profile.read_text(encoding="utf-8"))
        document["rules"] = [
            {"id": "0x100", "byte": 0, "value": 1, "event": "play_pause"}
        ]
        document["status"] = [
            {
                "id": "0x101",
                "byte": 0,
                "type": "bool",
                "path": "doors.front_right",
                "true": "0x01",
                "false": "0x00",
            }
        ]
        profile.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        fixtures = profile.parent / "fixtures/mappings.v1.json"
        fixtures.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "fixture_id": "open-mmi.vehicle-mapping-fixtures",
                    "profile_id": "example-car-one-platform",
                    "cases": [
                        {
                            "name": "play-pause",
                            "bus": "comfort",
                            "frames": [{"id": "0x100", "data": "01"}],
                            "expect": {
                                "events": [{"event": "play_pause", "payload": None}],
                                "statuses": {},
                            },
                        },
                        {
                            "name": "door",
                            "bus": "comfort",
                            "frames": [{"id": "0x101", "data": "01"}],
                            "expect": {
                                "events": [],
                                "statuses": {"doors.front_right": True},
                            },
                        },
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "docs").mkdir()
        (root / "docs/replay.md").write_text("# Replay proof\n", encoding="utf-8")
        (root / "docs/hardware.md").write_text("# Hardware proof\n", encoding="utf-8")
        return root, profile

    def promote_replay(self, root: Path, *, dry_run: bool = False) -> dict[str, object]:
        return vehicle_profile_qualification.transition_profile(
            root,
            "example-car-one-platform",
            target="replay",
            reason="Complete deterministic replay coverage was reviewed.",
            reviewers=["Reviewer One"],
            reviewed_on="2026-07-21",
            tested_on="2026-07-20",
            recheck_after="2027-01-20",
            scope=["Canonical event and status mapping replay"],
            evidence=[
                {
                    "kind": "replay",
                    "path": "docs/replay.md",
                    "description": "Reviewed deterministic replay proof.",
                }
            ],
            dry_run=dry_run,
        )

    def test_scaffold_starts_with_unreviewed_none_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, profile = self.make_profile(Path(tmp))
            record = vehicle_profile_qualification.load_record(
                profile.parent / "evidence/qualification.v1.json"
            )
            self.assertEqual(record["current"]["level"], "none")
            self.assertEqual(record["current"]["review"]["status"], "unreviewed")
            report = vehicle_profile_conformance.catalogue_report(root)
            self.assertTrue(report["valid"], report)

    def test_promotion_is_one_stage_and_dry_run_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, profile = self.make_profile(Path(tmp))
            before = profile.read_bytes()
            result = self.promote_replay(root, dry_run=True)
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["from"], "none")
            self.assertEqual(result["to"], "replay")
            self.assertEqual(profile.read_bytes(), before)

            with self.assertRaisesRegex(
                vehicle_profile_qualification.VehicleProfileQualificationError,
                "one stage",
            ):
                vehicle_profile_qualification.transition_profile(
                    root,
                    "example-car-one-platform",
                    target="hardware",
                    reason="Unsafe skipped stage.",
                    reviewers=["Reviewer One"],
                    reviewed_on="2026-07-21",
                    tested_on="2026-07-20",
                    recheck_after="2027-01-20",
                    scope=["Hardware test"],
                    equipment=["Example adapter"],
                    variants=["Example Car 2010 to 2014"],
                    evidence=[
                        {
                            "kind": "replay",
                            "path": "docs/replay.md",
                            "description": "Replay proof.",
                        },
                        {
                            "kind": "hardware",
                            "path": "docs/hardware.md",
                            "description": "Hardware proof.",
                        },
                    ],
                    dry_run=True,
                )

    def test_replay_then_hardware_promotion_and_demotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, profile = self.make_profile(Path(tmp))
            self.promote_replay(root)
            replay_document = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(replay_document["metadata"]["maturity"], "candidate")
            self.assertEqual(replay_document["metadata"]["qualification"]["level"], "replay")

            hardware = vehicle_profile_qualification.transition_profile(
                root,
                "example-car-one-platform",
                target="hardware",
                reason="Real passive CAN hardware test was reviewed.",
                reviewers=["Reviewer One", "Reviewer Two"],
                reviewed_on="2026-07-22",
                tested_on="2026-07-21",
                recheck_after="2027-07-21",
                scope=["Passive CAN receive on the documented interface"],
                equipment=["Example USB CAN adapter on comfort bus"],
                variants=["Example Car model years 2010 to 2014"],
                evidence=[
                    {
                        "kind": "hardware",
                        "path": "docs/hardware.md",
                        "description": "Reviewed passive hardware qualification.",
                    }
                ],
            )
            self.assertEqual(hardware["to"], "hardware")
            report = vehicle_profile_conformance.catalogue_report(root)
            self.assertTrue(report["valid"], report)
            profile_report = report["profiles"][0]
            self.assertEqual(profile_report["metadata"]["maturity"], "qualified")
            self.assertEqual(profile_report["qualification"]["history_count"], 2)
            self.assertEqual(
                profile_report["qualification"]["compatibility"]["equipment"],
                ["Example USB CAN adapter on comfort bus"],
            )

            demoted = vehicle_profile_qualification.transition_profile(
                root,
                "example-car-one-platform",
                target="none",
                reason="Hardware compatibility claim was withdrawn pending retest.",
                reviewers=["Reviewer One"],
                reviewed_on="2026-07-23",
            )
            self.assertEqual(demoted["to"], "none")
            document = json.loads(profile.read_text(encoding="utf-8"))
            self.assertEqual(document["metadata"]["maturity"], "experimental")
            self.assertEqual(document["metadata"]["qualification"]["evidence"], [])
            self.assertTrue(vehicle_profile_conformance.catalogue_report(root)["valid"])

    def test_stale_review_is_warning_not_silent_demotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, _profile = self.make_profile(Path(tmp))
            self.promote_replay(root)
            report = vehicle_profile_conformance.catalogue_report(
                root,
                as_of=date(2027, 1, 21),
            )
            self.assertTrue(report["valid"], report)
            qualification = report["profiles"][0]["qualification"]
            self.assertTrue(qualification["stale"])
            self.assertIn(
                "qualification-stale",
                {item["code"] for item in qualification["validation"]["warnings"]},
            )

    def test_cli_report_and_transition_dry_run_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, _profile = self.make_profile(Path(tmp))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = config_cli.main(
                    [
                        "vehicle-setup",
                        "qualification",
                        "report",
                        "example-car-one-platform",
                        "--root",
                        str(root),
                        "--as-of",
                        "2026-07-21",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(payload["profiles"][0]["qualification"]["level"], "none")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = config_cli.main(
                    [
                        "vehicle-setup",
                        "qualification",
                        "transition",
                        "example-car-one-platform",
                        "--root",
                        str(root),
                        "--to",
                        "replay",
                        "--reason",
                        "Reviewed replay promotion.",
                        "--reviewer",
                        "Reviewer One",
                        "--reviewed-on",
                        "2026-07-21",
                        "--tested-on",
                        "2026-07-20",
                        "--recheck-after",
                        "2027-01-20",
                        "--scope",
                        "Canonical replay coverage",
                        "--evidence",
                        "replay=docs/replay.md=Reviewed replay proof.",
                        "--dry-run",
                    ]
                )
            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["to"], "replay")

    def test_repository_seat_record_is_current_and_approved(self) -> None:
        report = vehicle_profile_conformance.catalogue_report(
            ROOT,
            identifiers=["seat_1p"],
            as_of=date(2026, 7, 21),
        )
        self.assertTrue(report["valid"], report)
        qualification = report["profiles"][0]["qualification"]
        self.assertEqual(qualification["level"], "hardware")
        self.assertEqual(qualification["review_status"], "approved")
        self.assertFalse(qualification["stale"])
        self.assertEqual(qualification["recheck_after"], "2027-07-20")


if __name__ == "__main__":
    unittest.main()
