import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "profile_provision.py"
SPEC = importlib.util.spec_from_file_location("profile_provision", MODULE_PATH)
profile_provision = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = profile_provision
assert SPEC.loader is not None
SPEC.loader.exec_module(profile_provision)


class ProfileProvisionTests(unittest.TestCase):
    def test_build_plan_uses_profile_default_bus(self):
        profile = {
            "default_bus": "comfort",
            "can_buses": {
                "comfort": {
                    "interface": "can9",
                    "bitrate": 125000,
                    "provisioning": "udev",
                    "capture_point": "test point",
                }
            },
        }

        plan = profile_provision.build_plan(
            profile,
            Path("/tmp/profile.json"),
            Path("/tmp/default.json"),
            "seat_1p",
            "default",
        )

        self.assertEqual(plan.default_bus, "comfort")
        self.assertEqual(plan.active_interface, "can9")
        self.assertEqual(plan.buses[0].bitrate, 125000)
        self.assertEqual(plan.buses[0].provisioning, "udev")

    def test_build_plan_falls_back_for_legacy_profile(self):
        plan = profile_provision.build_plan(
            {"rules": [], "presence": [], "status": []},
            Path("/tmp/profile.json"),
            Path("/tmp/default.json"),
            "legacy",
            "default",
        )

        self.assertEqual(plan.default_bus, "comfort")
        self.assertEqual(plan.active_interface, "can0")
        self.assertEqual(plan.buses[0].name, "comfort")
        self.assertEqual(plan.buses[0].provisioning, "manual")

    def test_render_systemd_dropin(self):
        plan = profile_provision.build_plan(
            {
                "default_bus": "comfort",
                "can_buses": {
                    "comfort": {
                        "interface": "vcan0",
                        "provisioning": "manual",
                    }
                },
            },
            Path("/tmp/profile.json"),
            Path("/tmp/default.json"),
            "seat_1p",
            "default",
        )

        rendered = profile_provision.render_systemd_dropin(plan)

        self.assertIn('Environment="OPEN_MMI_VEHICLE=seat_1p"', rendered)
        self.assertIn('Environment="OPEN_MMI_CAN_BUS=comfort"', rendered)
        self.assertIn('Environment="OPEN_MMI_CAN_INTERFACE=vcan0"', rendered)

    def test_render_udev_rules_for_udev_bus(self):
        plan = profile_provision.build_plan(
            {
                "default_bus": "comfort",
                "can_buses": {
                    "comfort": {
                        "interface": "can0",
                        "bitrate": 100000,
                        "provisioning": "udev",
                    }
                },
            },
            Path("/tmp/profile.json"),
            Path("/tmp/default.json"),
            "seat_1p",
            "default",
        )

        rendered = profile_provision.render_udev_rules(plan)

        self.assertIn('KERNEL=="can0"', rendered)
        self.assertIn("bitrate 100000", rendered)
        self.assertIn('KERNEL=="uinput"', rendered)

    def test_render_udev_rules_skips_manual_bus(self):
        plan = profile_provision.build_plan(
            {
                "default_bus": "replay",
                "can_buses": {
                    "replay": {
                        "interface": "vcan0",
                        "provisioning": "manual",
                    }
                },
            },
            Path("/tmp/profile.json"),
            Path("/tmp/default.json"),
            "seat_1p",
            "default",
        )

        rendered = profile_provision.render_udev_rules(plan)
        self.assertNotIn("ip link set vcan0 type can", rendered)

    def test_apply_plan_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            profile_path = tmp_path / "config" / "vehicles" / "seat_1p" / "config.json"
            bindings_path = tmp_path / "config" / "bindings" / "default.json"
            profile_path.parent.mkdir(parents=True)
            bindings_path.parent.mkdir(parents=True)
            profile_path.write_text("{}", encoding="utf-8")
            bindings_path.write_text("{}", encoding="utf-8")

            plan = profile_provision.build_plan(
                {
                    "default_bus": "comfort",
                    "can_buses": {
                        "comfort": {
                            "interface": "can0",
                            "bitrate": 100000,
                            "provisioning": "udev",
                        }
                    },
                },
                profile_path,
                bindings_path,
                "seat_1p",
                "default",
            )

            systemd_dir = tmp_path / "systemd" / "user"
            udev_path = tmp_path / "rules.d" / "80-canbus.rules"

            profile_provision.apply_plan(
                plan,
                systemd_dir,
                real_user="",
                udev_rule_path=udev_path,
            )

            self.assertTrue((systemd_dir / "canbusd.service.d" / "10-can-runtime.conf").exists())
            self.assertTrue(udev_path.exists())


    def test_dry_run_does_not_create_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            repo_root = tmp_path / "repo"
            install_dir = tmp_path / "install"
            user_config_dir = tmp_path / "home" / ".config" / "open-mmi"
            systemd_user_dir = tmp_path / "home" / ".config" / "systemd" / "user"

            profile_dir = repo_root / "vehicles" / "seat_1p"
            bindings_dir = repo_root / "bindings"
            profile_dir.mkdir(parents=True)
            bindings_dir.mkdir(parents=True)

            (profile_dir / "config.json").write_text(
                '{"default_bus":"comfort","can_buses":{"comfort":{"interface":"can0","bitrate":100000,"provisioning":"udev"}}}',
                encoding="utf-8",
            )
            (bindings_dir / "default.json").write_text("{}", encoding="utf-8")

            argv = [
                "profile_provision.py",
                "--repo-root",
                str(repo_root),
                "--install-dir",
                str(install_dir),
                "--user-config-dir",
                str(user_config_dir),
                "--systemd-user-dir",
                str(systemd_user_dir),
                "--vehicle",
                "seat_1p",
                "--bindings",
                "default",
                "--dry-run",
            ]

            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(profile_provision.main(), 0)

            self.assertFalse((user_config_dir / "vehicles" / "seat_1p" / "config.json").exists())
            self.assertFalse((user_config_dir / "bindings" / "default.json").exists())
            self.assertFalse((systemd_user_dir / "canbusd.service.d" / "10-can-runtime.conf").exists())



if __name__ == "__main__":
    unittest.main()
