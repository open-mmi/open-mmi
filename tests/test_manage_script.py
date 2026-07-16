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

    def test_update_systemctl_commands_are_complete_single_lines(self) -> None:
        start = self.text.index("cmd_update() {")
        end = self.text.index(
            "# =============================================================================\n"
            "# UNINSTALL",
            start,
        )
        update_block = self.text[start:end]
        commands = [
            line.strip()
            for line in update_block.splitlines()
            if line.strip().startswith('sudo -u "$REAL_USER"')
            and "systemctl --user" in line
        ]

        self.assertEqual(len(commands), 2)
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(command.endswith("\\"))

                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        f'''\
REAL_USER=pitto
REAL_HOME=/home/pitto
XDG_RUNTIME_DIR=/run/user/1000
sudo() {{ printf '%s\\0' "$@"; }}
{command}
''',
                    ],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stderr.decode("utf-8", errors="replace"),
                )
                arguments = [
                    value.decode("utf-8")
                    for value in result.stdout.split(b"\0")
                    if value
                ]
                self.assertIn("systemctl", arguments)
                systemctl_index = arguments.index("systemctl")
                self.assertEqual(arguments[systemctl_index + 1], "--user")

    def test_update_manages_both_service_units(self) -> None:
        self.assertIn(
            "systemctl --user restart "
            "canbusd.service open-mmi-dashboard.service",
            self.text,
        )
        self.assertIn(
            "systemctl --user enable canbusd.service",
            self.text,
        )
        self.assertIn(
            "systemctl --user enable open-mmi-dashboard.service",
            self.text,
        )
        self.assertIn(
            "systemctl --user disable open-mmi-dashboard.service",
            self.text,
        )

    def test_dashboard_autostart_reads_launcher_preference(self) -> None:
        self.assertIn("dashboard_start_at_login()", self.text)
        self.assertIn('payload.get("start_at_login", True) is not False', self.text)
        self.assertGreaterEqual(self.text.count("configure_dashboard_autostart"), 3)

    def test_desktop_entry_is_managed_by_install_update_and_uninstall(self) -> None:
        install_start = self.text.index("cmd_install() {")
        update_start = self.text.index("cmd_update() {")
        uninstall_start = self.text.index("cmd_uninstall() {")
        status_start = self.text.index("cmd_status() {")

        install_block = self.text[install_start:update_start]
        update_block = self.text[update_start:uninstall_start]
        uninstall_block = self.text[uninstall_start:status_start]

        self.assertIn("install_desktop_entry", install_block)
        self.assertIn("install_desktop_entry", update_block)
        self.assertIn("remove_desktop_entry", uninstall_block)
        self.assertIn("install_desktop_icons", self.text)
        self.assertIn("remove_desktop_icons", self.text)
        self.assertIn('cp -r "$REPO_ROOT/packaging" "$INSTALL_DIR/"', install_block)
        self.assertIn('sudo cp -r "$REPO_ROOT/packaging" "$INSTALL_DIR/"', update_block)

    def test_manage_script_can_be_sourced_without_running_main(self) -> None:
        self.assertIn(
            'if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then\n'
            '    main "$@"\n'
            "fi",
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
