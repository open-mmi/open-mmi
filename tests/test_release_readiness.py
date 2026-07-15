import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ReleaseReadinessTests(unittest.TestCase):
    def test_release_documents_exist(self):
        for relative in ("CHANGELOG.md", "docs/v1-foundation-migration.md", "docs/release-checklist.md"):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_runtime_dependencies_have_supported_major_bounds(self):
        source = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"python-can>=4.3,<5"', source)
        self.assertIn('"evdev>=1.6,<2"', source)

    def test_server_does_not_contain_transitional_provider_aliases(self):
        source = (ROOT / "ui/web_dashboard/server.py").read_text(encoding="utf-8")
        self.assertNotIn("Transitional private aliases", source)
        self.assertNotIn("Temporary private aliases", source)

    def test_generated_directories_are_ignored(self):
        source = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in ("node_modules/", "playwright-report/", "test-results/"):
            self.assertIn(entry, source)


if __name__ == "__main__":
    unittest.main()
