import sys
import types
import unittest
import uuid
from types import SimpleNamespace
from unittest import mock

try:
    import can
except ModuleNotFoundError:
    can = None
    fake_can = types.ModuleType("can")
    fake_can.interface = SimpleNamespace(Bus=None)
    sys.modules.setdefault("can", fake_can)

from canbusd import core
from canbusd.can_runtime import CanRuntimeConfig
from canbusd.status_rules import parse_status_rules


@unittest.skipIf(can is None, "python-can is not installed")
class VirtualCanReplayTests(unittest.TestCase):
    def test_virtual_can_frames_flow_through_daemon_decode_and_dispatch(self):
        channel = f"open-mmi-{uuid.uuid4()}"
        receiver = can.interface.Bus(channel=channel, interface="virtual")
        sender = can.interface.Bus(channel=channel, interface="virtual")

        sender.send(can.Message(arbitration_id=0x470, data=[0x01], is_extended_id=False))
        sender.send(can.Message(arbitration_id=0x5C1, data=[0x00], is_extended_id=False))
        sender.send(can.Message(arbitration_id=0x5C1, data=[0x2B], is_extended_id=False))

        runtime = CanRuntimeConfig(
            name="comfort",
            default_bus="comfort",
            interface="vcan-test",
            interface_source="test",
        )
        status_rules = parse_status_rules(
            [
                {
                    "id": "0x470",
                    "byte": 0,
                    "type": "bool",
                    "path": "vehicle.reverse",
                    "true": "0x01",
                    "false": "0x00",
                }
            ]
        )
        config = (
            {0x5C1: [(0, 0x2B, "mute_toggle")]},
            1.0,
            [],
            status_rules,
            core.Path("/tmp/virtual-can-profile.json"),
            runtime,
        )

        try:
            with (
                mock.patch.object(core, "_load_config", return_value=config),
                mock.patch.object(
                    core,
                    "_load_bindings",
                    return_value={"mute_toggle": {"module": "audio", "func": "mute_toggle"}},
                ),
                mock.patch.object(core.Path, "exists", return_value=True),
                mock.patch.object(core.time, "monotonic", return_value=1.0),
                mock.patch.object(core.can.interface, "Bus", return_value=receiver),
                mock.patch.object(core, "publish_status") as publish,
                mock.patch.object(core, "dispatch") as dispatch,
                mock.patch.object(core, "IFACE", "vcan-test"),
                mock.patch.object(core, "CAN_BUS", "comfort"),
                mock.patch.object(core, "RELOAD_INTERVAL", 60),
            ):
                core.main(max_iterations=3)
        finally:
            sender.shutdown()

        publish.assert_called_once_with({"vehicle": {"reverse": True}})
        dispatch.assert_called_once_with(
            "mute_toggle",
            {"module": "audio", "func": "mute_toggle"},
        )


if __name__ == "__main__":
    unittest.main()
