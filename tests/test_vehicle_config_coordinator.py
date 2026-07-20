from __future__ import annotations

import fcntl
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import vehicle_config_coordinator as coordinator


class VehicleConfigurationCoordinatorTests(unittest.TestCase):
    def test_initial_state_is_strict_read_only_idle_state(self) -> None:
        state = coordinator.initial_state()
        self.assertEqual(state["state"], "idle")
        self.assertEqual(state["stage"], "idle")
        self.assertIsNone(state["target"])
        self.assertFalse(state["restoration_attempted"])
        self.assertFalse(state["restoration_verified"])

    def test_state_round_trip_is_atomic_and_schema_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            state = coordinator.write_state(coordinator.initial_state(), path)
            self.assertEqual(coordinator.read_state(path), state)
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["unexpected"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(coordinator.CoordinatorError, "schema"):
                coordinator.read_state(path)

    def test_target_validation_rejects_paths_and_unbounded_values(self) -> None:
        state = coordinator.initial_state()
        state["target"] = {
            "vehicle": {
                "source": "maintained",
                "id": "../../seat_1p",
                "revision": "sha256:" + "0" * 64,
            },
            "bindings": {
                "source": "maintained",
                "id": "default",
                "revision": "sha256:" + "1" * 64,
            },
            "active_bus": "comfort",
            "interface": "can0",
        }
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(coordinator.CoordinatorError, "identifier"):
                coordinator.write_state(state, Path(temporary) / "state.json")

    def test_recovery_marks_interrupted_state_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state.json"
            state = coordinator.initial_state()
            state.update(
                {
                    "state": "applying",
                    "stage": "applying",
                    "transaction_id": "configuration-" + "a" * 32,
                    "started_at": state["updated_at"],
                }
            )
            coordinator.write_state(state, path)
            recovered = coordinator.recover_interrupted_state(path)
            self.assertEqual(recovered["state"], "failed")
            self.assertEqual(recovered["stage"], "recovery")
            self.assertTrue(recovered["recovered"])
            self.assertIn("restarted", recovered["error"])

    def test_configuration_locks_reserve_lifecycle_and_configuration_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configuration = root / "configuration.lock"
            lifecycle = root / "lifecycle.lock"
            update = root / "update.lock"
            with coordinator.ConfigurationTransactionLocks(configuration, lifecycle, update):
                with self.assertRaisesRegex(coordinator.CoordinatorError, "lifecycle"):
                    with coordinator.ConfigurationTransactionLocks(
                        root / "other-configuration.lock",
                        lifecycle,
                        root / "other-update.lock",
                    ):
                        pass
                with self.assertRaisesRegex(coordinator.CoordinatorError, "configuration"):
                    with coordinator.TransactionLock(
                        configuration,
                        "Another vehicle configuration transaction is active",
                    ):
                        pass

    def test_active_update_lock_blocks_configuration_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            update = root / "update.lock"
            with coordinator.TransactionLock(update, "busy"):
                with self.assertRaisesRegex(coordinator.CoordinatorError, "update"):
                    with coordinator.ConfigurationTransactionLocks(
                        root / "configuration.lock",
                        root / "lifecycle.lock",
                        update,
                    ):
                        pass

    def test_status_protocol_is_exact_and_apply_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            coordinator.write_state(coordinator.initial_state(), state_path)
            response = coordinator.response_for_request(
                {"api_version": 1, "action": "status"},
                state_path,
                root / "configuration.lock",
                root / "lifecycle.lock",
                root / "update.lock",
            )
            self.assertTrue(response["ok"])
            self.assertTrue(response["read_only"])
            self.assertFalse(response["preview_enabled"])
            self.assertFalse(response["apply_enabled"])
            self.assertFalse(response["restore_enabled"])
            self.assertEqual(
                response["locks"],
                {
                    "configuration_active": False,
                    "lifecycle_active": False,
                    "update_active": False,
                },
            )

            self.assertEqual(
                coordinator.response_for_request(
                    {"api_version": 1, "action": "apply"}, state_path
                ),
                {"ok": False, "error": "Coordinator action is not enabled"},
            )
            self.assertEqual(
                coordinator.response_for_request(
                    {"api_version": 1, "action": "status", "path": "/etc/shadow"},
                    state_path,
                ),
                {"ok": False, "error": "Invalid coordinator request schema"},
            )

    def test_status_reports_an_active_update_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            update_lock = root / "update.lock"
            coordinator.write_state(coordinator.initial_state(), state_path)
            update_lock.touch()
            update_lock.chmod(0o644)
            with update_lock.open("r+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                response = coordinator.response_for_request(
                    {"api_version": 1, "action": "status"},
                    state_path,
                    root / "configuration.lock",
                    root / "lifecycle.lock",
                    update_lock,
                )
            self.assertTrue(response["ok"])
            self.assertTrue(response["locks"]["update_active"])

    def test_socket_server_and_client_use_fixed_status_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            socket_path = root / "coordinator.sock"
            state_path = root / "state.json"
            coordinator.write_state(coordinator.initial_state(), state_path)
            group = type("Group", (), {"gr_gid": os.getgid()})()
            with patch.object(coordinator.grp, "getgrnam", return_value=group), patch.object(
                coordinator.os, "chown"
            ):
                server = coordinator.CoordinatorServer(socket_path, state_path)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    response = coordinator.client_status(socket_path)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            self.assertTrue(response["ok"])
            self.assertEqual(response["state"]["state"], "idle")
            self.assertFalse(socket_path.exists())

    def test_server_refuses_untrusted_existing_socket_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            socket_path = root / "coordinator.sock"
            socket_path.write_text("not a socket", encoding="utf-8")
            with self.assertRaisesRegex(coordinator.CoordinatorError, "untrusted"):
                coordinator.CoordinatorServer(socket_path, root / "state.json")

    def test_client_fails_closed_when_socket_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(coordinator.CoordinatorError, "unavailable"):
                coordinator.client_status(Path(temporary) / "missing.sock")


if __name__ == "__main__":
    unittest.main()
