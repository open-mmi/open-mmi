from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ui import update_coordinator


class UpdateCoordinatorTests(unittest.TestCase):
    def git(self, repository: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10,
            env={**os.environ, "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "tag.gpgSign",
                 "GIT_CONFIG_VALUE_0": "false", "GIT_CONFIG_KEY_1": "commit.gpgSign",
                 "GIT_CONFIG_VALUE_1": "false"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_status_and_confirmed_prepare_are_the_only_enabled_fixed_requests(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            update_coordinator.write_state(update_coordinator.initial_state(), state_path)
            response = update_coordinator.response_for_request(
                {"api_version": 1, "action": "status"}, state_path
            )
        self.assertTrue(response["ok"])
        self.assertFalse(response["execution_enabled"])
        self.assertTrue(response["preparation_enabled"])
        self.assertFalse(response["installation_enabled"])
        self.assertEqual(response["state"]["state"], "idle")
        for request in (
            {"api_version": 1, "action": "install"},
            {"api_version": 1, "action": "rollback"},
            {"api_version": 1, "action": "status", "path": "/tmp/evil"},
            {"action": "status"},
        ):
            self.assertFalse(update_coordinator.response_for_request(request, state_path)["ok"])

        prepared = dict(update_coordinator.initial_state(), state="prepared", stage="prepared")
        with patch.object(update_coordinator, "_prepare_candidate", return_value=prepared) as prepare:
            response = update_coordinator.response_for_request(
                {"api_version": 1, "action": "prepare", "confirm": True},
                state_path, Path(temporary) / "lock", Path(temporary) / "staging",
            )
        self.assertTrue(response["ok"])
        self.assertEqual(response["state"]["state"], "prepared")
        prepare.assert_called_once()

        for request in (
            {"api_version": 1, "action": "prepare"},
            {"api_version": 1, "action": "prepare", "confirm": False},
            {"api_version": 1, "action": "prepare", "confirm": True, "url": "https://evil.test"},
        ):
            self.assertFalse(update_coordinator.response_for_request(request, state_path)["ok"])

    def test_state_is_atomic_strict_and_mode_0644(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            state = update_coordinator.initial_state()
            rendered = update_coordinator.write_state(state, path)
            self.assertEqual(update_coordinator.read_state(path), rendered)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            malformed = dict(state, command="sh")
            with self.assertRaises(update_coordinator.CoordinatorError):
                update_coordinator.write_state(malformed, path)

    def test_schema_one_state_migrates_without_losing_transaction_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            state = update_coordinator.initial_state()
            state.pop("candidate_commit")
            state["schema_version"] = 1
            path.write_text(json.dumps(state), encoding="utf-8")
            migrated = update_coordinator.recover_interrupted_state(path)
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["candidate_commit"], "")

    def test_interrupted_active_state_recovers_to_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            state = update_coordinator.initial_state()
            state.update({
                "state": "installing", "stage": "installing",
                "transaction_id": "prepare-0123456789abcdef0123456789abcdef",
            })
            update_coordinator.write_state(state, path)
            recovered = update_coordinator.recover_interrupted_state(path)
        self.assertEqual(recovered["state"], "failed")
        self.assertEqual(recovered["stage"], "recovery")
        self.assertTrue(recovered["recovered"])
        self.assertNotIn("/", recovered["error"])

    def test_transaction_lock_prevents_overlap_and_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "update.lock"
            with update_coordinator.TransactionLock(path):
                self.assertTrue(path.exists())
                with self.assertRaisesRegex(update_coordinator.CoordinatorError, "Another update"):
                    with update_coordinator.TransactionLock(path):
                        pass
            self.assertTrue(path.exists())

    def test_production_state_write_requires_root(self):
        with patch.object(update_coordinator.os, "geteuid", return_value=1000):
            with self.assertRaisesRegex(update_coordinator.CoordinatorError, "requires root"):
                update_coordinator.write_state(update_coordinator.initial_state())

    def test_staging_cleanup_refuses_paths_outside_transaction_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "staging"
            outside = Path(temporary) / "important"
            outside.mkdir()
            with self.assertRaisesRegex(update_coordinator.CoordinatorError, "staging path"):
                update_coordinator._safe_remove_staging(outside, root)
            self.assertTrue(outside.exists())

    def test_client_request_raises_for_coordinator_failure_response(self):
        fake_socket = MagicMock()
        fake_socket.__enter__.return_value = fake_socket
        fake_socket.makefile.return_value.readline.return_value = b'{"ok": false, "error": "No candidate"}\n'
        with patch.object(update_coordinator.socket, "socket", return_value=fake_socket):
            with self.assertRaisesRegex(update_coordinator.CoordinatorError, "No candidate"):
                update_coordinator.client_prepare(Path("/tmp/coordinator.sock"))

    def test_prepare_stages_proven_candidate_without_installing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = root / "source"
            repository.mkdir()
            state_path = root / "state.json"
            lock_path = root / "update.lock"
            staging_root = root / "staging"
            installed = "1" * 40
            candidate = "2" * 40
            source = {
                "repository_path": str(repository), "installed_commit": installed,
                "installed_version": "old", "branch": "main", "upstream": "origin/main",
                "remote": "origin", "remote_branch": "main", "recorded_channel": "development",
            }
            with patch.object(update_coordinator.update_status, "_read_source_descriptor", return_value=(source, "configured")), patch.object(
                update_coordinator.update_policy, "read_policy", return_value=({"channel": "development"}, "configured")
            ), patch.object(update_coordinator.update_status, "_repository_snapshot", return_value={"state": "ready"}), patch.object(
                update_coordinator, "_preparation_readiness"
            ), patch.object(update_coordinator, "_candidate", return_value=(candidate[:12], candidate, "")), patch.object(
                update_coordinator.update_status, "_remote_url", return_value="https://example.invalid/open-mmi.git"
            ), patch.object(update_coordinator.update_status, "_run_git", return_value=SimpleNamespace(returncode=0)), patch.object(
                update_coordinator.update_status, "_git_success", return_value=True
            ), patch.object(
                update_coordinator, "_secure_staging_tree"
            ), patch.object(update_coordinator.uuid, "uuid4", return_value=SimpleNamespace(hex="a" * 32)):
                prepared = update_coordinator._prepare_candidate(state_path, lock_path, staging_root)
        self.assertEqual(prepared["state"], "prepared")
        self.assertEqual(prepared["candidate_commit"], candidate)
        self.assertEqual(prepared["previous_version"], "old")
        self.assertFalse(prepared["error"])

    def test_development_candidate_is_cloned_and_forward_ancestry_is_proved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            source = root / "source"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "init", "-b", "main", str(source)], check=True, stdout=subprocess.DEVNULL)
            self.git(source, "config", "user.name", "Open MMI Test")
            self.git(source, "config", "user.email", "test@example.invalid")
            (source / "README.md").write_text("one\n", encoding="utf-8")
            self.git(source, "add", "README.md")
            self.git(source, "commit", "-m", "one")
            installed = self.git(source, "rev-parse", "HEAD")
            self.git(source, "remote", "add", "origin", str(remote))
            self.git(source, "push", "-u", "origin", "main")
            (source / "README.md").write_text("two\n", encoding="utf-8")
            self.git(source, "commit", "-am", "two")
            candidate = self.git(source, "rev-parse", "HEAD")
            self.git(source, "push", "origin", "main")
            self.git(source, "reset", "--hard", installed)
            descriptor = {
                "repository_path": str(source), "installed_commit": installed,
                "installed_version": "old", "branch": "main", "upstream": "origin/main",
                "remote": "origin", "remote_branch": "main", "recorded_channel": "development",
            }
            with patch.object(update_coordinator.update_status, "_read_source_descriptor", return_value=(descriptor, "configured")), patch.object(
                update_coordinator.update_policy, "read_policy", return_value=({"channel": "development"}, "configured")
            ), patch.object(update_coordinator, "_preparation_readiness"), patch.object(
                update_coordinator.update_status.os, "geteuid", return_value=1000
            ), patch.object(
                update_coordinator, "_secure_staging_tree"
            ):
                prepared = update_coordinator._prepare_candidate(
                    root / "state.json", root / "update.lock", root / "staging"
                )
            stage = root / "staging" / prepared["transaction_id"]
            self.assertEqual(prepared["state"], "prepared")
            self.assertEqual(prepared["candidate_commit"], candidate)
            self.assertEqual(self.git(stage, "rev-parse", "HEAD"), candidate)
            self.assertEqual(self.git(source, "rev-parse", "HEAD"), installed)


if __name__ == "__main__":
    unittest.main()
