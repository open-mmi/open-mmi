import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_release_documents_exist(self):
        for relative in ("CHANGELOG.md", "docs/v1-foundation-migration.md", "docs/release-checklist.md"):
            self.assertTrue((ROOT / relative).is_file(), relative)

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

    def test_default_media_bindings_use_transport_actions(self):
        bindings = json.loads((ROOT / "bindings/default.json").read_text(encoding="utf-8"))
        expected = {
            "play_pause": "play_pause",
            "next_track": "next_track",
            "previous_track": "prev_track",
            "stop_playback": "stop",
        }
        for event, function in expected.items():
            self.assertEqual(bindings[event]["module"], "audio")
            self.assertEqual(bindings[event]["func"], function)

    def test_generated_directories_are_ignored(self):
        source = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in ("node_modules/", "playwright-report/", "test-results/"):
            self.assertIn(entry, source)


if __name__ == "__main__":
    unittest.main()
