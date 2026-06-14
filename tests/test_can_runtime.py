import unittest

from canbusd.can_runtime import item_matches_bus, resolve_can_runtime


class CanRuntimeTests(unittest.TestCase):
    def test_defaults_without_profile_metadata(self):
        runtime = resolve_can_runtime({}, env={})

        self.assertEqual(runtime.name, "comfort")
        self.assertEqual(runtime.default_bus, "comfort")
        self.assertEqual(runtime.interface, "can0")
        self.assertEqual(runtime.interface_source, "default")
        self.assertFalse(runtime.bring_up)

    def test_profile_default_bus_and_interface_metadata(self):
        runtime = resolve_can_runtime(
            {
                "default_bus": "comfort",
                "can_buses": {
                    "comfort": {
                        "interface": "can1",
                        "bitrate": 100000,
                        "capture_point": "radio harness",
                        "provisioning": "udev",
                    }
                },
            },
            env={},
        )

        self.assertEqual(runtime.name, "comfort")
        self.assertEqual(runtime.interface, "can1")
        self.assertEqual(runtime.interface_source, "profile:comfort.interface")
        self.assertEqual(runtime.bitrate, 100000)
        self.assertEqual(runtime.capture_point, "radio harness")
        self.assertEqual(runtime.provisioning, "udev")
        self.assertTrue(runtime.declared)

    def test_environment_interface_override_wins(self):
        runtime = resolve_can_runtime(
            {
                "default_bus": "comfort",
                "can_buses": {
                    "comfort": {
                        "interface": "can0",
                        "bitrate": 100000,
                    }
                },
            },
            env={
                "OPEN_MMI_CAN_BUS": "comfort",
                "OPEN_MMI_CAN_INTERFACE": "vcan0",
            },
        )

        self.assertEqual(runtime.name, "comfort")
        self.assertEqual(runtime.interface, "vcan0")
        self.assertEqual(runtime.interface_source, "env:OPEN_MMI_CAN_INTERFACE")

    def test_environment_named_bus_selection(self):
        runtime = resolve_can_runtime(
            {
                "default_bus": "comfort",
                "can_buses": {
                    "comfort": {"interface": "can0"},
                    "powertrain": {"interface": "can1", "bitrate": 500000},
                },
            },
            env={"OPEN_MMI_CAN_BUS": "powertrain"},
        )

        self.assertEqual(runtime.name, "powertrain")
        self.assertEqual(runtime.interface, "can1")
        self.assertEqual(runtime.bitrate, 500000)

    def test_missing_bus_item_belongs_to_default_bus(self):
        self.assertTrue(item_matches_bus({}, "comfort", "comfort"))
        self.assertFalse(item_matches_bus({}, "powertrain", "comfort"))

    def test_explicit_bus_item(self):
        self.assertTrue(item_matches_bus({"bus": "comfort"}, "comfort", "comfort"))
        self.assertFalse(item_matches_bus({"bus": "comfort"}, "powertrain", "comfort"))

    def test_list_bus_item(self):
        item = {"bus": ["comfort", "replay"]}

        self.assertTrue(item_matches_bus(item, "comfort", "comfort"))
        self.assertTrue(item_matches_bus(item, "replay", "comfort"))
        self.assertFalse(item_matches_bus(item, "powertrain", "comfort"))


if __name__ == "__main__":
    unittest.main()
