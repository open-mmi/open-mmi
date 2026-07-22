from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")


class DocumentationContractTests(unittest.TestCase):
    def test_primary_documentation_is_split_by_audience(self) -> None:
        expected = (
            "docs/README.md",
            "docs/getting-started.md",
            "docs/dashboard.md",
            "docs/media-sources.md",
            "docs/vehicle-setup.md",
            "docs/manual-administration.md",
            "docs/troubleshooting.md",
            "docs/demo-mode.md",
        )
        for relative in expected:
            self.assertTrue((ROOT / relative).is_file(), relative)
        self.assertFalse((ROOT / "README_demo_mode.md").exists())

    def test_readme_remains_a_navigation_page_not_the_complete_manual(self) -> None:
        source = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(source.splitlines()), 450)
        for target in (
            "docs/getting-started.md",
            "docs/vehicle-setup.md",
            "docs/README.md",
            "docs/manual-administration.md",
            "docs/troubleshooting.md",
        ):
            self.assertIn(target, source)
        self.assertIn("Settings → Vehicle setup", source)
        self.assertIn("Settings → System → Software updates", source)
        for relegated_image in (
            "status-dashboard-active.png",
            "install-status.png",
            "manage-help.png",
            "daemon-logs.png",
        ):
            self.assertNotIn(relegated_image, source)

    def test_stale_pre_enablement_claims_do_not_return(self) -> None:
        stale_phrases = (
            "the settings button still cannot",
            "browser button remains disabled",
            "leaving the ui control disabled",
            "unfinished settings workflow",
            "automated tests are still minimal",
            "replay/demo tooling is not yet complete",
            "this is the normal setup path",
            "vehicles/{profile}/config.json",
            "beta/factory-web-dashboard",
            "future coordinator's verification input",
        )
        documents = [ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
        documents.extend((ROOT / "docs").rglob("*.md"))
        documents.append(ROOT / "ui/web_dashboard/README.md")
        combined = "\n".join(path.read_text(encoding="utf-8") for path in documents).casefold()
        for phrase in stale_phrases:
            self.assertNotIn(phrase, combined, phrase)

    def test_local_markdown_links_resolve(self) -> None:
        errors: list[str] = []
        for path in ROOT.rglob("*.md"):
            if any(part in {".git", "node_modules"} for part in path.parts):
                continue
            source = path.read_text(encoding="utf-8")
            for raw_target in LINK_RE.findall(source):
                target = raw_target.strip().split()[0]
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target = target.split("#", 1)[0]
                if not target:
                    continue
                destination = (path.parent / target).resolve()
                try:
                    destination.relative_to(ROOT.resolve())
                except ValueError:
                    errors.append(f"{path.relative_to(ROOT)}: link escapes repository: {target}")
                    continue
                if not destination.exists():
                    errors.append(f"{path.relative_to(ROOT)}: missing link target: {target}")
        self.assertEqual(errors, [], "\n".join(errors))

    def test_each_design_set_is_listed_in_the_design_index(self) -> None:
        index = (ROOT / "docs/design/README.md").read_text(encoding="utf-8")
        design_root = ROOT / "docs/design"
        for directory in sorted(path for path in design_root.iterdir() if path.is_dir()):
            self.assertTrue((directory / "README.md").is_file(), directory.name)
            self.assertIn(f"({directory.name}/README.md)", index, directory.name)


if __name__ == "__main__":
    unittest.main()
