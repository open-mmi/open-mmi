from __future__ import annotations

import json
import subprocess
import tempfile
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

    def test_update_source_metadata_python_has_valid_syntax(self) -> None:
        marker = "<<'PY_UPDATE_SOURCE'\n"
        start = self.text.index(marker) + len(marker)
        end = self.text.index("\nPY_UPDATE_SOURCE", start)
        compile(self.text[start:end], "manage.sh:PY_UPDATE_SOURCE", "exec")

    def test_update_source_writer_migrates_and_preserves_named_channel_policy(self) -> None:
        marker = "<<'PY_UPDATE_SOURCE'\n"
        start = self.text.index(marker) + len(marker)
        end = self.text.index("\nPY_UPDATE_SOURCE", start)
        program = self.text[start:end]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata = root / "install" / ".update-source.json"
            policy = root / "etc" / "update-policy.json"
            source = root / "source"
            source.mkdir()
            arguments = [
                "python3", "-c", program,
                str(metadata), str(source), "main", "origin/main",
                "a" * 40, "v0.1.0", str(policy),
            ]
            first = subprocess.run(arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(policy.read_text(encoding="utf-8"))["channel"], "nightly")
            self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["channel"], "nightly")

            policy.write_text(json.dumps({
                "schema_version": 1,
                "channel": "development",
                "updated_at": "2026-07-18T12:00:00+00:00",
            }), encoding="utf-8")
            policy.chmod(0o644)
            migrated = subprocess.run(arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertEqual(json.loads(policy.read_text(encoding="utf-8"))["channel"], "nightly")
            self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["channel"], "nightly")

            policy.write_text(json.dumps({
                "schema_version": 1,
                "channel": "beta",
                "updated_at": "2026-07-18T12:00:00+00:00",
            }), encoding="utf-8")
            policy.chmod(0o644)
            second = subprocess.run(arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["channel"], "beta")

            policy.write_text(json.dumps({
                "schema_version": 1,
                "channel": "beta",
                "repository": "https://evil.test/repo",
            }), encoding="utf-8")
            policy.chmod(0o644)
            invalid = subprocess.run(arguments, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(invalid.returncode, 0)

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
        end = self.text.index("cmd_deploy_prepared() {", start)
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
        self.assertNotIn(
            "systemctl --user enable open-mmi-dashboard.service",
            self.text,
        )
        self.assertIn(
            "systemctl --user disable open-mmi-dashboard.service",
            self.text,
        )

    def test_dashboard_service_is_not_the_user_facing_autostart_setting(self) -> None:
        self.assertIn("configure_install_service_defaults()", self.text)
        self.assertIn("configure_update_service_defaults()", self.text)
        self.assertIn("migrate_legacy_dashboard_startup()", self.text)
        self.assertIn('payload.pop("start_at_login", None)', self.text)
        self.assertIn("remove_login_autostart", self.text)
        self.assertNotIn("configure_dashboard_autostart", self.text)

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

    def test_package_and_command_links_are_managed_by_lifecycle(self) -> None:
        install_start = self.text.index("cmd_install() {")
        update_start = self.text.index("cmd_update() {")
        uninstall_start = self.text.index("cmd_uninstall() {")
        status_start = self.text.index("cmd_status() {")

        install_block = self.text[install_start:update_start]
        update_block = self.text[update_start:uninstall_start]
        uninstall_block = self.text[uninstall_start:status_start]

        self.assertIn("install_open_mmi_package", install_block)
        self.assertIn("install_command_links", install_block)
        self.assertIn("install_open_mmi_package", update_block)
        self.assertIn("install_command_links", update_block)
        self.assertIn("remove_command_links", uninstall_block)
        self.assertIn('local pip_arguments=(install --upgrade --force-reinstall)', self.text)
        self.assertIn('local package_source="${1:-$INSTALL_DIR}"', self.text)
        self.assertIn('( umask 0022; env -u PYTHONPATH "$python" -m pip', self.text)
        self.assertIn('sudo -u "$REAL_USER" env -u PYTHONPATH "$python" -I', self.text)
        self.assertIn('cp "$REPO_ROOT/README.md" "$INSTALL_DIR/"', install_block)
        self.assertIn('cp "$REPO_ROOT/LICENSE" "$INSTALL_DIR/"', install_block)
        self.assertIn('sudo cp "$REPO_ROOT/README.md" "$INSTALL_DIR/"', update_block)
        self.assertIn('sudo cp "$REPO_ROOT/LICENSE" "$INSTALL_DIR/"', update_block)

    def test_expected_console_commands_are_declared(self) -> None:
        for command in (
            "open-mmi-canbusd",
            "open-mmi-config",
            "open-mmi-dashboard",
            "open-mmi-launcher",
            "open-mmi-status",
            "open-mmi-update-coordinator",
            "open-mmi-update-installer",
        ):
            self.assertIn(command, self.text)
        self.assertIn(
            'COMMAND_LINK_DIR="${OPEN_MMI_COMMAND_LINK_DIR:-/usr/local/bin}"',
            self.text,
        )

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
        self.assertIn('systemctl stop "$UPDATE_INSTALLER_UNIT"', self.text)
        self.assertIn('"/etc/systemd/system/$UPDATE_INSTALLER_UNIT"', self.text)

    def test_prepared_deployment_is_fixed_root_only_and_rolls_back_on_error(self) -> None:
        start = self.text.index("cmd_deploy_prepared() {")
        end = self.text.index("# UNINSTALL", start)
        block = self.text[start:end]
        self.assertIn('^prepare-[0-9a-f]{32}$', block)
        self.assertIn('/var/lib/open-mmi/staging/$transaction', block)
        self.assertIn('trap rollback_prepared_deployment ERR', block)
        self.assertIn('Prepared deployment failed at stage: $deployment_stage', block)
        self.assertIn('env -u PYTHONPATH "$rollback_root/installation/venv/bin/python" -I -c \'import ui.config_cli\'', block)
        self.assertIn('env -u PYTHONPATH "$INSTALL_DIR/venv/bin/python" -I -c \'import ui.config_cli\'', block)
        self.assertIn('Prepared rollback verified', block)
        self.assertIn('pip wheel --no-deps', block)
        self.assertIn('tools/verify_wheel.py', block)
        self.assertIn('install_open_mmi_package "$candidate_wheel"', block)
        self.assertIn("import canbusd.core, ui.config_cli, ui.web_dashboard.server", self.text)
        self.assertIn('mv -- "$restored_install" "$INSTALL_DIR"', block)
        self.assertNotIn('pip install --upgrade --force-reinstall "$INSTALL_DIR"', block)
        self.assertIn('curl --fail --silent --max-time 2 http://127.0.0.1:8765/api/health', block)
        self.assertIn('payload.get("build_id") == expected', block)
        self.assertIn('for _attempt in {1..15}; do', block)
        self.assertIn('[[ "$api_ready" == true ]]', block)
        self.assertIn('[[ "$version_ready" == true ]]', block)
        self.assertNotIn("eval ", block)

    def test_installer_unit_is_one_shot_and_accepts_no_arguments(self) -> None:
        unit = (ROOT / "systemd/system/open-mmi-update-installer.service").read_text(encoding="utf-8")
        self.assertIn("Type=oneshot", unit)
        self.assertIn("Environment=OPEN_MMI_PREPARED_DEPLOYMENT=1", unit)
        self.assertIn("ExecStart=/opt/open-mmi/venv/bin/open-mmi-update-installer\n", unit)
        self.assertIn("/run/open-mmi", unit)
        self.assertIn("ProtectHome=false", unit)
        self.assertNotIn("ProtectHome=read-only", unit)
        self.assertIn("ReadWritePaths=/opt ", unit)
        self.assertNotIn("ReadWritePaths=/opt/open-mmi ", unit)
        self.assertNotIn("%i", unit)
        self.assertIn("ProtectSystem=strict", unit)

    def test_coordinator_can_read_the_managed_checkout_and_is_restarted(self) -> None:
        unit = (ROOT / "systemd/system/open-mmi-update-coordinator.service").read_text(encoding="utf-8")
        self.assertIn("ProtectHome=read-only", unit)
        self.assertNotIn("ProtectHome=true", unit)
        start = self.text.index("install_update_coordinator() {")
        end = self.text.index("remove_login_autostart() {", start)
        block = self.text[start:end]
        self.assertIn('systemctl restart "$UPDATE_COORDINATOR_UNIT"', block)
        self.assertIn('${OPEN_MMI_PREPARED_DEPLOYMENT:-0}', block)
        self.assertIn("Log out and back in", block)


    def test_install_and_update_record_managed_update_source_metadata(self) -> None:
        install_start = self.text.index("cmd_install() {")
        update_start = self.text.index("cmd_update() {")
        uninstall_start = self.text.index("cmd_uninstall() {")
        install_block = self.text[install_start:update_start]
        update_block = self.text[update_start:uninstall_start]
        metadata_start = self.text.index("write_update_source_metadata() {")
        metadata_end = self.text.index("copy_if_missing() {", metadata_start)
        metadata_block = self.text[metadata_start:metadata_end]

        self.assertIn('destination="$INSTALL_DIR/.update-source.json"', metadata_block)
        self.assertIn('UPDATE_POLICY_FILE="/etc/open-mmi/update-policy.json"', self.text)
        self.assertIn('"schema_version": 1', metadata_block)
        self.assertIn('"channel": "nightly"', metadata_block)
        self.assertIn('"channel": policy["channel"]', metadata_block)
        self.assertIn('approved_channels = {"stable", "beta", "nightly"}', metadata_block)
        self.assertIn('"repository_path": str(Path(sys.argv[2]).resolve())', metadata_block)
        self.assertIn('"installed_commit": sys.argv[5].lower()', metadata_block)
        self.assertIn('tempfile.NamedTemporaryFile(', metadata_block)
        self.assertIn('os.fsync(temporary.fileno())', metadata_block)
        self.assertIn('os.replace(temporary_name, path)', metadata_block)
        self.assertIn('atomic_json(metadata_path, payload, 0o644)', metadata_block)
        self.assertIn("write_update_source_metadata", install_block)
        self.assertIn("write_update_source_metadata", update_block)
        self.assertGreater(install_block.index('get_current_version > "$VERSION_FILE"'), 0)
        self.assertGreater(
            install_block.index("write_update_source_metadata"),
            install_block.index('get_current_version > "$VERSION_FILE"'),
        )
        self.assertGreater(
            update_block.index("write_update_source_metadata"),
            update_block.index("echo '$new_version' > '$VERSION_FILE'"),
        )

    def test_uninstall_removes_root_owned_update_policy(self) -> None:
        uninstall_start = self.text.index("cmd_uninstall() {")
        status_start = self.text.index("cmd_status() {")
        uninstall_block = self.text[uninstall_start:status_start]
        self.assertIn('sudo rm -f "$UPDATE_POLICY_FILE"', uninstall_block)
        self.assertIn('sudo rmdir "$(dirname "$UPDATE_POLICY_FILE")"', uninstall_block)

    def test_group_cleanup_guidance_is_safe(self) -> None:
        self.assertNotIn("sudo usermod -G $(groups", self.text)
        self.assertIn("sudo gpasswd -d $REAL_USER video", self.text)
        self.assertIn("sudo gpasswd -d $REAL_USER input", self.text)


if __name__ == "__main__":
    unittest.main()
