import sys
import threading
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

from canbusd import core, dispatcher
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
                core.main(max_iterations=3, dispatch_fn=core.dispatch)
        finally:
            sender.shutdown()

        publish.assert_called_once_with({"vehicle": {"reverse": True}})
        dispatch.assert_called_once_with(
            "mute_toggle",
            {"module": "audio", "func": "mute_toggle"},
        )


    def test_slow_action_worker_does_not_block_sustained_virtual_can_replay(self):
        channel = f"open-mmi-load-{uuid.uuid4()}"
        receiver = can.interface.Bus(channel=channel, interface="virtual")
        sender = can.interface.Bus(channel=channel, interface="virtual")

        sender.send(can.Message(arbitration_id=0x5C1, data=[0x01], is_extended_id=False))
        for value in range(100):
            sender.send(
                can.Message(
                    arbitration_id=0x470,
                    data=[value & 0x01],
                    is_extended_id=False,
                )
            )

        runtime = CanRuntimeConfig(
            name="comfort",
            default_bus="comfort",
            interface="vcan-load-test",
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
        binding = {"module": "audio", "func": "play_pause"}
        config = (
            {0x5C1: [(0, 0x01, "play_pause")]},
            1.0,
            [],
            status_rules,
            core.Path("/tmp/virtual-can-load-profile.json"),
            runtime,
        )
        action_started = threading.Event()
        action_release = threading.Event()

        def slow_action(_event, _action, _extra_args):
            action_started.set()
            action_release.wait(2.0)

        worker = dispatcher.ActionQueue(maxsize=8)
        main_thread = None
        try:
            with (
                mock.patch.object(core, "_load_config", return_value=config),
                mock.patch.object(core, "_load_bindings", return_value={"play_pause": binding}),
                mock.patch.object(core.Path, "exists", return_value=True),
                mock.patch.object(core.time, "monotonic", return_value=1.0),
                mock.patch.object(core.can.interface, "Bus", return_value=receiver),
                mock.patch.object(core, "publish_status") as publish,
                mock.patch.object(dispatcher, "_execute_action", side_effect=slow_action),
                mock.patch.object(core, "IFACE", "vcan-load-test"),
                mock.patch.object(core, "CAN_BUS", "comfort"),
                mock.patch.object(core, "RELOAD_INTERVAL", 60),
            ):
                main_thread = threading.Thread(
                    target=core.main,
                    kwargs={"max_iterations": 101, "dispatch_fn": worker.dispatch},
                    daemon=True,
                )
                main_thread.start()
                self.assertTrue(action_started.wait(1.0))
                main_thread.join(1.0)
                self.assertFalse(
                    main_thread.is_alive(),
                    "CAN replay stalled behind the subprocess-backed action",
                )

            self.assertEqual(publish.call_count, 100)
        finally:
            action_release.set()
            worker.close(timeout=2.0)
            sender.shutdown()
            if main_thread is not None:
                main_thread.join(1.0)


if __name__ == "__main__":
    unittest.main()
