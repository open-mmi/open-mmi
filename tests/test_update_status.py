from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ui.web_dashboard import update_status


class UpdateStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        update_status.clear_cached_status()
        # The container test runner may be root. Product code must refuse to run
        # checkout-local Git configuration as root, so ordinary integration
        # tests model the unprivileged dashboard service.
        self.euid = patch.object(update_status.os, "geteuid", return_value=1000)
        self.euid.start()

    def tearDown(self) -> None:
        self.euid.stop()
        update_status.clear_cached_status()

    def git(self, repository: Path, *arguments: str) -> str:
        result = subprocess.run(
            [
                "git",
                "-c", "commit.gpgSign=false",
                "-c", "tag.gpgSign=false",
                "-C", str(repository),
                *arguments,
            ],
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
            "channel": "nightly",
            "repository_path": str(source),
            "branch": "main",
            "upstream": "origin/main",
            "installed_commit": commit,
            "installed_version": "test-build",
        }
        payload.update(overrides)
        path.write_text(json.dumps(payload), encoding="utf-8")

    @contextlib.contextmanager
    def environment(self, version_file: Path, source_file: Path, policy_file: Path | None = None):
        selected_policy = policy_file or source_file.with_name("update-policy.json")
        with patch.dict(
            os.environ,
            {
                "OPEN_MMI_VERSION_FILE": str(version_file),
                "OPEN_MMI_UPDATE_SOURCE_FILE": str(source_file),
            },
            clear=False,
        ), patch.object(update_status.update_policy, "policy_file", return_value=selected_policy):
            yield

    def write_policy(self, path: Path, channel: str, **overrides: object) -> None:
        payload = {
            "schema_version": 1,
            "channel": channel,
            "updated_at": "2026-07-18T12:00:00+00:00",
        }
        payload.update(overrides)
        path.write_text(json.dumps(payload), encoding="utf-8")
        path.chmod(0o644)

    def test_sudo_cli_git_inspection_drops_to_original_user(self):
        completed = subprocess.CompletedProcess(["git"], 0, stdout="ok\n", stderr="")
        account = SimpleNamespace(pw_dir="/home/driver", pw_name="driver")
        with patch.dict(os.environ, {"SUDO_UID": "1000", "SUDO_GID": "1000"}, clear=False), patch.object(
            update_status.os, "geteuid", return_value=0
        ), patch.object(update_status.pwd, "getpwuid", return_value=account), patch.object(
            update_status.os, "getgrouplist", return_value=[1000, 20]
        ), patch.object(update_status.subprocess, "run", return_value=completed) as run:
            result = update_status._run_git(Path("/home/driver/open-mmi"), ("status", "--short"))
        self.assertEqual(result.stdout.strip(), "ok")
        arguments, keyword = run.call_args
        self.assertEqual(arguments[0][:3], ["git", "-C", "/home/driver/open-mmi"])
        self.assertEqual(keyword["user"], 1000)
        self.assertEqual(keyword["group"], 1000)
        self.assertEqual(keyword["extra_groups"], [1000, 20])
        self.assertEqual(keyword["env"]["HOME"], "/home/driver")
        self.assertEqual(keyword["env"]["USER"], "driver")


    def test_root_git_inspection_without_unprivileged_identity_fails_closed(self):
        repository = Path("/root/open-mmi")
        owner = SimpleNamespace(st_uid=0, st_gid=0)
        with patch.object(update_status.os, "geteuid", return_value=0), patch.dict(
            os.environ, {"SUDO_UID": "", "SUDO_GID": ""}, clear=False
        ), patch.object(Path, "stat", return_value=owner), patch.object(
            update_status.subprocess, "run"
        ) as run:
            with self.assertRaisesRegex(OSError, "Refusing to inspect.*as root"):
                update_status._run_git(repository, ("status", "--short"))
        run.assert_not_called()

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

    def test_remote_descendant_is_fetched_before_comparison(self):
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
        self.assertEqual(payload["update"]["state"], "update-available")
        self.assertTrue(payload["update"]["update_available"])
        self.assertTrue(payload["update"]["remote_differs"])
        self.assertEqual(payload["update"]["available_commit"], remote_commit)

    def test_fetched_remote_divergence_is_not_assumed_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, remote, _initial_commit = self.create_repository(root)
            (source / "local.txt").write_text("local\n", encoding="utf-8")
            self.git(source, "add", "local.txt")
            self.git(source, "commit", "-m", "installed local commit")
            installed_commit = self.git(source, "rev-parse", "HEAD")

            other = root / "other"
            subprocess.run(
                ["git", "clone", "-b", "main", str(remote), str(other)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            self.git(other, "config", "user.name", "Open MMI Test")
            self.git(other, "config", "user.email", "test@example.invalid")
            (other / "remote.txt").write_text("remote\n", encoding="utf-8")
            self.git(other, "add", "remote.txt")
            self.git(other, "commit", "-m", "diverged remote commit")
            remote_commit = self.git(other, "rev-parse", "HEAD")
            self.git(other, "push", "origin", "main")

            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, installed_commit)
            with self.environment(version_file, source_file):
                payload = update_status.check_for_updates()

        self.assertEqual(payload["update"]["state"], "diverged")
        self.assertIsNone(payload["update"]["update_available"])
        self.assertTrue(payload["update"]["remote_differs"])
        self.assertEqual(payload["update"]["available_commit"], remote_commit)

    def test_missing_installed_commit_object_blocks_check(self):
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
        self.assertEqual(payload["source"]["state"], "source-changed")
        self.assertEqual(payload["update"]["state"], "blocked")
        self.assertIsNone(payload["update"]["update_available"])
        self.assertIn("does not match", payload["update"]["error"])

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
                dirty_check = update_status.check_for_updates()
            self.assertEqual(dirty["source"]["state"], "dirty")
            self.assertEqual(dirty_check["update"]["state"], "blocked")
            self.assertIn("local changes", dirty_check["update"]["error"])
            self.git(source, "clean", "-fd")
            self.git(source, "checkout", "--detach", commit)
            update_status.clear_cached_status()
            with self.environment(version_file, source_file):
                detached = update_status.check_for_updates()
        self.assertEqual(detached["source"]["state"], "detached")
        self.assertEqual(detached["update"]["state"], "blocked")
        self.assertIn("detached HEAD", detached["update"]["error"])

    def test_source_change_blocks_check_before_remote_inspection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, installed_commit = self.create_repository(root)
            (source / "README.md").write_text("local candidate\n", encoding="utf-8")
            self.git(source, "commit", "-am", "local candidate")
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, installed_commit)
            with self.environment(version_file, source_file), patch.object(
                update_status, "_remote_commit"
            ) as remote_commit:
                payload = update_status.check_for_updates()
        self.assertEqual(payload["source"]["state"], "source-changed")
        self.assertEqual(payload["update"]["state"], "blocked")
        self.assertFalse(payload["update"]["update_available"])
        self.assertIn("does not match", payload["update"]["error"])
        remote_commit.assert_not_called()

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
                "channel": "nightly",
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

    def test_missing_policy_migrates_as_implicit_nightly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit)
            with self.environment(version_file, source_file):
                payload = update_status.status_payload()
        self.assertEqual(payload["channel"], "nightly")
        self.assertEqual(payload["policy"]["state"], "legacy-nightly")
        self.assertTrue(payload["policy"]["implicit"])
        self.assertEqual(payload["readiness"]["state"], "ready")

    def test_invalid_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            policy_file = root / "update-policy.json"
            version_file.write_text("test-build\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit)
            self.write_policy(policy_file, "nightly", repository="https://evil.test/repo")
            with self.environment(version_file, source_file, policy_file):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["channel"], "invalid")
        self.assertEqual(payload["policy"]["state"], "invalid")
        self.assertEqual(payload["update"]["state"], "blocked")
        self.assertIn("update-policy-invalid", payload["readiness"]["blockers"])

    def test_configure_channel_writes_fixed_policy_and_clears_cached_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            policy_file = root / "update-policy.json"
            version_file.write_text("v0.1.0\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit, installed_version="v0.1.0")
            with self.environment(version_file, source_file, policy_file), patch.object(
                update_status, "_remote_url", return_value="https://github.com/open-mmi/open-mmi.git"
            ):
                payload = update_status.configure_channel("stable")
                written = json.loads(policy_file.read_text(encoding="utf-8"))
        self.assertEqual(written["channel"], "stable")
        self.assertEqual(set(written), {"schema_version", "channel", "updated_at"})
        self.assertEqual(payload["channel"], "stable")
        self.assertEqual(payload["update"]["state"], "not-checked")

    def test_stable_channel_rejects_untrusted_remote(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, commit = self.create_repository(root)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            policy_file = root / "update-policy.json"
            version_file.write_text("v0.1.0\n", encoding="utf-8")
            self.write_descriptor(source_file, source, commit, channel="stable", installed_version="v0.1.0")
            self.write_policy(policy_file, "stable")
            with self.environment(version_file, source_file, policy_file):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["source"]["state"], "untrusted-remote")
        self.assertEqual(payload["update"]["state"], "blocked")
        self.assertIn("not trusted", payload["update"]["error"])

    def test_stable_channel_selects_highest_official_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, installed_commit = self.create_repository(root)
            self.git(source, "tag", "v0.1.0")
            (source / "README.md").write_text("release\n", encoding="utf-8")
            self.git(source, "commit", "-am", "release")
            release_commit = self.git(source, "rev-parse", "HEAD")
            self.git(source, "tag", "v0.2.0")
            self.git(source, "tag", "v0.3.0-beta.1")
            self.git(source, "push", "origin", "main", "--tags")
            self.git(source, "reset", "--hard", installed_commit)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            policy_file = root / "update-policy.json"
            version_file.write_text("v0.1.0\n", encoding="utf-8")
            self.write_descriptor(source_file, source, installed_commit, channel="stable", installed_version="v0.1.0")
            self.write_policy(policy_file, "stable")
            with self.environment(version_file, source_file, policy_file), patch.object(
                update_status, "_remote_url", return_value="git@github.com:open-mmi/open-mmi.git"
            ):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["update"]["state"], "update-available")
        self.assertEqual(payload["update"]["available_version"], "v0.2.0")
        self.assertEqual(payload["update"]["available_commit"], release_commit)
        self.assertTrue(payload["update"]["update_available"])

    def test_beta_channel_accepts_prereleases_and_stable_promotions(self):
        self.assertLess(
            update_status._release_key("v0.2.0-beta.2", "beta"),
            update_status._release_key("v0.2.0-rc.1", "beta"),
        )
        self.assertLess(
            update_status._release_key("v0.2.0-rc.1", "beta"),
            update_status._release_key("v0.2.0", "beta"),
        )
        self.assertIsNone(update_status._release_key("v0.2.0-beta.2", "stable"))
        self.assertIsNone(update_status._release_key("v1.0.0-backend", "beta"))

    def test_release_comparison_detects_rewritten_tag_and_unknown_installed_version(self):
        source = {
            "installed_commit": "a" * 40,
            "installed_version": "v0.2.0",
        }
        rewritten = update_status._release_comparison(
            source, "stable", "v0.2.0", "b" * 40, (0, 2, 0, 3, 0)
        )
        self.assertEqual(rewritten[0], "release-rewritten")
        self.assertIsNone(rewritten[1])

        unknown_source = {
            "installed_commit": "a" * 40,
            "installed_version": "development-build",
        }
        unknown = update_status._release_comparison(
            unknown_source, "stable", "v0.2.0", "b" * 40, (0, 2, 0, 3, 0)
        )
        self.assertEqual(unknown[0], "remote-different")
        self.assertIsNone(unknown[1])

    def test_release_channel_blocks_downgrade(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, _, installed_commit = self.create_repository(root)
            (source / "README.md").write_text("older-release\n", encoding="utf-8")
            self.git(source, "commit", "-am", "older release")
            self.git(source, "tag", "v0.2.0")
            self.git(source, "push", "origin", "main", "--tags")
            self.git(source, "reset", "--hard", installed_commit)
            version_file = root / ".version"
            source_file = root / ".update-source.json"
            policy_file = root / "update-policy.json"
            version_file.write_text("v0.3.0\n", encoding="utf-8")
            self.write_descriptor(source_file, source, installed_commit, channel="stable", installed_version="v0.3.0")
            self.write_policy(policy_file, "stable")
            with self.environment(version_file, source_file, policy_file), patch.object(
                update_status, "_remote_url", return_value="https://github.com/open-mmi/open-mmi"
            ):
                payload = update_status.check_for_updates()
        self.assertEqual(payload["update"]["state"], "downgrade-blocked")
        self.assertFalse(payload["update"]["update_available"])
        self.assertIn("downgrade", payload["update"]["error"])


if __name__ == "__main__":
    unittest.main()
