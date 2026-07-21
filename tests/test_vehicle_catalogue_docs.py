from __future__ import annotations

import copy
import unittest
from pathlib import Path

from tools import generate_vehicle_catalogue_docs
from ui import vehicle_profile_conformance


ROOT = Path(__file__).resolve().parents[1]


class VehicleCatalogueDocumentationTests(unittest.TestCase):
    @staticmethod
    def report() -> dict[str, object]:
        base_profile = {
            "id": "alpha-one-a-platform",
            "aliases": ["alpha_legacy"],
            "path": "vehicles/alpha/one/a-platform/config.json",
            "valid": True,
            "metadata": {
                "id": "alpha-one-a-platform",
                "display_name": "Alpha One A (Platform)",
                "manufacturer": "Alpha",
                "model": "One",
                "generation": "A",
                "platform": "Platform",
                "market_aliases": ["Beta One A"],
                "model_years": {"from": 2010, "to": 2014},
                "maturity": "qualified",
                "qualification": {
                    "level": "hardware",
                    "last_tested": "2026-07-20",
                    "scope": ["Passive CAN reception"],
                    "evidence": [
                        {
                            "kind": "hardware",
                            "path": "docs/alpha.md",
                            "description": "Hardware qualification.",
                        },
                        {
                            "kind": "replay",
                            "path": "vehicles/alpha/fixtures.json",
                            "description": "Replay proof.",
                        },
                    ],
                },
                "limitations": ["Example limitation."],
            },
            "capabilities": {
                "buses": ["comfort"],
                "events": ["play_pause", "volume_up"],
                "statuses": ["doors.front_left"],
                "event_count": 2,
                "status_count": 1,
            },
            "qualification": {
                "level": "hardware",
                "tested_on": "2026-07-20",
                "review_status": "approved",
                "reviewers": ["Reviewer One"],
                "reviewed_on": "2026-07-20",
                "recheck_after": "2027-07-20",
                "compatibility": {
                    "equipment": ["Example CAN adapter"],
                    "variants": ["Alpha One A model years 2010 to 2014"],
                },
                "history_count": 2,
                "stale": False,
                "validation": {"valid": True, "errors": [], "warnings": []},
            },
            "fixtures": {
                "present": True,
                "valid": True,
                "path": "fixtures/mappings.v1.json",
                "case_count": 3,
                "coverage": {
                    "events": 2,
                    "event_total": 2,
                    "statuses": 1,
                    "status_total": 1,
                },
            },
            "validation": {"valid": True, "errors": [], "warnings": []},
        }
        second = copy.deepcopy(base_profile)
        second["id"] = "zeta-two-b-platform"
        second["aliases"] = []
        second["path"] = "vehicles/zeta/two/b-platform/config.json"
        second["metadata"].update(
            {
                "id": "zeta-two-b-platform",
                "display_name": "Zeta Two B (Platform)",
                "manufacturer": "Zeta",
                "model": "Two",
                "generation": "B",
                "market_aliases": [],
            }
        )
        second["capabilities"] = {
            "buses": ["comfort"],
            "events": ["play_pause"],
            "statuses": ["vehicle.speed_kmh"],
            "event_count": 1,
            "status_count": 1,
        }
        return {
            "standard": "open-mmi.maintained-vehicle-profile",
            "schema_version": 1,
            "valid": True,
            "count": 2,
            "summary": {"valid": 2, "invalid": 0, "maturity": {"qualified": 2}},
            "profiles": [second, base_profile],
        }

    def test_catalogue_document_groups_navigation_and_reports_evidence(self) -> None:
        rendered = generate_vehicle_catalogue_docs.render_catalogue(self.report())
        self.assertLess(rendered.index("**Alpha**"), rendered.index("**Zeta**"))
        self.assertIn("`alpha_legacy`", rendered)
        self.assertIn("Beta One A", rendered)
        self.assertIn("3 cases; 2/2 events; 1/1 statuses", rendered)
        self.assertIn("hardware: 1, replay: 1", rendered)
        self.assertIn("last tested `2026-07-20`", rendered)
        self.assertIn("recheck after `2027-07-20`", rendered)
        self.assertIn("Example CAN adapter", rendered)

    def test_capability_matrix_distinguishes_supported_descriptors(self) -> None:
        rendered = generate_vehicle_catalogue_docs.render_capability_matrix(self.report())
        self.assertIn(
            "| `volume_up` | Yes | — |",
            rendered,
        )
        self.assertIn(
            "| `vehicle.speed_kmh` | — | Yes |",
            rendered,
        )

    def test_repository_generated_documents_are_current(self) -> None:
        catalogue, matrix = generate_vehicle_catalogue_docs.render_documents(ROOT)
        self.assertEqual(
            (ROOT / "docs/vehicle-catalogue.md").read_text(encoding="utf-8"),
            catalogue,
        )
        self.assertEqual(
            (ROOT / "docs/vehicle-capability-matrix.md").read_text(encoding="utf-8"),
            matrix,
        )

    def test_invalid_catalogue_is_not_documented(self) -> None:
        report = self.report()
        report["valid"] = False
        report["profiles"][0]["valid"] = False
        report["profiles"][0]["validation"] = {
            "valid": False,
            "errors": [{"message": "broken fixture"}],
            "warnings": [],
        }
        with self.assertRaisesRegex(ValueError, "broken fixture"):
            generate_vehicle_catalogue_docs.render_catalogue(report)

    def test_optional_market_aliases_are_validated(self) -> None:
        document = {
            "schema_version": 1,
            "metadata": {
                "id": "example_car",
                "display_name": "Example Car",
                "manufacturer": "Example",
                "model": "Car",
                "generation": "One",
                "platform": "Example Platform",
                "market_aliases": ["Example Car Regional Name"],
                "model_years": {"from": 2010, "to": 2014},
                "maturity": "experimental",
                "license": "GPL-3.0-only",
                "maintainers": ["Open MMI contributors"],
                "qualification": {
                    "level": "none",
                    "last_tested": None,
                    "scope": [],
                    "evidence": [],
                },
                "limitations": [],
            },
            "default_bus": "comfort",
            "can_buses": {"comfort": {"interface": "can0"}},
            "rules": [],
            "presence": [],
            "status": [],
        }
        result = vehicle_profile_conformance.validate_metadata(
            document, expected_id="example_car"
        )
        self.assertTrue(result["valid"], result)

        document["metadata"]["market_aliases"] = ["Duplicate", "Duplicate"]
        result = vehicle_profile_conformance.validate_metadata(
            document, expected_id="example_car"
        )
        self.assertIn(
            "duplicate-value",
            {issue["code"] for issue in result["errors"]},
        )


if __name__ == "__main__":
    unittest.main()
