import json
import unittest
from pathlib import Path
from unittest import mock

from canbusd.status_rules import evaluate_status_rules, parse_status_rules
from ui.web_dashboard import server


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "vehicles" / "seat_1p" / "config.json"
APP_PATH = ROOT / "ui" / "web_dashboard" / "static" / "app.js"
STATUS_CLI_PATH = ROOT / "ui" / "dashboard" / "status_cli.py"


class StatusSchemaCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = json.loads(PROFILE_PATH.read_text())

    def _recirculation_rule(self):
        return next(
            rule
            for rule in self.profile["status"]
            if rule.get("path") == "climate.recirculation_active"
        )

    def test_profile_uses_canonical_recirculation_name_with_alpha_alias(self):
        rule = self._recirculation_rule()

        self.assertEqual(rule["raw_path"], "climate.recirculation_raw")
        self.assertIn("climate.front_demist_air_request", rule["aliases"])
        self.assertIn("climate.front_demist_air_request_raw", rule["raw_aliases"])

    def test_decoder_publishes_new_and_legacy_fields_with_identical_values(self):
        grouped = parse_status_rules([self._recirculation_rule()])

        active = evaluate_status_rules(grouped[0x3E3], bytes([0, 0, 0, 0, 0x80]), 5)
        inactive = evaluate_status_rules(grouped[0x3E3], bytes([0, 0, 0, 0, 0x00]), 5)

        for update, expected, raw in ((active, True, 0x80), (inactive, False, 0x00)):
            climate = update["climate"]
            self.assertIs(climate["recirculation_active"], expected)
            self.assertIs(climate["front_demist_air_request"], expected)
            self.assertEqual(climate["recirculation_raw"], raw)
            self.assertEqual(climate["front_demist_air_request_raw"], raw)

    def test_demo_payload_keeps_new_and_legacy_fields_aligned(self):
        for now in (0.0, 50.0):
            with mock.patch.object(server.time, "time", return_value=now):
                climate = server.demo_status("drive", started_at=0.0)["state"]["climate"]
            self.assertEqual(
                climate["recirculation_active"],
                climate["front_demist_air_request"],
            )
            self.assertEqual(
                climate["air_intake"],
                "Recirc" if climate["recirculation_active"] else "Normal",
            )

    def test_consumers_prefer_canonical_name_and_fall_back_to_legacy(self):
        app_source = APP_PATH.read_text()
        cli_source = STATUS_CLI_PATH.read_text()

        self.assertIn(
            "climate.recirculation_active ?? climate.front_demist_air_request",
            app_source,
        )
        self.assertIn(
            "climate.get('recirculation_active', climate.get('front_demist_air_request'))",
            cli_source,
        )
        self.assertNotIn("Front demist air", cli_source)


if __name__ == "__main__":
    unittest.main()
