from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ui import can_namespace as canns


class CanNamespaceTests(unittest.TestCase):
    @staticmethod
    def clsact_json() -> bytes:
        return json.dumps([{"kind": "clsact"}]).encode()

    @staticmethod
    def drop_json() -> bytes:
        return json.dumps([
            {"protocol": "all", "pref": 1, "kind": "matchall", "chain": 0},
            {
                "protocol": "all",
                "pref": 1,
                "kind": "matchall",
                "chain": 0,
                "options": {
                    "handle": 1,
                    "actions": [
                        {"kind": "gact", "control_action": {"type": "drop"}}
                    ],
                },
            },
        ]).encode()

    def test_exact_drop_filter_accepts_qualified_tc_shape(self) -> None:
        self.assertTrue(canns._exact_drop_filter(json.loads(self.drop_json())))
        broken = json.loads(self.drop_json())
        broken[-1]["options"]["actions"][0]["control_action"]["type"] = "pass"
        self.assertFalse(canns._exact_drop_filter(broken))

    def test_ensure_egress_drop_repairs_only_while_caller_keeps_link_down(self) -> None:
        state = {"drop": False}
        commands = []

        def run(argv):
            command = tuple(argv)
            commands.append(command)
            if command[:4] == ("/sbin/tc", "filter", "del", "dev"):
                state["drop"] = False
            if command[:4] == ("/sbin/tc", "filter", "add", "dev"):
                state["drop"] = True

        def output(argv):
            command = tuple(argv)
            if command[:4] == ("/sbin/tc", "-json", "qdisc", "show"):
                return self.clsact_json()
            if command[:4] == ("/sbin/tc", "-json", "filter", "show"):
                if state["drop"]:
                    return self.drop_json()
                return json.dumps([
                    {
                        "protocol": "all",
                        "pref": 1,
                        "kind": "matchall",
                        "options": {
                            "handle": 1,
                            "actions": [
                                {"kind": "gact", "control_action": {"type": "pass"}}
                            ],
                        },
                    }
                ]).encode()
            raise AssertionError(command)

        canns.ensure_egress_drop("can0", command_runner=run, output_runner=output)
        self.assertEqual(commands[0], ("/sbin/tc", "filter", "del", "dev", "can0", "egress"))
        self.assertEqual(commands[1][-3:], ("matchall", "action", "drop"))
        self.assertIn("matchall", commands[1])

    def _private_sysfs(self, root: Path) -> Path:
        class_net = root / "sys/class/net"
        virtual_root = root / "sys/devices/virtual/net"
        physical = root / "sys/devices/pci0000:00/net/can0"
        peer = virtual_root / canns.PRIVATE_RECEIVE_INTERFACE
        for path in (class_net, virtual_root, physical, peer):
            path.mkdir(parents=True, exist_ok=True)
        (physical / "type").write_text("280\n", encoding="ascii")
        (peer / "type").write_text("280\n", encoding="ascii")
        (class_net / "can0").symlink_to(os.path.relpath(physical, class_net))
        (class_net / canns.PRIVATE_RECEIVE_INTERFACE).symlink_to(
            os.path.relpath(peer, class_net)
        )
        return class_net

    def test_private_provision_is_one_way_and_physical_up_is_last(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            class_net = self._private_sysfs(Path(temporary))
            commands = []

            def run(argv):
                commands.append(tuple(argv))

            def output(argv):
                command = tuple(argv)
                if command[:6] == ("/sbin/ip", "-details", "-json", "link", "show", "dev"):
                    interface = command[-1]
                    kind = "vxcan" if interface == canns.PRIVATE_RECEIVE_INTERFACE else "can"
                    info_data = {"ctrlmode": ["BERR-REPORTING"]} if kind == "can" else {}
                    return json.dumps([{
                        "ifname": interface,
                        "linkinfo": {"info_kind": kind, "info_data": info_data},
                    }]).encode()
                if command[:4] == ("/sbin/tc", "-json", "qdisc", "show"):
                    return self.clsact_json()
                if command[:4] == ("/sbin/tc", "-json", "filter", "show"):
                    return self.drop_json()
                if command == ("/usr/bin/cangw", "-L"):
                    return b"cangw -A -s can0 -d openmmi-rxp # 0 handled 0 dropped 0 deleted\n"
                raise AssertionError(command)

            result = canns.provision_private_network(
                "can0",
                100000,
                sys_class_net=class_net,
                command_runner=run,
                output_runner=output,
            )
            self.assertEqual(result, "configured")
            self.assertIn(
                ("/sbin/ip", "link", "set", "dev", "can0", "type", "can", "bitrate", "100000", "listen-only", "off"),
                commands,
            )
            self.assertIn(("/usr/bin/cangw", "-F"), commands)
            self.assertIn(("/usr/bin/cangw", "-A", "-s", "can0", "-d", "openmmi-rxp"), commands)
            self.assertNotIn(("/usr/bin/cangw", "-A", "-s", "openmmi-rxp", "-d", "can0"), commands)
            self.assertEqual(commands[-1], ("/sbin/ip", "link", "set", "dev", "can0", "up"))

    def test_gateway_verification_rejects_reverse_or_extra_route(self) -> None:
        self.assertFalse(
            canns.exact_one_way_gateway(
                "can0",
                output_runner=lambda _argv: (
                    b"cangw -A -s can0 -d openmmi-rxp # 0 handled 0 dropped 0 deleted\n"
                    b"cangw -A -s openmmi-rxp -d can0 # 0 handled 0 dropped 0 deleted\n"
                ),
            )
        )


    def test_cangw_list_nonzero_success_status_is_usable(self) -> None:
        listing = (
            b"cangw -A -s can0 -d openmmi-rxp "
            b"# 0 handled 0 dropped 0 deleted\n"
        )
        completed = mock.Mock(returncode=36, stdout=listing, stderr=b"")
        with mock.patch.object(canns.subprocess, "run", return_value=completed):
            self.assertTrue(canns.exact_one_way_gateway("can0"))

    def test_cangw_list_nonzero_with_stderr_remains_fail_closed(self) -> None:
        listing = (
            b"cangw -A -s can0 -d openmmi-rxp "
            b"# 0 handled 0 dropped 0 deleted\n"
        )
        completed = mock.Mock(
            returncode=36,
            stdout=listing,
            stderr=b"netlink receive warning\n",
        )
        with mock.patch.object(canns.subprocess, "run", return_value=completed):
            with self.assertRaises(canns.CanNamespaceError):
                canns.exact_one_way_gateway("can0")

    def test_non_cangw_nonzero_evidence_status_remains_fail_closed(self) -> None:
        completed = mock.Mock(
            returncode=36,
            stdout=b"[]\n",
            stderr=b"",
        )
        with mock.patch.object(canns.subprocess, "run", return_value=completed):
            with self.assertRaises(canns.CanNamespaceError):
                canns._output(
                    (
                        "/sbin/ip",
                        "-details",
                        "-json",
                        "link",
                        "show",
                    )
                )


if __name__ == "__main__":
    unittest.main()
