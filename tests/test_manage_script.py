from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGE_SCRIPT = ROOT / "scripts" / "manage.sh"


class ManageScriptLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = MANAGE_SCRIPT.read_text(encoding="utf-8")

    def test_manage_script_has_valid_bash_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(MANAGE_SCRIPT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_service_units_use_single_command_source_and_destination(self) -> None:
        install_canbusd = (
            'install -m 0644 -o "$REAL_USER" -g "$REAL_USER" '
            '"$REPO_ROOT/systemd/user/canbusd.service" '
            '"$user_systemd_dir/canbusd.service"'
        )
        install_dashboard = (
            'install -m 0644 -o "$REAL_USER" -g "$REAL_USER" '
            '"$REPO_ROOT/systemd/user/open-mmi-dashboard.service" '
            '"$user_systemd_dir/open-mmi-dashboard.service"'
        )
        self.assertGreaterEqual(self.text.count(install_canbusd), 2)
        self.assertGreaterEqual(self.text.count(install_dashboard), 2)
        self.assertNotIn(
            'cp "$REPO_ROOT/systemd/user/canbusd.service" \\\n',
            self.text,
        )
        self.assertNotIn(
            'cp "$REPO_ROOT/systemd/user/open-mmi-dashboard.service" \\\n',
            self.text,
        )

    def test_uninstall_handles_absent_units_quietly(self) -> None:
        self.assertIn(
            "for service in canbusd.service open-mmi-dashboard.service; do",
            self.text,
        )
        self.assertIn(
            'systemctl --user disable --now "$service" >/dev/null 2>&1 || true',
            self.text,
        )

    def test_group_cleanup_guidance_is_safe(self) -> None:
        self.assertNotIn("sudo usermod -G $(groups", self.text)
        self.assertIn("sudo gpasswd -d $REAL_USER video", self.text)
        self.assertIn("sudo gpasswd -d $REAL_USER input", self.text)


if __name__ == "__main__":
    unittest.main()
