from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui.web_dashboard import update_status


class UpdateStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        update_status.clear_cached_status()

    def tearDown(self) -> None:
        update_status.clear_cached_status()

    def git(self, repository: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def create_repository(self, root: Path) -> tuple[Path, Path, str]:
        remote = root / "remote.git"
        source = root / "source"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "init", "-b", "main", str(source)], check=True, stdout=subprocess.DEVNULL)
        self.git(source, "config", "user.name", "Open MMI Test")
        self.git(source, "config", "user.email", "test@example.invalid")
        (source / "README.md").write_text("initial\n", encoding="utf-8")
        self.git(source, "add", "README.md")
        self.git(source, "commit", "-m", "initial")
        self.git(source, "remote", "add", "origin", str(remote))
        self.git(source, "push", "-u", "origin", "main")
        return source, remote, self.git(source, "rev-parse", "HEAD")

    def write_descriptor(self, path: Path, source: Path, commit: str, **overrides: object) -> None:
        payload = {
            "schema_version": 1,
            "channel": "development",
            "repository_path": str(source),
            "branch": "main",
            "upstream": "origin/main",
            "installed_commit": commit,
            "installed_version": "test-build",
        }
        payload.update(overrides)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def environment(self, version_file: Path, source_file: Path):
        return patch.dict(
            os.environ,
            {
                "OPEN_MMI_VERSION_FILE": str(version_file),
                "OPEN_MMI_UPDATE_SOURCE_FILE": str(source_file),
            },
            clear=False,
        )

    def test_status_without_source_never_claims_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("installed-build\n", encoding="utf-8")
            with self.environment(version_file, source_file):
                payload = update_status.status_payload()
        self.assertEqual(payload["installed"]["version"], "installed-build")
        self.assertEqual(payload["source"]["state"], "unconfigured")
        self.assertEqual(payload["update"]["state"], "not-checked")
        self.assertEqual(payload["readiness"]["state"], "blocked")

    def test_descriptor_version_without_managed_version_file_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            self.write_descriptor(source_file, source, commit)
            with self.environment(version_file, source_file):
                payload = update_status.status_payload()
        self.assertFalse(payload["installed"]["managed"])
        self.assertEqual(payload["installed"]["version"], "test-build")
        self.assertEqual(payload["readiness"]["state"], "blocked")
        self.assertIn("installed-version-unknown", payload["readiness"]["blockers"])

    def test_version_metadata_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("different-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit)
            with self.environment(version_file, source_file):
                payload = update_status.status_payload()
        self.assertTrue(payload["installed"]["managed"])
        self.assertEqual(payload["installed"]["version"], "different-build")
        self.assertIn("installed-metadata-mismatch", payload["readiness"]["blockers"])

    def test_clean_tracked_repository_reports_up_to_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit)
            with self.environment(version_file, source_file):
                before = update_status.status_payload()
                after = update_status.check_for_updates()
        self.assertEqual(before["source"]["state"], "ready")
        self.assertEqual(before["update"]["state"], "not-checked")
        self.assertEqual(after["update"]["state"], "up-to-date")
        self.assertFalse(after["update"]["remote_differs"])
        self.assertFalse(after["update"]["update_available"])
        self.assertTrue(after["update"]["checked_at"])

    def test_proven_descendant_is_update_available(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, installed_commit = self.create_repository(root)
            (source / "README.md").write_text("second\n", encoding="utf-8")
            self.git(source, "commit", "-am", "second")
            remote_commit = self.git(source, "rev-parse", "HEAD")
            self.git(source, "push", "origin", "main")
            self.git(source, "reset", "--hard", installed_commit)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, installed_commit)
            with self.environment(version_file, source_file):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["update"]["state"], "update-available")
        self.assertTrue(payload["update"]["update_available"])
        self.assertEqual(payload["update"]["available_commit"], remote_commit)

    def test_unknown_ancestry_is_remote_different_not_assumed_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, remote, installed_commit = self.create_repository(root)
            other = root / "other"
            subprocess.run(["git", "clone", "-b", "main", str(remote), str(other)], check=True, stdout=subprocess.DEVNULL)
            self.git(other, "config", "user.name", "Open MMI Test")
            self.git(other, "config", "user.email", "test@example.invalid")
            (other / "remote.txt").write_text("remote\n", encoding="utf-8")
            self.git(other, "add", "remote.txt")
            self.git(other, "commit", "-m", "remote")
            remote_commit = self.git(other, "rev-parse", "HEAD")
            self.git(other, "push", "origin", "main")
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, installed_commit)
            with self.environment(version_file, source_file):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["update"]["state"], "remote-different")
        self.assertIsNone(payload["update"]["update_available"])
        self.assertTrue(payload["update"]["remote_differs"])
        self.assertEqual(payload["update"]["available_commit"], remote_commit)

    def test_missing_installed_commit_object_is_remote_different(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, current_commit = self.create_repository(root)
            missing_commit = "f" * 40
            self.assertNotEqual(current_commit, missing_commit)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, missing_commit)
            with self.environment(version_file, source_file):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["update"]["state"], "remote-different")
        self.assertIsNone(payload["update"]["update_available"])

    def test_dirty_and_detached_sources_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit)
            (source / "local.txt").write_text("dirty\n", encoding="utf-8")
            with self.environment(version_file, source_file):
                dirty = update_status.status_payload()
            self.assertEqual(dirty["source"]["state"], "dirty")
            self.git(source, "clean", "-fd")
            self.git(source, "checkout", "--detach", commit)
            update_status.clear_cached_status()
            with self.environment(version_file, source_file):
                detached = update_status.check_for_updates()
        self.assertEqual(detached["source"]["state"], "detached")
        self.assertEqual(detached["update"]["state"], "blocked")
        self.assertIn("detached HEAD", detached["update"]["error"])

    def test_unreachable_remote_is_unavailable_not_up_to_date(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            self.git(source, "remote", "set-url", "origin", str(root / "missing.git"))
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit)
            with self.environment(version_file, source_file):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["update"]["state"], "unavailable")
        self.assertIsNone(payload["update"]["update_available"])
        self.assertNotIn(str(root), payload["update"]["error"])

    def test_invalid_descriptor_and_overlapping_check_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_file = root / ".update-source.json"
            version_file = root / ".version"
            version_file.write_text("test-build\n", encoding="utf-8")
            source_file.write_text(json.dumps({
                "schema_version": 1,
                "channel": "development",
                "repository_path": str(root),
                "branch": "--upload-pack=bad",
                "upstream": "origin/main",
                "installed_commit": "a" * 40,
                "installed_version": "test-build",
            }), encoding="utf-8")
            with self.environment(version_file, source_file):
                payload = update_status.check_for_updates()
            self.assertEqual(payload["update"]["state"], "source-invalid")

        update_status._CHECK_LOCK.acquire()
        try:
            with self.assertRaisesRegex(update_status.UpdateStatusError, "already in progress"):
                update_status.check_for_updates()
        finally:
            update_status._CHECK_LOCK.release()


if __name__ == "__main__":
    unittest.main()
