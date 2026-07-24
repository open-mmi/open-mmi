from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PowerdIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manage = (ROOT / "scripts/manage.sh").read_text(encoding="utf-8")
        cls.pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        cls.unit = (
            ROOT / "systemd/system/open-mmi-powerd.service"
        ).read_text(encoding="utf-8")

    def test_daemon_is_not_an_action_module(self) -> None:
        self.assertFalse((ROOT / "actions/power.py").exists())
        self.assertTrue((ROOT / "powerd/daemon.py").is_file())
        self.assertIn('open-mmi-powerd = "powerd.cli:main"', self.pyproject)
        self.assertIn('    "powerd*",', self.pyproject)

    def test_all_deployment_paths_copy_and_install_powerd(self) -> None:
        self.assertIn('cp -r "$REPO_ROOT/powerd" "$INSTALL_DIR/"', self.manage)
        self.assertIn('sudo cp -r "$REPO_ROOT/powerd" "$INSTALL_DIR/"', self.manage)
        self.assertIn(
            "for item in canbusd vehicles bindings actions powerd ui scripts packaging systemd; do",
            self.manage,
        )
        self.assertGreaterEqual(self.manage.count("install_power_manager"), 4)

    def test_service_is_disabled_by_default_and_policy_controls_enablement(self) -> None:
        start = self.manage.index("install_power_manager() {")
        end = self.manage.index("cmd_power() {", start)
        install_block = self.manage[start:end]
        self.assertIn('"enabled": false', install_block)
        self.assertIn("reconcile_power_manager", install_block)
        self.assertNotIn('systemctl enable "$POWERD_UNIT"', install_block)
        self.assertIn('systemctl enable --now "$POWERD_UNIT"', self.manage)
        self.assertIn('systemctl disable --now "$POWERD_UNIT"', self.manage)

    def test_prepared_update_backs_up_power_unit_and_policy(self) -> None:
        self.assertIn('"$POWERD_UNIT"; do', self.manage)
        self.assertIn("system-files/power-policy.json", self.manage)
        self.assertIn("reconcile_power_manager", self.manage)
        malformed = (
            'cp -a -- "$rollback_root/system-files/'
            'vehicle-config-coordinator-sandbox.conf" \\\n'
            '                "$VEHICLE_CONFIG_COORDINATOR_SANDBOX" \\\n'
            '        "$POWER_POLICY_FILE"'
        )
        self.assertNotIn(malformed, self.manage)

    def test_system_service_runs_standalone_hardened_daemon(self) -> None:
        self.assertIn(
            "ExecStart=/opt/open-mmi/venv/bin/open-mmi-powerd run",
            self.unit,
        )
        self.assertIn("RestrictAddressFamilies=AF_CAN AF_NETLINK AF_UNIX", self.unit)
        self.assertIn("ProtectSystem=strict", self.unit)
        self.assertNotIn("actions.power", self.unit)

    def test_wheel_verifier_requires_powerd_modules(self) -> None:
        verifier = (ROOT / "tools/verify_wheel.py").read_text(encoding="utf-8")
        self.assertIn('"powerd/daemon.py"', verifier)
        self.assertIn('"powerd/policy.py"', verifier)

    def test_manage_script_has_valid_bash_syntax(self) -> None:
        completed = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts/manage.sh")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
