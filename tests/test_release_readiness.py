import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_release_documents_exist(self):
        for relative in ("CHANGELOG.md", "docs/v1-foundation-migration.md", "docs/release-checklist.md"):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_maintained_profile_standard_and_schema_exist(self):
        self.assertTrue((ROOT / "docs/maintained-profile-standard.md").is_file())
        self.assertTrue((ROOT / "canbusd/data/vehicle-profile.v1.schema.json").is_file())

    def test_ci_runs_the_single_maintained_profile_gate(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "open-mmi-config vehicle-setup conform --root .",
            source,
        )

    def test_reference_profile_declares_qualified_hardware_evidence(self):
        profile = json.loads(
            (ROOT / "vehicles/seat/leon/1p-pq35/config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(profile["schema_version"], 1)
        self.assertEqual(profile["metadata"]["id"], "seat-leon-1p-pq35")
        self.assertEqual(profile["metadata"]["maturity"], "qualified")
        self.assertEqual(
            profile["metadata"]["qualification"]["level"],
            "hardware",
        )


    def test_hierarchical_catalogue_and_replay_fixture_exist(self):
        self.assertTrue((ROOT / "vehicles/catalogue.v1.json").is_file())
        self.assertTrue((ROOT / "vehicles/_template/config.template.json").is_file())
        self.assertTrue((ROOT / "vehicles/seat/leon/1p-pq35/config.json").is_file())
        self.assertTrue(
            (ROOT / "vehicles/seat/leon/1p-pq35/fixtures/mappings.v1.json").is_file()
        )

    def test_ci_runs_the_reference_mapping_replay(self):
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "open-mmi-config vehicle-setup replay --root . seat-leon-1p-pq35",
            source,
        )

    def test_vehicle_profile_scaffold_workflow_is_packaged_and_checked(self):
        self.assertTrue((ROOT / "ui/vehicle_profile_scaffold.py").is_file())
        self.assertTrue((ROOT / "docs/vehicle-profile-scaffolding.md").is_file())
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "open-mmi-config vehicle-setup scaffold",
            source,
        )
        wheel = (ROOT / "tools/verify_wheel.py").read_text(encoding="utf-8")
        self.assertIn('"ui/vehicle_profile_scaffold.py"', wheel)
        self.assertIn('"vehicles/_template/config.template.json"', wheel)

    def test_vehicle_capture_research_workflow_is_packaged_and_checked(self):
        self.assertTrue((ROOT / "ui/vehicle_capture_analysis.py").is_file())
        self.assertTrue((ROOT / "docs/vehicle-capture-analysis.md").is_file())
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "open-mmi-config vehicle-setup capture compare",
            source,
        )
        self.assertIn(
            "open-mmi-config vehicle-setup capture export",
            source,
        )
        wheel = (ROOT / "tools/verify_wheel.py").read_text(encoding="utf-8")
        self.assertIn('"ui/vehicle_capture_analysis.py"', wheel)

    def test_vehicle_qualification_workflow_is_packaged_and_checked(self):
        self.assertTrue((ROOT / "ui/vehicle_profile_qualification.py").is_file())
        self.assertTrue((ROOT / "docs/vehicle-qualification-workflow.md").is_file())
        self.assertTrue((ROOT / "canbusd/data/vehicle-qualification.v1.schema.json").is_file())
        self.assertTrue(
            (ROOT / "vehicles/seat/leon/1p-pq35/evidence/qualification.v1.json").is_file()
        )
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "open-mmi-config vehicle-setup qualification report --root .",
            source,
        )
        wheel = (ROOT / "tools/verify_wheel.py").read_text(encoding="utf-8")
        self.assertIn('"ui/vehicle_profile_qualification.py"', wheel)
        self.assertIn('"canbusd/data/vehicle-qualification.v1.schema.json"', wheel)

    def test_generated_vehicle_catalogue_documents_exist_and_ci_checks_them(self):
        self.assertTrue((ROOT / "docs/vehicle-catalogue.md").is_file())
        self.assertTrue((ROOT / "docs/vehicle-capability-matrix.md").is_file())
        self.assertTrue((ROOT / "tools/generate_vehicle_catalogue_docs.py").is_file())
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "python tools/generate_vehicle_catalogue_docs.py --check",
            source,
        )

    def test_update_management_design_set_exists(self):
        root = ROOT / "docs" / "design" / "v1-update-management"
        for name in (
            "README.md",
            "update-source-and-channels.md",
            "update-status-api.md",
            "update-ui.md",
            "update-execution.md",
            "health-checks-and-rollback.md",
            "security-and-permissions.md",
            "qualification.md",
        ):
            self.assertTrue((root / name).is_file(), name)

    def test_package_ci_verifies_privileged_update_entry_points(self):
        source = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn('"open-mmi-update-coordinator": "ui.update_coordinator:main"', source)
        self.assertIn('"open-mmi-update-installer": "ui.update_installer:main"', source)
        self.assertIn('"open-mmi-vehicle-config-coordinator": "ui.vehicle_config_coordinator:main"', source)

    def test_product_docs_do_not_describe_browser_nightly_installation_as_future(self):
        source = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("same-origin browser flow", source)
        self.assertNotIn(
            "Browser installation, scheduling, unattended updates, and stable/beta installation remain disabled",
            source,
        )

    def test_runtime_dependencies_have_supported_major_bounds(self):
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"python-can>=4.3,<5"', source)
        self.assertIn('"evdev>=1.6,<2"', source)

    def test_server_does_not_contain_transitional_provider_aliases(self):
        source = (ROOT / "ui/web_dashboard/server.py").read_text(encoding="utf-8")
        self.assertNotIn("Transitional private aliases", source)
        self.assertNotIn("Temporary private aliases", source)

    def test_default_media_bindings_use_canonical_actions(self):
        bindings = json.loads((ROOT / "bindings/default.json").read_text(encoding="utf-8"))
        expected = {
            "play_pause": "media.playback.toggle",
            "next_track": "media.playback.next",
            "previous_track": "media.playback.previous",
            "stop_playback": "media.playback.stop",
        }
        for event, action in expected.items():
            self.assertEqual(bindings[event], {"action": action})

    def test_generated_directories_are_ignored(self):
        source = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in ("node_modules/", "playwright-report/", "test-results/"):
            self.assertIn(entry, source)


if __name__ == "__main__":
    unittest.main()
