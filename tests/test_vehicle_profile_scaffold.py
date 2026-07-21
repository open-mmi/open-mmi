from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch

from canbusd import profile_catalogue
from ui import config_cli, vehicle_profile_conformance, vehicle_profile_scaffold, vehicle_setup


ROOT = Path(__file__).resolve().parents[1]


class VehicleProfileScaffoldTests(unittest.TestCase):
    def make_root(self, base: Path, *, aliases: Optional[List[str]] = None) -> Path:
        root = base / "open-mmi"
        vehicles = root / "vehicles"
        shutil.copytree(ROOT / "vehicles" / "_template", vehicles / "_template")
        existing = vehicles / "existing" / "model" / "one-platform" / "config.json"
        existing.parent.mkdir(parents=True)
        existing.write_text(
            json.dumps({"metadata": {"id": "existing-profile"}}),
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
                            "aliases": aliases or [],
                        }
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return root

    def test_scaffold_creates_valid_registered_experimental_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))

            result = vehicle_profile_scaffold.scaffold_profile(
                root,
                brand="Example",
                model="Road Car",
                generation="Mk2",
                platform="C1",
                year_from=2010,
                year_to=2014,
                maintainers=["Example contributor"],
                market_aliases=["Regional Road Car"],
                bitrate=125000,
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["dry_run"])
            self.assertEqual(result["profile_id"], "example-road-car-mk2-c1")
            profile_path = (
                root / "vehicles/example/road-car/mk2-c1/config.json"
            )
            document = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(document["metadata"]["maturity"], "experimental")
            self.assertEqual(document["metadata"]["qualification"]["level"], "none")
            self.assertEqual(
                document["metadata"]["limitations"],
                [
                    "This scaffold does not claim any confirmed CAN mappings or hardware support."
                ],
            )
            self.assertEqual(document["can_buses"]["comfort"]["bitrate"], 125000)
            self.assertTrue(
                vehicle_profile_conformance.validate_metadata(
                    document, expected_id="example-road-car-mk2-c1"
                )["valid"]
            )
            self.assertTrue(vehicle_setup.validate_profile(document)["valid"])
            self.assertTrue(
                (profile_path.parent / "fixtures/README.md").is_file()
            )
            self.assertTrue(
                (profile_path.parent / "evidence/README.md").is_file()
            )
            self.assertTrue((profile_path.parent / "notes/README.md").is_file())
            readme = (profile_path.parent / "README.md").read_text(encoding="utf-8")
            self.assertIn("does not claim that Open MMI", readme)
            self.assertIn("currently supports this vehicle", readme)

            resolved = profile_catalogue.resolve_profile(
                root, "example-road-car-mk2-c1"
            )
            self.assertEqual(resolved["path"], profile_path)
            tree = profile_catalogue.verify_tree(root)
            self.assertTrue(tree["valid"], tree)
            self.assertEqual(tree["count"], 2)

    def test_dry_run_reports_plan_without_mutating_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))
            before = (root / "vehicles/catalogue.v1.json").read_bytes()

            result = vehicle_profile_scaffold.scaffold_profile(
                root,
                brand="Example",
                model="Model",
                generation="One",
                platform="Platform",
                year_from=2018,
                year_to=2020,
                dry_run=True,
            )

            self.assertTrue(result["dry_run"])
            self.assertFalse((root / result["relative_directory"]).exists())
            self.assertEqual(
                (root / "vehicles/catalogue.v1.json").read_bytes(), before
            )

    def test_cli_scaffold_dry_run_returns_machine_readable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                result = config_cli.main(
                    [
                        "vehicle-setup",
                        "scaffold",
                        "--root",
                        str(root),
                        "--brand",
                        "Example",
                        "--model",
                        "Model",
                        "--generation",
                        "One",
                        "--platform",
                        "Platform",
                        "--year-from",
                        "2018",
                        "--year-to",
                        "2020",
                        "--dry-run",
                    ]
                )

            payload = json.loads(output.getvalue())
            self.assertEqual(result, 0)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(
                payload["profile_id"], "example-model-one-platform"
            )

    def test_duplicate_canonical_or_alias_identity_is_rejected(self) -> None:
        for selected_id in ("existing-profile", "legacy-profile"):
            with self.subTest(selected_id=selected_id), tempfile.TemporaryDirectory() as tmp:
                root = self.make_root(Path(tmp), aliases=["legacy-profile"])
                with self.assertRaisesRegex(
                    vehicle_profile_scaffold.VehicleProfileScaffoldError,
                    "already registered",
                ):
                    vehicle_profile_scaffold.scaffold_profile(
                        root,
                        brand="Example",
                        model="Model",
                        generation="One",
                        platform="Platform",
                        year_from=2018,
                        year_to=2020,
                        profile_id=selected_id,
                    )

    def test_existing_destination_is_rejected_without_catalogue_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))
            destination = root / "vehicles/example/model/one-platform"
            destination.mkdir(parents=True)
            before = (root / "vehicles/catalogue.v1.json").read_bytes()

            with self.assertRaisesRegex(
                vehicle_profile_scaffold.VehicleProfileScaffoldError,
                "destination already exists",
            ):
                vehicle_profile_scaffold.scaffold_profile(
                    root,
                    brand="Example",
                    model="Model",
                    generation="One",
                    platform="Platform",
                    year_from=2018,
                    year_to=2020,
                )

            self.assertEqual(
                (root / "vehicles/catalogue.v1.json").read_bytes(), before
            )

    def test_path_syntax_and_symlinked_parents_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))
            with self.assertRaisesRegex(
                vehicle_profile_scaffold.VehicleProfileScaffoldError,
                "path syntax",
            ):
                vehicle_profile_scaffold.scaffold_profile(
                    root,
                    brand="../escape",
                    model="Model",
                    generation="One",
                    platform="Platform",
                    year_from=2018,
                    year_to=2020,
                )

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = self.make_root(Path(tmp))
            (root / "vehicles/example").symlink_to(
                Path(outside), target_is_directory=True
            )
            with self.assertRaisesRegex(
                vehicle_profile_scaffold.VehicleProfileScaffoldError,
                "contains a symlink",
            ):
                vehicle_profile_scaffold.scaffold_profile(
                    root,
                    brand="Example",
                    model="Model",
                    generation="One",
                    platform="Platform",
                    year_from=2018,
                    year_to=2020,
                )

    def test_failed_catalogue_replace_removes_partial_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))
            catalogue_path = root / "vehicles/catalogue.v1.json"
            before = catalogue_path.read_bytes()
            real_replace = vehicle_profile_scaffold.os.replace

            def replace(source: object, destination: object) -> None:
                if Path(destination) == catalogue_path:
                    raise OSError("simulated catalogue replacement failure")
                real_replace(source, destination)

            with patch.object(vehicle_profile_scaffold.os, "replace", side_effect=replace):
                with self.assertRaisesRegex(
                    vehicle_profile_scaffold.VehicleProfileScaffoldError,
                    "simulated",
                ):
                    vehicle_profile_scaffold.scaffold_profile(
                        root,
                        brand="Example",
                        model="Model",
                        generation="One",
                        platform="Platform",
                        year_from=2018,
                        year_to=2020,
                    )

            self.assertFalse(
                (root / "vehicles/example/model/one-platform").exists()
            )
            self.assertEqual(catalogue_path.read_bytes(), before)

    def test_invalid_year_range_and_bitrate_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self.make_root(Path(tmp))
            with self.assertRaisesRegex(
                vehicle_profile_scaffold.VehicleProfileScaffoldError,
                "model years",
            ):
                vehicle_profile_scaffold.scaffold_profile(
                    root,
                    brand="Example",
                    model="Model",
                    generation="One",
                    platform="Platform",
                    year_from=2020,
                    year_to=2018,
                )
            with self.assertRaisesRegex(
                vehicle_profile_scaffold.VehicleProfileScaffoldError,
                "bitrate",
            ):
                vehicle_profile_scaffold.scaffold_profile(
                    root,
                    brand="Example",
                    model="Model",
                    generation="One",
                    platform="Platform",
                    year_from=2018,
                    year_to=2020,
                    bitrate=0,
                )


if __name__ == "__main__":
    unittest.main()
