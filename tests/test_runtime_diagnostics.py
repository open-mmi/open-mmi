from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from ui.web_dashboard import runtime_diagnostics


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sys_root = self.root / "sys"
        self.proc_root = self.root / "proc"
        self.proc_root.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative: str, value: object, *, root: Optional[Path] = None) -> Path:
        base = root or self.sys_root
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{value}\n", encoding="utf-8")
        return path

    def add_cpu(self, index: int, current: int, minimum: int = 400000, maximum: int = 3500000):
        base = f"devices/system/cpu/cpu{index}/cpufreq"
        self.write(f"{base}/scaling_cur_freq", current)
        self.write(f"{base}/scaling_min_freq", minimum)
        self.write(f"{base}/scaling_max_freq", maximum)
        self.write(f"{base}/scaling_governor", "powersave")

    def add_zone(self, index: int, zone_type: str, temp: int, trips=()):
        base = f"class/thermal/thermal_zone{index}"
        self.write(f"{base}/type", zone_type)
        self.write(f"{base}/temp", temp)
        for trip_index, (trip_type, trip_temp) in enumerate(trips):
            self.write(f"{base}/trip_point_{trip_index}_type", trip_type)
            self.write(f"{base}/trip_point_{trip_index}_temp", trip_temp)

    def add_power(self, name: str, supply_type: str, **values):
        base = f"class/power_supply/{name}"
        self.write(f"{base}/type", supply_type)
        for key, value in values.items():
            self.write(f"{base}/{key}", value)

    def sample(self):
        return runtime_diagnostics.runtime_diagnostics_payload(
            sys_root=self.sys_root,
            proc_root=self.proc_root,
            sampled_at=datetime.datetime(2026, 7, 16, 22, 29, 54, tzinfo=datetime.timezone.utc),
        )

    def test_surface_style_thermal_limit_and_charge_suspension_are_visible(self):
        for index, current in enumerate((399000, 400000, 399000, 400000)):
            self.add_cpu(index, current)
        self.write("loadavg", "6.21 4.24 4.04 4/123 999", root=self.proc_root)
        self.add_zone(
            1,
            "GEN4",
            52500,
            (("critical", 56050), ("hot", 54050), ("passive", 48050), ("active", 48050)),
        )
        self.add_zone(4, "B0D4", 53000, (("critical", 125050), ("passive", 122050)))
        self.add_power("ADP1", "Mains", online=1)
        self.add_power("AAA_MOUSE", "Battery", status="Discharging", capacity=100)
        self.add_power(
            "BAT1",
            "Battery",
            status="Not charging",
            capacity=65,
            energy_now=21130000,
            power_now=53946000,
            voltage_now=8072000,
            temp=315,
        )

        payload = self.sample()

        self.assertEqual(payload["sampled_at"], "2026-07-16T22:29:54+00:00")
        self.assertEqual(payload["cpu"]["average_mhz"], 399.5)
        self.assertTrue(payload["cpu"]["near_minimum"])
        self.assertTrue(payload["cpu"]["load_high"])
        self.assertEqual(payload["thermal"]["summary"], "thermal-limit-active")
        self.assertEqual(payload["thermal"]["selected_zone"], "GEN4")
        self.assertEqual(payload["thermal"]["relevant_trip"]["temperature_c"], 48.05)
        self.assertEqual(payload["thermal"]["relevant_trip"]["types"], ["active", "passive"])
        self.assertTrue(payload["power"]["ac_online"])
        self.assertEqual(payload["power"]["charging_state"], "not-charging")
        self.assertEqual(payload["power"]["capacity_percent"], 65)
        self.assertEqual(payload["power"]["energy_wh"], 21.13)
        battery = next(supply for supply in payload["power"]["supplies"] if supply["name"] == "BAT1")
        self.assertEqual(battery["reported_power_w"], 53.946)
        self.assertEqual(battery["temperature_c"], 31.5)

    def test_low_idle_clock_is_not_high_load_constraint(self):
        for index in range(4):
            self.add_cpu(index, 400000)
        self.write("loadavg", "0.08 0.10 0.09 1/100 999", root=self.proc_root)
        self.add_zone(0, "package", 42000, (("passive", 85000),))

        payload = self.sample()

        self.assertTrue(payload["cpu"]["near_minimum"])
        self.assertFalse(payload["cpu"]["load_high"])
        self.assertEqual(payload["thermal"]["summary"], "normal")

    def test_margin_selection_prefers_zone_nearest_relevant_trip(self):
        self.add_zone(0, "far-hotter", 60000, (("passive", 100000),))
        self.add_zone(1, "nearer", 47000, (("passive", 49000),))

        payload = self.sample()

        self.assertEqual(payload["thermal"]["selected_zone"], "nearer")
        self.assertEqual(payload["thermal"]["summary"], "warm")
        self.assertEqual(payload["thermal"]["relevant_trip"]["margin_c"], 2.0)

    def test_invalid_thermal_values_and_outside_symlinks_are_ignored(self):
        self.add_zone(0, "invalid", -274000, (("passive", -274000),))
        outside = self.root / "outside-zone"
        outside.mkdir()
        (outside / "type").write_text("outside\n", encoding="utf-8")
        (outside / "temp").write_text("52000\n", encoding="utf-8")
        link = self.sys_root / "class/thermal/thermal_zone9"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside, target_is_directory=True)

        payload = self.sample()

        self.assertEqual(payload["thermal"]["summary"], "unavailable")
        self.assertEqual(payload["thermal"]["zones"], [])

    def test_partial_platform_data_returns_stable_empty_contract(self):
        payload = self.sample()

        self.assertEqual(payload["api_version"], 1)
        self.assertEqual(payload["cpu"]["cpus"], [])
        self.assertIsNone(payload["cpu"]["average_mhz"])
        self.assertEqual(payload["thermal"]["summary"], "unavailable")
        self.assertEqual(payload["power"]["charging_state"], "unknown")
        self.assertEqual(payload["power"]["supplies"], [])

    def test_intel_pstate_and_cooling_devices_are_allowlisted(self):
        self.write("devices/system/cpu/intel_pstate/status", "active")
        self.write("devices/system/cpu/intel_pstate/no_turbo", 0)
        self.write("devices/system/cpu/intel_pstate/min_perf_pct", 11)
        self.write("devices/system/cpu/intel_pstate/max_perf_pct", 100)
        self.write("class/thermal/cooling_device0/type", "TCC Offset")
        self.write("class/thermal/cooling_device0/cur_state", 10)
        self.write("class/thermal/cooling_device0/max_state", 63)

        payload = self.sample()

        self.assertEqual(
            payload["cpu"]["intel_pstate"],
            {"status": "active", "no_turbo": 0, "min_perf_pct": 11, "max_perf_pct": 100},
        )
        self.assertEqual(
            payload["thermal"]["cooling_devices"][0],
            {"device": "cooling_device0", "type": "TCC Offset", "current_state": 10, "maximum_state": 63},
        )


if __name__ == "__main__":
    unittest.main()
