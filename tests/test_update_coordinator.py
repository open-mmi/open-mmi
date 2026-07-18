from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import update_coordinator


class UpdateCoordinatorTests(unittest.TestCase):
    def test_status_is_the_only_enabled_fixed_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            update_coordinator.write_state(update_coordinator.initial_state(), state_path)
            response = update_coordinator.response_for_request(
                {"api_version": 1, "action": "status"}, state_path
            )
        self.assertTrue(response["ok"])
        self.assertFalse(response["execution_enabled"])
        self.assertEqual(response["state"]["state"], "idle")
        for request in (
            {"api_version": 1, "action": "prepare"},
            {"api_version": 1, "action": "install"},
            {"api_version": 1, "action": "rollback"},
            {"api_version": 1, "action": "status", "path": "/tmp/evil"},
            {"action": "status"},
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

    def test_interrupted_active_state_recovers_to_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            state = update_coordinator.initial_state()
            state.update({"state": "installing", "stage": "installing", "transaction_id": "tx-1"})
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


if __name__ == "__main__":
    unittest.main()
