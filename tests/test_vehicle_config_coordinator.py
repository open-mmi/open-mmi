from __future__ import annotations

import fcntl
import io
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from ui import vehicle_config_coordinator as coordinator
from ui import vehicle_setup


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
            self.assertTrue(response["preview_enabled"])
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

    def test_preview_protocol_rebuilds_the_plan_inside_the_coordinator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            maintained = root / "installed"
            custom = root / "custom"
            profile = maintained / "vehicles" / "seat_1p" / "config.json"
            bindings = maintained / "bindings" / "default.json"
            profile.parent.mkdir(parents=True)
            bindings.parent.mkdir(parents=True)
            profile.write_text(
                json.dumps(
                    {
                        "default_bus": "comfort",
                        "can_buses": {
                            "comfort": {
                                "interface": "can0",
                                "bitrate": 100000,
                                "provisioning": "udev",
                            }
                        },
                        "rules": [
                            {
                                "id": "0x100",
                                "byte": 0,
                                "value": 1,
                                "event": "play_pause",
                            }
                        ],
                        "presence": [],
                        "status": [],
                    }
                ),
                encoding="utf-8",
            )
            bindings.write_text(
                json.dumps(
                    {
                        "play_pause": {
                            "module": "audio",
                            "func": "play_pause",
                        }
                    }
                ),
                encoding="utf-8",
            )
            dropin = root / "10-can-runtime.conf"
            dropin.write_text(
                '[Service]\nEnvironment="OPEN_MMI_VEHICLE=seat_1p" '
                '"OPEN_MMI_BINDINGS=default" '
                '"OPEN_MMI_CAN_BUS=comfort" '
                '"OPEN_MMI_CAN_INTERFACE=can0"\n',
                encoding="utf-8",
            )
            request = {
                "vehicle": {"source": "maintained", "id": "seat_1p"},
                "bindings": {"source": "maintained", "id": "default"},
                "runtime": {
                    "active_bus": "comfort",
                    "buses": {"comfort": {"interface": "can0"}},
                },
            }
            response = coordinator.response_for_request(
                {
                    "api_version": 1,
                    "action": "preview",
                    "request": request,
                },
                root / "state.json",
                root / "configuration.lock",
                root / "lifecycle.lock",
                root / "update.lock",
                preview_roots=vehicle_setup.CatalogueRoots(maintained, custom),
                preview_dropin_path=dropin,
                preview_status_path=root / "missing-status.json",
                preview_sys_class_net=root / "missing-sysfs",
            )

            self.assertTrue(response["ok"])
            preview = response["preview"]
            self.assertTrue(preview["read_only"])
            self.assertFalse(preview["apply_available"])
            self.assertEqual(preview["state"], "ready")
            self.assertEqual(preview["plan"]["changes"], [])
            self.assertRegex(
                preview["expected_configuration_revision"],
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertEqual(
                preview["coordinator"],
                {
                    "previewed": True,
                    "read_only": True,
                    "locks": {
                        "configuration_active": False,
                        "lifecycle_active": False,
                        "update_active": False,
                    },
                    "apply_blocked": False,
                },
            )
            rendered = json.dumps(response)
            self.assertNotIn(str(root), rendered)
            self.assertNotIn("manage.sh", rendered)

    def test_preview_reports_lock_conflicts_without_acquiring_a_mutation_lock(self) -> None:
        request = {
            "vehicle": {"source": "maintained", "id": "seat_1p"},
            "bindings": {"source": "maintained", "id": "default"},
            "runtime": {
                "active_bus": "comfort",
                "buses": {"comfort": {"interface": "can0"}},
            },
        }
        preview = {
            "api_version": 1,
            "read_only": True,
            "apply_available": False,
            "state": "ready",
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            update_lock = root / "update.lock"
            with coordinator.TransactionLock(update_lock, "busy"):
                with patch.object(
                    coordinator.vehicle_setup,
                    "preview_payload",
                    return_value=preview,
                ), patch.object(
                    coordinator.vehicle_setup,
                    "status_payload",
                    return_value={"active": {}, "interfaces": []},
                ), patch.object(
                    coordinator.vehicle_setup,
                    "read_runtime_environment",
                    return_value={},
                ):
                    result = coordinator.coordinator_preview(
                        request,
                        roots=vehicle_setup.CatalogueRoots(
                            root / "installed", root / "custom"
                        ),
                        dropin_path=root / "dropin.conf",
                        status_path=root / "status.json",
                        sys_class_net=root / "sys",
                        configuration_lock=root / "configuration.lock",
                        lifecycle_lock=root / "lifecycle.lock",
                        update_lock=update_lock,
                    )
            self.assertTrue(result["coordinator"]["apply_blocked"])
            self.assertTrue(
                result["coordinator"]["locks"]["update_active"]
            )

    def test_preview_protocol_rejects_paths_and_unknown_outer_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            coordinator.write_state(coordinator.initial_state(), state_path)
            request = {
                "vehicle": {"source": "maintained", "id": "../seat_1p"},
                "bindings": {"source": "maintained", "id": "default"},
                "runtime": {
                    "active_bus": "comfort",
                    "buses": {"comfort": {"interface": "can0"}},
                },
            }
            response = coordinator.response_for_request(
                {
                    "api_version": 1,
                    "action": "preview",
                    "request": request,
                },
                state_path,
                root / "configuration.lock",
                root / "lifecycle.lock",
                root / "update.lock",
                preview_roots=vehicle_setup.CatalogueRoots(
                    root / "installed", root / "custom"
                ),
                preview_dropin_path=root / "dropin.conf",
                preview_status_path=root / "status.json",
                preview_sys_class_net=root / "sys",
            )
            self.assertFalse(response["ok"])
            self.assertIn("invalid", response["error"].lower())
            self.assertEqual(
                coordinator.response_for_request(
                    {
                        "api_version": 1,
                        "action": "preview",
                        "request": {},
                        "path": "/etc/shadow",
                    },
                    state_path,
                ),
                {"ok": False, "error": "Invalid coordinator request schema"},
            )

    def test_preview_context_rejects_relative_root_configuration(self) -> None:
        with patch.dict(
            coordinator.os.environ,
            {"OPEN_MMI_INSTALL_DIR": "relative/install"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                coordinator.CoordinatorError, "absolute fixed path"
            ):
                coordinator._preview_context()

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
                    target = {
                        "vehicle": {
                            "source": "maintained",
                            "id": "seat_1p",
                            "revision": "sha256:" + "a" * 64,
                        },
                        "bindings": {
                            "source": "maintained",
                            "id": "default",
                            "revision": "sha256:" + "b" * 64,
                        },
                        "runtime": {
                            "mode": "single",
                            "active_bus": "comfort",
                            "buses": {"comfort": {"interface": "can0"}},
                        },
                    }
                    expected_preview = {
                        "api_version": 1,
                        "read_only": True,
                        "apply_available": False,
                        "state": "ready",
                        "expected_configuration_revision": "sha256:" + "c" * 64,
                        "target_configuration_revision": coordinator.vehicle_configuration.selection_revision(target),
                        "target": target,
                        "coordinator": {
                            "previewed": True,
                            "read_only": True,
                            "locks": {
                                "configuration_active": False,
                                "lifecycle_active": False,
                                "update_active": False,
                            },
                            "apply_blocked": False,
                        },
                    }
                    request = {
                        "vehicle": {"source": "maintained", "id": "seat_1p"},
                        "bindings": {"source": "maintained", "id": "default"},
                        "runtime": {
                            "active_bus": "comfort",
                            "buses": {"comfort": {"interface": "can0"}},
                        },
                    }
                    with patch.object(
                        coordinator,
                        "coordinator_preview",
                        return_value=expected_preview,
                    ):
                        preview = coordinator.client_preview(request, socket_path)
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                        connection.connect(str(socket_path))
                        connection.sendall(
                            b'{"api_version":1,"api_version":1,"action":"status"}\n'
                        )
                        duplicate = json.loads(connection.makefile("rb").readline())
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            self.assertTrue(response["ok"])
            self.assertEqual(response["state"]["state"], "idle")
            self.assertEqual(preview, expected_preview)
            self.assertFalse(duplicate["ok"])
            self.assertEqual(duplicate["error"], "Invalid coordinator request schema")
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

    def test_qualification_gate_is_root_style_one_shot_consent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            gate = root / "qualification"
            gate.write_bytes(coordinator.QUALIFICATION_GATE_CONTENT)
            gate.chmod(0o600)
            coordinator.consume_qualification_gate(gate)
            self.assertFalse(gate.exists())

            victim = root / "victim"
            victim.write_bytes(coordinator.QUALIFICATION_GATE_CONTENT)
            victim.chmod(0o600)
            gate.symlink_to(victim)
            with self.assertRaises(coordinator.CoordinatorError):
                coordinator.consume_qualification_gate(gate)
            self.assertTrue(victim.exists())

    def test_vcan_validation_requires_an_up_virtual_can_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sys"
            class_net = root / "class" / "net"
            virtual = root / "devices" / "virtual" / "net" / "vcan0"
            class_net.mkdir(parents=True)
            virtual.mkdir(parents=True)
            (virtual / "type").write_text("280\n", encoding="ascii")
            (virtual / "flags").write_text("0x1\n", encoding="ascii")
            (class_net / "vcan0").symlink_to(
                os.path.relpath(virtual, class_net)
            )
            coordinator.validate_vcan_interface("vcan0", sys_class_net=class_net)

            (virtual / "flags").write_text("0x0\n", encoding="ascii")
            with self.assertRaisesRegex(coordinator.CoordinatorError, "up vcan"):
                coordinator.validate_vcan_interface("vcan0", sys_class_net=class_net)
            with self.assertRaisesRegex(coordinator.CoordinatorError, "vcan"):
                coordinator.validate_vcan_interface("can0", sys_class_net=class_net)

    def test_qualification_preview_reader_rejects_duplicate_json_fields(self) -> None:
        with self.assertRaisesRegex(coordinator.CoordinatorError, "JSON"):
            coordinator.read_qualification_preview(
                io.BytesIO(b'{"api_version":1,"api_version":1}')
            )

    def test_direct_command_environment_loader_requires_exact_trusted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            environment = root / "coordinator.env"
            values = {
                "OPEN_MMI_INSTALL_DIR": str(root / "opt"),
                "OPEN_MMI_CONFIG_DIR": str(root / "home" / "config"),
                "OPEN_MMI_RUNTIME_DROPIN": str(root / "home" / "dropin.conf"),
                "OPEN_MMI_STATUS_PATH": str(root / "run" / "status.json"),
            }
            environment.write_text(
                "".join(
                    f"{key}={json.dumps(value)}\n"
                    for key, value in values.items()
                ),
                encoding="utf-8",
            )
            environment.chmod(0o644)
            with patch.dict(os.environ, {}, clear=False):
                self.assertEqual(
                    coordinator.load_coordinator_environment(environment), values
                )
                for key, value in values.items():
                    self.assertEqual(os.environ[key], value)

            environment.write_text(
                environment.read_text(encoding="utf-8") + "UNEXPECTED=\"/tmp\"\n",
                encoding="utf-8",
            )
            environment.chmod(0o644)
            with self.assertRaisesRegex(coordinator.CoordinatorError, "schema"):
                coordinator.load_coordinator_environment(environment)

    def test_idle_server_start_does_not_require_apply_paths(self) -> None:
        class Server:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def serve_forever(self):
                return None

        with patch.object(coordinator.os, "geteuid", return_value=0), patch.object(
            coordinator, "load_coordinator_environment"
        ), patch.object(
            coordinator, "read_state", return_value=coordinator.initial_state()
        ), patch.object(
            coordinator, "root_apply_operations", side_effect=AssertionError("unused")
        ), patch.object(
            coordinator, "CoordinatorServer", Server
        ):
            self.assertEqual(coordinator.main(["serve"]), 0)


class ApplyTransactionTests(unittest.TestCase):
    class Operations:
        def __init__(self, target, *, fail_at="", failure_message=""):
            self.target = target
            self.fail_at = fail_at
            self.failure_message = failure_message
            self.calls = []
            self.restored = False

        def _call(self, name):
            self.calls.append(name)
            if self.fail_at == name:
                raise RuntimeError(self.failure_message or f"failed at {name}")

        def snapshot(self, transaction_id):
            if not transaction_id.startswith("configuration-"):
                raise AssertionError("invalid transaction identifier")
            self._call("snapshot")
            return {"previous": True}

        def load_snapshot(self, transaction_id):
            if not transaction_id.startswith("configuration-"):
                raise AssertionError("invalid transaction identifier")
            self._call("load_snapshot")
            return {"previous": True}

        def discard_snapshot(self, snapshot):
            self._call("discard_snapshot")

        def install(self, target):
            self.assert_safe_target(target)
            self._call("install")

        def reload(self, target):
            self.assert_safe_target(target)
            self._call("reload")

        def assert_safe_target(self, target):
            if set(target) != {"vehicle", "bindings", "runtime"}:
                raise AssertionError("operations received an unsafe preview object")

        def restart(self):
            self._call("restart")

        def restore(self, snapshot):
            self._call("restore")
            self.restored = True

        def restoration_verified(self, snapshot, loaded):
            self._call("restoration_verified")
            return snapshot == {"previous": True} and loaded.get("state") == "ready"

        def loaded_runtime(self):
            self._call("loaded_runtime")
            if self.restored:
                return {"state": "ready"}
            bus = self.target["runtime"]["active_bus"]
            return {
                "state": "ready",
                "errors": [],
                "vehicle": self.target["vehicle"],
                "bindings": self.target["bindings"],
                "active_bus": bus,
                "interface": self.target["runtime"]["buses"][bus]["interface"],
            }

    def target(self):
        return {
            "vehicle": {
                "source": "maintained",
                "id": "seat_1p",
                "revision": "sha256:" + "a" * 64,
            },
            "bindings": {
                "source": "maintained",
                "id": "default",
                "revision": "sha256:" + "b" * 64,
            },
            "runtime": {
                "mode": "single",
                "active_bus": "comfort",
                "buses": {"comfort": {"interface": "can0"}},
            },
        }

    def preview(self, target=None):
        selected = target or self.target()
        return {
            "expected_configuration_revision": "sha256:" + "c" * 64,
            "target_configuration_revision": coordinator.vehicle_configuration.selection_revision(selected),
            "target": selected,
        }

    def execute(self, operations, root, **updates):
        args = dict(
            request={},
            reviewed_target=self.target(),
            expected_configuration_revision="sha256:" + "c" * 64,
            confirm=True,
            operations=operations,
            state_path=root / "state.json",
            configuration_lock=root / "configuration.lock",
            lifecycle_lock=root / "lifecycle.lock",
            update_lock=root / "update.lock",
        )
        args.update(updates)
        preview = args.pop("preview", self.preview())
        with patch.object(coordinator, "coordinator_preview", return_value=preview):
            return coordinator.run_apply_transaction(**args)

    def test_internal_apply_completes_and_verifies_loaded_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())
            state = self.execute(operations, root)
            self.assertEqual(state["state"], "complete")
            self.assertEqual(
                operations.calls,
                ["snapshot", "install", "reload", "restart", "loaded_runtime"],
            )
            self.assertFalse(state["restoration_attempted"])

    def test_vcan_qualification_restores_before_releasing_the_transaction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = self.target()
            target["runtime"]["buses"]["comfort"]["interface"] = "vcan0"
            operations = self.Operations(target)
            observed_at_discard = {}

            def discard_snapshot(snapshot):
                operations._call("discard_snapshot")
                observed_at_discard.update(
                    coordinator.read_state(root / "state.json")
                )

            operations.discard_snapshot = discard_snapshot
            preview = self.preview(target)
            with patch.object(coordinator, "coordinator_preview", return_value=preview):
                state = coordinator.run_apply_transaction(
                    {},
                    reviewed_target=target,
                    expected_configuration_revision="sha256:" + "c" * 64,
                    confirm=True,
                    operations=operations,
                    state_path=root / "state.json",
                    configuration_lock=root / "configuration.lock",
                    lifecycle_lock=root / "lifecycle.lock",
                    update_lock=root / "update.lock",
                    qualification_restore_on_success=True,
                )
            self.assertEqual(state["state"], "complete")
            self.assertEqual(state["stage"], "qualification-restored")
            self.assertTrue(state["restoration_attempted"])
            self.assertTrue(state["restoration_verified"])
            self.assertEqual(observed_at_discard["state"], "complete")
            self.assertEqual(
                observed_at_discard["stage"], "qualification-restored"
            )
            self.assertEqual(
                operations.calls,
                [
                    "snapshot",
                    "install",
                    "reload",
                    "restart",
                    "loaded_runtime",
                    "restore",
                    "restart",
                    "loaded_runtime",
                    "restoration_verified",
                    "discard_snapshot",
                ],
            )

    def test_one_shot_vcan_qualification_consumes_gate_and_round_trips(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            target = self.target()
            target["runtime"]["buses"]["comfort"]["interface"] = "vcan0"
            preview = {
                "api_version": 1,
                "read_only": True,
                "apply_available": False,
                "state": "ready",
                "expected_configuration_revision": "sha256:" + "c" * 64,
                "target_configuration_revision": coordinator.vehicle_configuration.selection_revision(target),
                "target": target,
                "coordinator": {
                    "previewed": True,
                    "read_only": True,
                    "locks": {
                        "configuration_active": False,
                        "lifecycle_active": False,
                        "update_active": False,
                    },
                    "apply_blocked": False,
                },
            }
            gate = root / "qualification"
            gate.write_bytes(coordinator.QUALIFICATION_GATE_CONTENT)
            gate.chmod(0o600)
            class_net = root / "sys" / "class" / "net"
            virtual = root / "sys" / "devices" / "virtual" / "net" / "vcan0"
            class_net.mkdir(parents=True)
            virtual.mkdir(parents=True)
            (virtual / "type").write_text("280\n", encoding="ascii")
            (virtual / "flags").write_text("0x1\n", encoding="ascii")
            (class_net / "vcan0").symlink_to(os.path.relpath(virtual, class_net))
            dropin = root / "home" / "10-can-runtime.conf"
            dropin.parent.mkdir(mode=0o700)
            operations = self.Operations(target)
            with patch.object(coordinator, "coordinator_preview", return_value=preview):
                state = coordinator.run_vcan_qualification(
                    preview,
                    operations=operations,
                    gate_path=gate,
                    state_path=root / "state.json",
                    dropin_path=dropin,
                    sys_class_net=class_net,
                    configuration_lock=root / "configuration.lock",
                    lifecycle_lock=root / "lifecycle.lock",
                    update_lock=root / "update.lock",
                )
            self.assertFalse(gate.exists())
            self.assertEqual(state["stage"], "qualification-restored")

    def test_vcan_qualification_rejects_a_conflicting_later_dropin_before_consent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            target = self.target()
            target["runtime"]["buses"]["comfort"]["interface"] = "vcan0"
            preview = {
                "api_version": 1,
                "read_only": True,
                "apply_available": False,
                "state": "ready",
                "expected_configuration_revision": "sha256:" + "c" * 64,
                "target_configuration_revision": coordinator.vehicle_configuration.selection_revision(target),
                "target": target,
                "coordinator": {
                    "previewed": True,
                    "read_only": True,
                    "locks": {
                        "configuration_active": False,
                        "lifecycle_active": False,
                        "update_active": False,
                    },
                    "apply_blocked": False,
                },
            }
            gate = root / "qualification"
            gate.write_bytes(coordinator.QUALIFICATION_GATE_CONTENT)
            gate.chmod(0o600)
            class_net = root / "sys" / "class" / "net"
            virtual = root / "sys" / "devices" / "virtual" / "net" / "vcan0"
            class_net.mkdir(parents=True)
            virtual.mkdir(parents=True)
            (virtual / "type").write_text("280\n", encoding="ascii")
            (virtual / "flags").write_text("0x1\n", encoding="ascii")
            (class_net / "vcan0").symlink_to(os.path.relpath(virtual, class_net))
            dropin = root / "home" / "10-can-runtime.conf"
            dropin.parent.mkdir(mode=0o700)
            conflict = dropin.parent / "99-local.conf"
            conflict.write_text(
                '[Service]\nEnvironment="OPEN_MMI_CAN_INTERFACE=can0"\n',
                encoding="utf-8",
            )
            conflict.chmod(0o644)
            with self.assertRaisesRegex(coordinator.CoordinatorError, "99-local"):
                coordinator.run_vcan_qualification(
                    preview,
                    operations=self.Operations(target),
                    gate_path=gate,
                    state_path=root / "state.json",
                    dropin_path=dropin,
                    sys_class_net=class_net,
                    configuration_lock=root / "configuration.lock",
                    lifecycle_lock=root / "lifecycle.lock",
                    update_lock=root / "update.lock",
                )
            self.assertTrue(gate.exists())

    def test_stale_or_unconfirmed_apply_mutates_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())
            with self.assertRaisesRegex(coordinator.CoordinatorError, "confirmation"):
                self.execute(operations, root, confirm=False)
            with self.assertRaisesRegex(coordinator.CoordinatorError, "stale"):
                self.execute(
                    operations,
                    root,
                    expected_configuration_revision="sha256:" + "d" * 64,
                )
            self.assertEqual(operations.calls, [])

    def test_changed_reviewed_target_is_rejected_before_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())
            changed = self.target()
            changed["vehicle"]["revision"] = "sha256:" + "d" * 64
            with self.assertRaisesRegex(coordinator.CoordinatorError, "changed after review"):
                self.execute(operations, root, preview=self.preview(changed))
            self.assertEqual(operations.calls, [])

    def test_inconsistent_preview_target_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())
            preview = self.preview()
            preview["target_configuration_revision"] = "sha256:" + "f" * 64
            with self.assertRaisesRegex(coordinator.CoordinatorError, "inconsistent"):
                self.execute(operations, root, preview=preview)
            self.assertEqual(operations.calls, [])

    def test_failure_after_mutation_restores_and_marks_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target(), fail_at="reload")
            with self.assertRaisesRegex(coordinator.CoordinatorError, "during reloading"):
                self.execute(operations, root)
            state = coordinator.read_state(root / "state.json")
            self.assertEqual(state["state"], "failed")
            self.assertEqual(state["stage"], "restored")
            self.assertTrue(state["restoration_attempted"])
            self.assertTrue(state["restoration_verified"])
            self.assertIn("restore", operations.calls)
            self.assertIn("restoration_verified", operations.calls)

    def test_keyboard_interrupt_after_mutation_still_restores(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())

            def interrupted_reload(target):
                operations.assert_safe_target(target)
                operations.calls.append("reload")
                raise KeyboardInterrupt()

            operations.reload = interrupted_reload
            with self.assertRaisesRegex(
                coordinator.CoordinatorError, "during reloading"
            ):
                self.execute(operations, root)
            state = coordinator.read_state(root / "state.json")
            self.assertEqual(state["stage"], "restored")
            self.assertTrue(state["restoration_verified"])

    def test_multiline_operation_error_is_not_exposed_and_cannot_block_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            secret = "failed\nprivate=/root/secret"
            operations = self.Operations(
                self.target(), fail_at="reload", failure_message=secret
            )
            with self.assertRaisesRegex(coordinator.CoordinatorError, "during reloading") as raised:
                self.execute(operations, root)
            self.assertNotIn("secret", str(raised.exception))
            state = coordinator.read_state(root / "state.json")
            self.assertEqual(state["stage"], "restored")
            self.assertNotIn("secret", state["error"])
            self.assertIn("restore", operations.calls)

    def test_state_write_failure_entering_restore_does_not_block_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target(), fail_at="reload")
            real_write = coordinator.write_state

            def fail_restoring(payload, path):
                if payload.get("state") == "restoring":
                    raise coordinator.CoordinatorError("state storage unavailable")
                return real_write(payload, path)

            with patch.object(coordinator, "write_state", side_effect=fail_restoring):
                with self.assertRaises(coordinator.CoordinatorError):
                    self.execute(operations, root)
            self.assertIn("restore", operations.calls)
            self.assertIn("restoration_verified", operations.calls)

    def test_snapshot_failure_does_not_attempt_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target(), fail_at="snapshot")
            with self.assertRaisesRegex(coordinator.CoordinatorError, "during snapshot"):
                self.execute(operations, root)
            state = coordinator.read_state(root / "state.json")
            self.assertFalse(state["restoration_attempted"])
            self.assertNotIn("restore", operations.calls)


    def test_interrupted_mutation_uses_durable_snapshot_and_verifies_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())
            state = coordinator.initial_state()
            state.update(
                {
                    "state": "reloading",
                    "stage": "reloading",
                    "transaction_id": "configuration-" + "e" * 32,
                    "started_at": state["updated_at"],
                    "target": {
                        "vehicle": self.target()["vehicle"],
                        "bindings": self.target()["bindings"],
                        "active_bus": "comfort",
                        "interface": "can0",
                    },
                    "expected_configuration_revision": "sha256:" + "c" * 64,
                }
            )
            coordinator.write_state(state, root / "state.json")
            recovered = coordinator.recover_interrupted_transaction(
                operations,
                state_path=root / "state.json",
                configuration_lock=root / "configuration.lock",
                lifecycle_lock=root / "lifecycle.lock",
                update_lock=root / "update.lock",
            )
            self.assertEqual(recovered["state"], "failed")
            self.assertEqual(recovered["stage"], "restored")
            self.assertTrue(recovered["recovered"])
            self.assertTrue(recovered["restoration_verified"])
            self.assertEqual(
                operations.calls,
                [
                    "load_snapshot",
                    "restore",
                    "restart",
                    "loaded_runtime",
                    "restoration_verified",
                ],
            )

    def test_interrupted_validation_does_not_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            operations = self.Operations(self.target())
            state = coordinator.initial_state()
            state.update(
                {
                    "state": "validating",
                    "stage": "validated",
                    "transaction_id": "configuration-" + "f" * 32,
                    "started_at": state["updated_at"],
                    "target": {
                        "vehicle": self.target()["vehicle"],
                        "bindings": self.target()["bindings"],
                        "active_bus": "comfort",
                        "interface": "can0",
                    },
                    "expected_configuration_revision": "sha256:" + "c" * 64,
                }
            )
            coordinator.write_state(state, root / "state.json")
            recovered = coordinator.recover_interrupted_transaction(
                operations,
                state_path=root / "state.json",
                configuration_lock=root / "configuration.lock",
                lifecycle_lock=root / "lifecycle.lock",
                update_lock=root / "update.lock",
            )
            self.assertEqual(recovered["stage"], "recovery")
            self.assertTrue(recovered["recovered"])
            self.assertEqual(operations.calls, [])

    def test_public_protocol_still_rejects_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            coordinator.write_state(coordinator.initial_state(), root / "state.json")
            response = coordinator.response_for_request(
                {"api_version": 1, "action": "apply", "confirm": True},
                root / "state.json",
                root / "configuration.lock",
                root / "lifecycle.lock",
                root / "update.lock",
            )
            self.assertFalse(response["ok"])
            self.assertIn("not enabled", response["error"])


if __name__ == "__main__":
    unittest.main()
