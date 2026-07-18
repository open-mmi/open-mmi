from __future__ import annotations

import socket
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ui import update_readiness


class UpdateReadinessTests(unittest.TestCase):
    def status(self, *blockers: str):
        return {"readiness": {"state": "blocked" if blockers else "ready", "blockers": list(blockers)}}

    def diagnostics(self, *, ac=True, capacity=80, thermal="normal"):
        return {
            "power": {"ac_online": ac, "capacity_percent": capacity},
            "thermal": {"summary": thermal},
        }

    def test_missing_coordinator_keeps_installation_blocked(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            update_readiness, "_service_check", return_value=update_readiness._check("service-health", "pass", "ok")
        ), patch.object(update_readiness.shutil, "which", return_value="/usr/bin/tool"), patch.object(
            update_readiness.shutil, "disk_usage", return_value=SimpleNamespace(free=2 * update_readiness.MIN_FREE_BYTES)
        ):
            root = Path(temporary)
            payload = update_readiness.readiness_payload(
                self.status(), install_dir=root, config_dir=root / "config",
                coordinator_socket=root / "missing.sock", update_lock=root / "missing.lock",
                diagnostics=self.diagnostics(),
            )
        self.assertEqual(payload["state"], "blocked")
        self.assertFalse(payload["install_allowed"])
        self.assertIn("privileged-coordinator", payload["blockers"])

    def test_low_battery_thermal_constraint_and_existing_lock_are_blockers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock = root / "update.lock"
            lock.write_text("active", encoding="utf-8")
            lock.chmod(0o600)
            transaction = update_readiness._transaction_check(lock)
            self.assertEqual(transaction["state"], "block")
        self.assertEqual(update_readiness._power_check({"ac_online": False, "capacity_percent": 12})["state"], "block")
        self.assertEqual(update_readiness._thermal_check({"summary": "thermal-limit-active"})["state"], "block")

    def test_unexposed_power_and_thermal_are_unknown_not_assumed_safe(self):
        self.assertEqual(update_readiness._power_check({"ac_online": None})["state"], "unknown")
        self.assertEqual(update_readiness._thermal_check({"summary": "unavailable"})["state"], "unknown")

    def test_fixed_command_and_service_lists_do_not_accept_caller_input(self):
        self.assertEqual(update_readiness.REQUIRED_COMMANDS, ("git", "systemctl"))
        self.assertEqual(update_readiness.REQUIRED_SERVICES, ("canbusd.service", "open-mmi-dashboard.service"))
        with patch.object(update_readiness.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="0\nactive\nrunning\n2\n")) as run:
            result = update_readiness._service_check()
        self.assertEqual(result["state"], "pass")
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["systemctl", "--user", "show"])
        self.assertEqual(command[3:5], list(update_readiness.REQUIRED_SERVICES))

    def test_restart_loop_and_insufficient_disk_block(self):
        with patch.object(update_readiness.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="9\n")):
            self.assertEqual(update_readiness._service_check()["state"], "block")
        with patch.object(update_readiness.shutil, "disk_usage", return_value=SimpleNamespace(free=1)):
            self.assertEqual(update_readiness._disk_check(Path("/tmp"))["state"], "block")

    def test_coordinator_requires_root_owned_non_world_writable_socket(self):
        trusted = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660, st_uid=0)
        untrusted = SimpleNamespace(st_mode=stat.S_IFSOCK | 0o666, st_uid=0)
        path = Path("/run/open-mmi/test.sock")
        with patch.object(Path, "lstat", return_value=trusted):
            self.assertEqual(update_readiness._coordinator_check(path)["state"], "pass")
        with patch.object(Path, "lstat", return_value=untrusted):
            self.assertEqual(update_readiness._coordinator_check(path)["state"], "block")


if __name__ == "__main__":
    unittest.main()
