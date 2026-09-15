from __future__ import annotations

import ast
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = (
    ROOT
    / "independent_checker"
    / "open_mmi_can_trust_test.py"
)

SPEC = importlib.util.spec_from_file_location(
    "independent_can_trust_under_test",
    CHECKER_PATH,
)
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class IndependentCanTrustTests(unittest.TestCase):
    def test_checker_imports_no_open_mmi_runtime(self) -> None:
        tree = ast.parse(
            CHECKER_PATH.read_text(encoding="utf-8")
        )
        forbidden = {
            "open_mmi_trust",
            "open_mmi_telemetry",
            "ui",
            "canbusd",
            "powerd",
            "actions",
            "bindings",
            "vehicles",
        }
        observed = []

        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)

            observed.extend(
                module
                for module in modules
                if module.split(".", 1)[0] in forbidden
            )

        self.assertEqual(observed, [])

    @staticmethod
    def _drop_filter() -> list[dict]:
        return [
            {
                "protocol": "all",
                "pref": 1,
                "kind": "matchall",
                "chain": 0,
            },
            {
                "protocol": "all",
                "pref": 1,
                "kind": "matchall",
                "chain": 0,
                "options": {
                    "handle": 1,
                    "actions": [
                        {
                            "kind": "gact",
                            "control_action": {
                                "type": "drop",
                            },
                        }
                    ],
                },
            },
        ]

    @classmethod
    def _topology_fixture(cls) -> dict:
        return {
            "schema_version": checker.TOPOLOGY_SCHEMA_VERSION,
            "service": checker.NAMESPACE_SERVICE,
            "namespace": {
                "pid_before": 123,
                "pid_after": 123,
                "identity_before": "net:[4026533000]",
                "identity_inside_before": "net:[4026533000]",
                "identity_inside_after": "net:[4026533000]",
                "identity_after": "net:[4026533000]",
            },
            "host": {
                "physical_present": False,
                "receive_link": [
                    {
                        "ifname": checker.HOST_RECEIVE_INTERFACE,
                        "ifindex": 10,
                        "link_index": 11,
                        "flags": ["UP"],
                        "link_type": "can",
                        "linkinfo": {
                            "info_kind": "vxcan",
                        },
                    }
                ],
                "receive_qdisc": [{"kind": "clsact"}],
                "receive_filter": cls._drop_filter(),
            },
            "private": {
                "physical_link": [
                    {
                        "ifname": "can0",
                        "ifindex": 12,
                        "flags": ["UP"],
                        "link_type": "can",
                        "linkinfo": {
                            "info_kind": "can",
                            "info_data": {
                                "ctrlmode": [
                                    "BERR-REPORTING",
                                ],
                                "ctrlmode_supported": [
                                    "LOOPBACK",
                                    "LISTEN-ONLY",
                                    "ONE-SHOT",
                                    "BERR-REPORTING",
                                ],
                                "bittiming_const": {
                                    "name": "gs_usb",
                                },
                            },
                        },
                        "parentbus": "usb",
                        "parentdev": "1-1:1.0",
                    }
                ],
                "peer_link": [
                    {
                        "ifname": checker.PRIVATE_RECEIVE_INTERFACE,
                        "ifindex": 11,
                        "link_index": 10,
                        "flags": ["UP"],
                        "link_type": "can",
                        "linkinfo": {
                            "info_kind": "vxcan",
                        },
                    }
                ],
                "physical_qdisc": [{"kind": "clsact"}],
                "physical_filter": cls._drop_filter(),
                "physical_driver": "/sys/bus/usb/drivers/gs_usb",
                "gateway": (
                    "cangw -A -s can0 -d openmmi-rxp "
                    "# 2499 handled 0 dropped 0 deleted\n"
                ),
            },
        }

    def test_ack_capable_private_topology_passes(self) -> None:
        result = checker.production_topology_check(
            self._topology_fixture(),
            "can0",
        )

        self.assertEqual(result["status"], checker.PASS)
        self.assertNotIn(
            "LISTEN-ONLY",
            result["evidence"]["ctrlmode"],
        )
        self.assertEqual(result["evidence"]["controller_name"], "gs_usb")
        self.assertEqual(result["evidence"]["driver_name"], "gs_usb")
        self.assertEqual(result["evidence"]["gateway_handled"], 2499)

    def test_physical_can_visible_on_host_fails(self) -> None:
        evidence = self._topology_fixture()
        evidence["host"]["physical_present"] = True

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(result["status"], checker.FAIL)

    def test_wrong_or_changed_namespace_cannot_pass(self) -> None:
        wrong = self._topology_fixture()
        wrong["namespace"]["identity_inside_before"] = "net:[4026533999]"
        wrong["namespace"]["identity_inside_after"] = "net:[4026533999]"

        changed = self._topology_fixture()
        changed["namespace"]["identity_after"] = "net:[4026533999]"

        self.assertEqual(
            checker.production_topology_check(
                wrong,
                "can0",
            )["status"],
            checker.FAIL,
        )
        self.assertEqual(
            checker.production_topology_check(
                changed,
                "can0",
            )["status"],
            checker.UNVERIFIED,
        )

    def test_wrong_vxcan_peer_fails(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["peer_link"][0]["link_index"] = 99

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(result["status"], checker.FAIL)

    def test_gateway_requires_one_exact_forward_route(self) -> None:
        variants = (
            "",
            (
                "cangw -A -s can0 -d openmmi-rxp\n"
                "cangw -A -s openmmi-rxp -d can0\n"
            ),
            (
                "cangw -A -s openmmi-rxp -d can0 "
                "# 0 handled 0 dropped 0 deleted\n"
            ),
            (
                "cangw -A -s can0 -d openmmi-rxp-extra "
                "# 0 handled 0 dropped 0 deleted\n"
            ),
        )

        for gateway in variants:
            with self.subTest(gateway=gateway):
                evidence = self._topology_fixture()
                evidence["private"]["gateway"] = gateway
                result = checker.production_topology_check(
                    evidence,
                    "can0",
                )
                self.assertEqual(
                    result["status"],
                    checker.FAIL,
                )

    def test_tc_filter_rejects_weakened_or_ambiguous_shapes(self) -> None:
        permissive = self._drop_filter()
        permissive[-1]["options"]["actions"][0][
            "control_action"
        ]["type"] = "pass"

        reordered = self._drop_filter()
        reordered.reverse()

        extra_action = self._drop_filter()
        extra_action[-1]["options"]["actions"].append(
            {
                "kind": "gact",
                "control_action": {
                    "type": "drop",
                },
            }
        )

        wrong_chain = self._drop_filter()
        wrong_chain[-1]["chain"] = 1

        unsupported = self._drop_filter()
        unsupported[-1]["options"]["actions"][0][
            "kind"
        ] = "mirred"

        for filters in (
            permissive,
            [],
            reordered,
            extra_action,
            wrong_chain,
            unsupported,
        ):
            with self.subTest(filters=filters):
                evidence = self._topology_fixture()
                evidence["private"]["physical_filter"] = filters
                result = checker.production_topology_check(
                    evidence,
                    "can0",
                )
                self.assertEqual(
                    result["status"],
                    checker.FAIL,
                )

    def test_listen_only_evidence_no_longer_certifies_production(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["physical_link"][0][
            "linkinfo"
        ]["info_data"]["ctrlmode"].append("LISTEN-ONLY")

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(result["status"], checker.FAIL)

    def test_link_down_is_not_healthy_live_reception(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["physical_link"][0]["flags"] = []

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(
            result["status"],
            checker.UNVERIFIED,
        )

    def test_absent_active_ctrlmode_with_supported_modes_passes(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["physical_link"][0][
            "linkinfo"
        ]["info_data"].pop("ctrlmode")

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(result["status"], checker.PASS)
        self.assertEqual(result["evidence"]["ctrlmode"], [])

    def test_missing_supported_mode_evidence_is_unverified(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["physical_link"][0][
            "linkinfo"
        ]["info_data"].pop("ctrlmode_supported")

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(result["status"], checker.UNVERIFIED)

    def test_supported_modes_without_listen_only_is_unverified(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["physical_link"][0][
            "linkinfo"
        ]["info_data"]["ctrlmode_supported"] = [
            "LOOPBACK",
            "ONE-SHOT",
            "BERR-REPORTING",
        ]
        evidence["private"]["physical_link"][0][
            "linkinfo"
        ]["info_data"].pop("ctrlmode")

        result = checker.production_topology_check(
            evidence,
            "can0",
        )

        self.assertEqual(result["status"], checker.UNVERIFIED)

    def test_missing_driver_or_controller_identity_is_unverified(self) -> None:
        for mutation in ("driver", "controller", "parent"):
            with self.subTest(mutation=mutation):
                evidence = self._topology_fixture()
                physical = evidence["private"]["physical_link"][0]
                if mutation == "driver":
                    evidence["private"].pop("physical_driver")
                elif mutation == "controller":
                    physical["linkinfo"]["info_data"].pop("bittiming_const")
                else:
                    physical["parentdev"] = "../escape"

                result = checker.production_topology_check(evidence, "can0")
                self.assertEqual(result["status"], checker.UNVERIFIED)

    def test_zero_gateway_receive_count_is_unverified(self) -> None:
        evidence = self._topology_fixture()
        evidence["private"]["gateway"] = (
            "cangw -A -s can0 -d openmmi-rxp "
            "# 0 handled 0 dropped 0 deleted\n"
        )
        result = checker.production_topology_check(evidence, "can0")
        self.assertEqual(result["status"], checker.UNVERIFIED)

    def test_cangw_list_success_byte_count_is_accepted(self) -> None:
        listing = (
            b"cangw -A -s can0 -d openmmi-rxp "
            b"# 2499 handled 0 dropped 0 deleted\n"
        )
        completed = mock.Mock(returncode=36, stdout=listing, stderr=b"")
        with mock.patch.object(checker.subprocess, "run", return_value=completed):
            self.assertEqual(
                checker.run_cangw_list_command(
                    (
                        "/usr/bin/nsenter",
                        "--target",
                        "123",
                        "--net",
                        "/usr/bin/cangw",
                        "-L",
                    )
                ),
                listing,
            )

    def test_cangw_list_nonzero_with_stderr_is_unverified(self) -> None:
        completed = mock.Mock(
            returncode=36,
            stdout=b"",
            stderr=b"netlink warning\n",
        )
        with mock.patch.object(checker.subprocess, "run", return_value=completed):
            with self.assertRaises(checker.EvidenceUnavailable):
                checker.run_cangw_list_command(
                    (
                        "/usr/bin/nsenter",
                        "--target",
                        "123",
                        "--net",
                        "/usr/bin/cangw",
                        "-L",
                    )
                )

    def test_collector_uses_only_read_only_topology_commands(self) -> None:
        commands: list[tuple[str, ...]] = []
        programs = dict(checker.FIXED_PROGRAMS)

        def runner(argv) -> bytes:
            command = tuple(map(str, argv))
            commands.append(command)

            if command[0] == "/usr/bin/systemctl":
                return b"123\n"
            if command[:2] == ("/usr/bin/readlink", "-f"):
                self.assertEqual(
                    command[-1],
                    "/sys/bus/usb/devices/1-1:1.0/driver",
                )
                return b"/sys/bus/usb/drivers/gs_usb\n"
            if "/usr/bin/readlink" in command:
                return b"net:[4026533000]\n"
            if "-L" in command:
                return (
                    b"cangw -A -s can0 -d openmmi-rxp "
                    b"# 2499 handled 0 dropped 0 deleted\n"
                )
            if "qdisc" in command:
                return json.dumps(
                    [{"kind": "clsact"}]
                ).encode()
            if "filter" in command:
                return json.dumps(
                    self._drop_filter()
                ).encode()
            if "link" in command and "show" in command:
                interface = command[-1]
                if interface == checker.HOST_RECEIVE_INTERFACE:
                    item = self._topology_fixture()[
                        "host"
                    ]["receive_link"][0]
                elif interface == checker.PRIVATE_RECEIVE_INTERFACE:
                    item = self._topology_fixture()[
                        "private"
                    ]["peer_link"][0]
                elif interface == "can0":
                    item = self._topology_fixture()[
                        "private"
                    ]["physical_link"][0]
                else:
                    raise AssertionError(command)
                return json.dumps([item]).encode()

            raise AssertionError(command)

        evidence = checker.collect_production_topology(
            "can0",
            programs=programs,
            runner=runner,
            gateway_runner=runner,
            namespace_reader=lambda _pid: "net:[4026533000]",
            host_presence=lambda _interface: False,
        )

        self.assertEqual(
            checker.production_topology_check(
                evidence,
                "can0",
            )["status"],
            checker.PASS,
        )

        joined = [
            " " + " ".join(command) + " "
            for command in commands
        ]
        for command in joined:
            self.assertNotIn(" link set ", command)
            self.assertNotIn(" qdisc add ", command)
            self.assertNotIn(" filter add ", command)
            self.assertNotIn(" -A ", command)
            self.assertNotIn(" -F ", command)

    def test_challenge_profile_is_receive_side_only(self) -> None:
        profile = checker.challenge_profile(
            "vcan99",
            0x5A5,
        )

        self.assertEqual(profile["rules"], [])
        self.assertEqual(profile["presence"], [])
        self.assertEqual(
            profile["status"][0]["path"],
            "engine.speed_raw",
        )
        self.assertEqual(
            profile["can_buses"]["trust-challenge"][
                "provisioning"
            ],
            "manual",
        )

    def test_exact_fresh_observation_passes(self) -> None:
        challenge = {
            "schema_version": 1,
            "can_id": 0x5A5,
            "values": list(range(16)),
            "digest": "sha256:" + "1" * 64,
        }
        frames = [
            (0x5A5, bytes([value]))
            for value in challenge["values"]
        ]

        result = checker.classify_challenge_observation(
            challenge,
            challenge["values"],
            frames,
        )

        self.assertEqual(result["status"], checker.PASS)

    def test_stale_or_wrong_status_cannot_pass(self) -> None:
        challenge = {
            "schema_version": 1,
            "can_id": 0x5A5,
            "values": list(range(16)),
            "digest": "sha256:" + "2" * 64,
        }
        frames = [
            (0x5A5, bytes([value]))
            for value in challenge["values"]
        ]

        observed = list(challenge["values"])
        observed[-1] = 200

        result = checker.classify_challenge_observation(
            challenge,
            observed,
            frames,
        )

        self.assertEqual(
            result["status"],
            checker.UNVERIFIED,
        )

    def test_additional_bus_traffic_cannot_pass(self) -> None:
        challenge = {
            "schema_version": 1,
            "can_id": 0x5A5,
            "values": list(range(16)),
            "digest": "sha256:" + "3" * 64,
        }
        frames = [
            (0x5A5, bytes([value]))
            for value in challenge["values"]
        ]
        frames.append((0x123, b"\x00"))

        result = checker.classify_challenge_observation(
            challenge,
            challenge["values"],
            frames,
        )

        self.assertEqual(
            result["status"],
            checker.UNVERIFIED,
        )

    def test_challenge_contains_sixteen_unique_values(self) -> None:
        challenge = checker.make_challenge()

        self.assertEqual(
            len(challenge["values"]),
            checker.CHALLENGE_STEPS,
        )
        self.assertEqual(
            len(set(challenge["values"])),
            checker.CHALLENGE_STEPS,
        )
        self.assertRegex(
            challenge["digest"],
            r"^sha256:[0-9a-f]{64}$",
        )


if __name__ == "__main__":
    unittest.main()
