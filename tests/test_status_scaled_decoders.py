import unittest

from canbusd.status_rules import evaluate_status_rules, parse_status_rules


class StatusScaledDecoderTests(unittest.TestCase):
    def test_scaled_byte_with_raw_path(self):
        grouped = parse_status_rules([
            {
                "id": "0x3E1",
                "byte": 4,
                "type": "scaled",
                "path": "climate.blower_load_percent",
                "scale": 100 / 255,
                "round": 1,
                "raw_path": "climate.blower_load_raw",
            }
        ])

        update = evaluate_status_rules(grouped[0x3E1], bytes([0, 0, 0, 0, 128]), 5)

        self.assertEqual(update["climate"]["blower_load_raw"], 128)
        self.assertEqual(update["climate"]["blower_load_percent"], 50.2)

    def test_scaled_byte_ignores_short_frames(self):
        grouped = parse_status_rules([
            {
                "id": "0x3E1",
                "byte": 4,
                "type": "scaled",
                "path": "climate.blower_load_percent",
                "scale": 100 / 255,
            }
        ])

        update = evaluate_status_rules(grouped[0x3E1], bytes([0, 0, 0, 0]), 4)

        self.assertEqual(update, {})

    def test_u16le_with_scale_and_raw_path(self):
        grouped = parse_status_rules([
            {
                "id": "0x351",
                "type": "u16le",
                "start_byte": 1,
                "path": "vehicle.speed_kmh",
                "scale": 0.005,
                "round": 1,
                "raw_path": "vehicle.speed_raw",
            }
        ])

        # bytes[1:3] = 0x2710 little-endian = 10000; 10000 / 200 = 50.0 km/h
        update = evaluate_status_rules(grouped[0x351], bytes([0, 0x10, 0x27]), 3)

        self.assertEqual(update["vehicle"]["speed_raw"], 10000)
        self.assertEqual(update["vehicle"]["speed_kmh"], 50.0)

    def test_u16le_ignores_short_frames(self):
        grouped = parse_status_rules([
            {
                "id": "0x351",
                "type": "u16le",
                "start_byte": 1,
                "path": "vehicle.speed_kmh",
                "scale": 0.005,
            }
        ])

        update = evaluate_status_rules(grouped[0x351], bytes([0, 0x10]), 2)

        self.assertEqual(update, {})


if __name__ == "__main__":
    unittest.main()
