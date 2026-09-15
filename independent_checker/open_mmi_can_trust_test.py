#!/usr/bin/env python3
"""Independent live CAN trust test for Open MMI.

This program intentionally imports no Open MMI Python package.

It provides two independent measurements:

* production: independently verify the fixed private physical CAN namespace,
  vxcan receive peer, one-way gateway and both egress DROP barriers;
* challenge: exercise the installed canbusd implementation as a black box on
  an already-created isolated vcanN interface.

The challenge is receive-side only from Open MMI's perspective.  The checker
owns the transmitting socket.  Open MMI is never given a CAN transmit action
or challenge-response protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


PASS = "PASS"
FAIL = "FAIL"
UNVERIFIED = "UNVERIFIED"
STATUSES = {PASS, FAIL, UNVERIFIED}

INTERFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")
VCAN_RE = re.compile(r"^vcan[0-9]{1,3}$")
PHYSICAL_CAN_RE = re.compile(r"^can[0-9]{1,3}$")
NAMESPACE_ID_RE = re.compile(r"^net:\[[0-9]+\]$")
GATEWAY_STATS_RE = re.compile(
    r"^(?P<handled>[0-9]+) handled "
    r"(?P<dropped>[0-9]+) dropped "
    r"(?P<deleted>[0-9]+) deleted$"
)
SYSFS_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:@+-]{1,128}$")

HOST_RECEIVE_INTERFACE = "openmmi-rx"
PRIVATE_RECEIVE_INTERFACE = "openmmi-rxp"
NAMESPACE_SERVICE = "open-mmi-can-namespace.service"
TOPOLOGY_SCHEMA_VERSION = 2

FIXED_PROGRAMS = {
    "systemctl": Path("/usr/bin/systemctl"),
    "nsenter": Path("/usr/bin/nsenter"),
    "readlink": Path("/usr/bin/readlink"),
    "ip": Path("/sbin/ip"),
    "tc": Path("/sbin/tc"),
    "cangw": Path("/usr/bin/cangw"),
}

CAN_FRAME = struct.Struct("=IB3x8s")
CAN_ID_MASK = 0x1FFFFFFF
CHALLENGE_STEPS = 16
MAX_IP_OUTPUT = 512 * 1024
MAX_COMMAND_OUTPUT = 512 * 1024
MAX_STATUS_BYTES = 256 * 1024


class CanTrustError(RuntimeError):
    pass


class EvidenceUnavailable(CanTrustError):
    pass


def check(check_id: str, status: str, summary: str, **evidence: Any) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(status)
    return {
        "id": check_id,
        "status": status,
        "summary": summary,
        "evidence": evidence,
    }


def overall_status(checks: Sequence[Mapping[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in checks}
    if FAIL in statuses:
        return FAIL
    if UNVERIFIED in statuses:
        return UNVERIFIED
    return PASS


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def validate_interface(value: str, *, vcan: bool = False) -> str:
    expression = VCAN_RE if vcan else INTERFACE_RE
    if not isinstance(value, str) or not expression.fullmatch(value):
        raise CanTrustError("CAN interface name is invalid")
    return value


def trusted_ip_program(explicit: str | None = None) -> Path:
    candidates: list[Path] = []

    if explicit:
        candidates.append(Path(explicit))
    else:
        for value in (
            "/usr/sbin/ip",
            "/usr/bin/ip",
            "/sbin/ip",
            "/bin/ip",
        ):
            candidates.append(Path(value))

        resolved = shutil.which("ip")
        if resolved:
            candidate = Path(resolved)
            if candidate not in candidates:
                candidates.append(candidate)

    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
            metadata = resolved.stat()
        except OSError:
            continue

        if (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_uid == 0
            and not metadata.st_mode & 0o022
            and metadata.st_mode & 0o111
        ):
            return resolved

    raise EvidenceUnavailable("trusted system ip executable is unavailable")


def ip_link_document(ip_program: Path, interface: str) -> Any:
    try:
        result = subprocess.run(
            [
                str(ip_program),
                "-details",
                "-json",
                "link",
                "show",
                "dev",
                interface,
            ],
            env={
                "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceUnavailable("could not inspect live CAN interface") from exc

    if len(result.stdout) + len(result.stderr) > MAX_IP_OUTPUT:
        raise CanTrustError("ip output exceeds safety limit")

    if result.returncode != 0:
        raise EvidenceUnavailable("live CAN interface cannot be inspected")

    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceUnavailable("ip did not return usable JSON") from exc


def one_link(document: Any, interface: str) -> Mapping[str, Any]:
    if not isinstance(document, list) or len(document) != 1:
        raise EvidenceUnavailable("live interface evidence is missing or ambiguous")

    item = document[0]
    if not isinstance(item, Mapping) or item.get("ifname") != interface:
        raise EvidenceUnavailable("live interface evidence does not identify requested interface")

    return item


def trusted_fixed_program(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise EvidenceUnavailable(
            f"trusted system {label} executable is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & 0o022
        or not metadata.st_mode & 0o111
    ):
        raise EvidenceUnavailable(
            f"trusted system {label} executable is unavailable"
        )
    return path


def production_programs() -> dict[str, Path]:
    return {
        name: trusted_fixed_program(path, name)
        for name, path in FIXED_PROGRAMS.items()
    }


def run_readonly_command(argv: Sequence[str]) -> bytes:
    try:
        result = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5.0,
            env={
                "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise EvidenceUnavailable(
            "CAN topology evidence command could not run"
        ) from exc
    if len(result.stdout) + len(result.stderr) > MAX_COMMAND_OUTPUT:
        raise EvidenceUnavailable(
            "CAN topology evidence command exceeded safety limit"
        )
    if result.returncode != 0:
        raise EvidenceUnavailable("CAN topology evidence command failed")
    return result.stdout


def run_cangw_list_command(argv: Sequence[str]) -> bytes:
    command = tuple(map(str, argv))
    valid_shape = (
        len(command) == 6
        and command[0] == str(FIXED_PROGRAMS["nsenter"])
        and command[1] == "--target"
        and command[2].isdigit()
        and int(command[2], 10) > 1
        and command[3] == "--net"
        and command[4:] == (str(FIXED_PROGRAMS["cangw"]), "-L")
    )
    if not valid_shape:
        raise EvidenceUnavailable("CAN gateway evidence command is invalid")
    try:
        result = subprocess.run(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5.0,
            env={
                "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise EvidenceUnavailable(
            "CAN gateway evidence command could not run"
        ) from exc
    if len(result.stdout) + len(result.stderr) > MAX_COMMAND_OUTPUT:
        raise EvidenceUnavailable(
            "CAN gateway evidence command exceeded safety limit"
        )
    successful_nonzero_list = (
        result.returncode > 0
        and bool(result.stdout)
        and not result.stderr
    )
    if result.returncode != 0 and not successful_nonzero_list:
        raise EvidenceUnavailable("CAN gateway evidence command failed")
    return result.stdout


def json_command(argv: Sequence[str], runner=run_readonly_command) -> Any:
    try:
        return json.loads(runner(argv).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceUnavailable(
            "CAN topology command did not return usable JSON"
        ) from exc


def service_main_pid(
    systemctl: Path,
    runner=run_readonly_command,
) -> int:
    raw = runner(
        (
            str(systemctl),
            "show",
            "--property=MainPID",
            "--value",
            NAMESPACE_SERVICE,
        )
    )
    try:
        pid = int(raw.decode("ascii").strip(), 10)
    except (UnicodeError, ValueError) as exc:
        raise EvidenceUnavailable("CAN namespace anchor PID is invalid") from exc
    if pid <= 1:
        raise EvidenceUnavailable("CAN namespace anchor is not running")
    return pid


def namespace_identity(
    pid: int,
    *,
    proc_root: Path = Path("/proc"),
) -> str:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 1:
        raise EvidenceUnavailable("CAN namespace anchor PID is invalid")
    try:
        value = os.readlink(proc_root / str(pid) / "ns/net")
    except OSError as exc:
        raise EvidenceUnavailable(
            "CAN namespace identity cannot be read"
        ) from exc
    if not NAMESPACE_ID_RE.fullmatch(value):
        raise EvidenceUnavailable("CAN namespace identity is malformed")
    return value


def host_interface_present(
    interface: str,
    *,
    sys_class_net: Path = Path("/sys/class/net"),
) -> bool:
    try:
        (sys_class_net / interface).lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise EvidenceUnavailable(
            "host CAN interface presence cannot be inspected"
        ) from exc
    return True


def nsenter_command(
    programs: Mapping[str, Path],
    pid: int,
    argv: Sequence[str],
) -> tuple[str, ...]:
    return (
        str(programs["nsenter"]),
        "--target",
        str(pid),
        "--net",
        *map(str, argv),
    )


def collect_production_topology(
    interface: str,
    *,
    programs: Mapping[str, Path] | None = None,
    runner=run_readonly_command,
    gateway_runner=run_cangw_list_command,
    namespace_reader=namespace_identity,
    host_presence=host_interface_present,
) -> dict[str, Any]:
    if not isinstance(interface, str) or not PHYSICAL_CAN_RE.fullmatch(interface):
        raise CanTrustError(
            "production CAN interface must be a physical canN name"
        )
    tools = dict(programs) if programs is not None else production_programs()
    if set(tools) != set(FIXED_PROGRAMS):
        raise EvidenceUnavailable("required CAN topology tools are unavailable")

    pid = service_main_pid(tools["systemctl"], runner)
    identity = namespace_reader(pid)

    def inside(*argv: str) -> bytes:
        return runner(nsenter_command(tools, pid, argv))

    def inside_json(*argv: str) -> Any:
        return json_command(nsenter_command(tools, pid, argv), runner)

    entered_before = inside(
        str(tools["readlink"]),
        "/proc/self/ns/net",
    ).decode("ascii").strip()
    if not NAMESPACE_ID_RE.fullmatch(entered_before):
        raise EvidenceUnavailable("entered CAN namespace identity is malformed")

    visible = host_presence(interface)
    host: dict[str, Any] = {"physical_present": visible}
    private: dict[str, Any] = {}

    if not visible:
        host.update(
            {
                "receive_link": json_command(
                    (
                        str(tools["ip"]),
                        "-details",
                        "-json",
                        "link",
                        "show",
                        "dev",
                        HOST_RECEIVE_INTERFACE,
                    ),
                    runner,
                ),
                "receive_qdisc": json_command(
                    (
                        str(tools["tc"]),
                        "-json",
                        "qdisc",
                        "show",
                        "dev",
                        HOST_RECEIVE_INTERFACE,
                        "clsact",
                    ),
                    runner,
                ),
                "receive_filter": json_command(
                    (
                        str(tools["tc"]),
                        "-json",
                        "filter",
                        "show",
                        "dev",
                        HOST_RECEIVE_INTERFACE,
                        "egress",
                    ),
                    runner,
                ),
            }
        )
        physical_link = inside_json(
            str(tools["ip"]),
            "-details",
            "-statistics",
            "-json",
            "link",
            "show",
            "dev",
            interface,
        )
        physical_item = strict_one_link(physical_link, interface)
        parent = topology_parent_device(physical_item)
        if parent is None:
            raise EvidenceUnavailable(
                "physical CAN parent-device evidence is unavailable"
            )
        parentbus, parentdev = parent
        driver_path = (
            Path("/sys/bus")
            / parentbus
            / "devices"
            / parentdev
            / "driver"
        )
        try:
            driver_target = runner(
                (
                    str(tools["readlink"]),
                    "-f",
                    str(driver_path),
                )
            ).decode("ascii").strip()
        except UnicodeError as exc:
            raise EvidenceUnavailable(
                "physical CAN driver evidence is malformed"
            ) from exc
        if not driver_target:
            raise EvidenceUnavailable(
                "physical CAN driver evidence is unavailable"
            )

        private.update(
            {
                "physical_link": physical_link,
                "peer_link": inside_json(
                    str(tools["ip"]),
                    "-details",
                    "-json",
                    "link",
                    "show",
                    "dev",
                    PRIVATE_RECEIVE_INTERFACE,
                ),
                "physical_qdisc": inside_json(
                    str(tools["tc"]),
                    "-json",
                    "qdisc",
                    "show",
                    "dev",
                    interface,
                    "clsact",
                ),
                "physical_filter": inside_json(
                    str(tools["tc"]),
                    "-json",
                    "filter",
                    "show",
                    "dev",
                    interface,
                    "egress",
                ),
                "physical_driver": driver_target,
                "gateway": gateway_runner(
                    nsenter_command(
                        tools,
                        pid,
                        (str(tools["cangw"]), "-L"),
                    )
                ).decode("utf-8"),
            }
        )

    entered_after = inside(
        str(tools["readlink"]),
        "/proc/self/ns/net",
    ).decode("ascii").strip()
    if not NAMESPACE_ID_RE.fullmatch(entered_after):
        raise EvidenceUnavailable("entered CAN namespace identity is malformed")
    pid_after = service_main_pid(tools["systemctl"], runner)

    return {
        "schema_version": TOPOLOGY_SCHEMA_VERSION,
        "service": NAMESPACE_SERVICE,
        "namespace": {
            "pid_before": pid,
            "pid_after": pid_after,
            "identity_before": identity,
            "identity_inside_before": entered_before,
            "identity_inside_after": entered_after,
            "identity_after": namespace_reader(pid_after),
        },
        "host": host,
        "private": private,
    }


def strict_one_link(document: Any, interface: str) -> Mapping[str, Any]:
    if (
        not isinstance(document, list)
        or len(document) != 1
        or not isinstance(document[0], Mapping)
    ):
        raise CanTrustError("CAN link evidence is missing or ambiguous")
    item = document[0]
    if item.get("ifname") != interface:
        raise CanTrustError(
            "CAN link evidence identifies the wrong interface"
        )
    return item


def topology_link_kind(item: Mapping[str, Any]) -> str | None:
    linkinfo = item.get("linkinfo")
    value = linkinfo.get("info_kind") if isinstance(linkinfo, Mapping) else None
    return value if isinstance(value, str) else None


def topology_link_flags(item: Mapping[str, Any]) -> list[str] | None:
    flags = item.get("flags")
    if (
        not isinstance(flags, list)
        or any(not isinstance(value, str) for value in flags)
    ):
        return None
    return flags


def topology_parent_device(
    item: Mapping[str, Any],
) -> tuple[str, str] | None:
    parentbus = item.get("parentbus")
    parentdev = item.get("parentdev")
    if (
        not isinstance(parentbus, str)
        or not isinstance(parentdev, str)
        or parentbus in {".", ".."}
        or parentdev in {".", ".."}
        or SYSFS_TOKEN_RE.fullmatch(parentbus) is None
        or SYSFS_TOKEN_RE.fullmatch(parentdev) is None
    ):
        return None
    return parentbus, parentdev


def topology_controller_name(item: Mapping[str, Any]) -> str | None:
    linkinfo = item.get("linkinfo")
    info_data = (
        linkinfo.get("info_data")
        if isinstance(linkinfo, Mapping)
        else None
    )
    bittiming_const = (
        info_data.get("bittiming_const")
        if isinstance(info_data, Mapping)
        else None
    )
    name = (
        bittiming_const.get("name")
        if isinstance(bittiming_const, Mapping)
        else None
    )
    if (
        not isinstance(name, str)
        or SYSFS_TOKEN_RE.fullmatch(name) is None
    ):
        return None
    return name


def topology_driver_name(raw: Any, parentbus: str) -> str | None:
    if not isinstance(raw, str):
        return None
    prefix = f"/sys/bus/{parentbus}/drivers/"
    if not raw.startswith(prefix):
        return None
    driver = raw[len(prefix):]
    if (
        not driver
        or "/" in driver
        or driver in {".", ".."}
        or SYSFS_TOKEN_RE.fullmatch(driver) is None
    ):
        return None
    return driver


def topology_ctrlmode(
    item: Mapping[str, Any],
) -> tuple[list[str], list[str]] | None:
    linkinfo = item.get("linkinfo")
    info_data = (
        linkinfo.get("info_data")
        if isinstance(linkinfo, Mapping)
        else None
    )
    if not isinstance(info_data, Mapping):
        return None
    supported = info_data.get("ctrlmode_supported")
    if (
        not isinstance(supported, list)
        or any(not isinstance(value, str) for value in supported)
        or "LISTEN-ONLY" not in supported
    ):
        return None
    if "ctrlmode" in info_data:
        ctrlmode = info_data.get("ctrlmode")
        if (
            not isinstance(ctrlmode, list)
            or any(not isinstance(value, str) for value in ctrlmode)
        ):
            return None
    else:
        # iproute2 omits active ctrlmode when the kernel flag word is zero.
        ctrlmode = []
    return sorted(set(ctrlmode)), sorted(set(supported))

def exact_clsact(document: Any) -> bool:
    return (
        isinstance(document, list)
        and len(document) == 1
        and isinstance(document[0], Mapping)
        and document[0].get("kind") == "clsact"
    )


def handle_one(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        try:
            return int(value.rstrip(":"), 0) == 1
        except ValueError:
            return False
    return False


def exact_egress_drop(document: Any) -> bool:
    if (
        not isinstance(document, list)
        or len(document) != 2
        or any(not isinstance(item, Mapping) for item in document)
    ):
        return False
    summary, detail = document

    def header(item: Mapping[str, Any]) -> bool:
        return (
            item.get("protocol") == "all"
            and item.get("pref") == 1
            and item.get("kind") == "matchall"
            and item.get("chain") == 0
        )

    options = detail.get("options")
    actions = options.get("actions") if isinstance(options, Mapping) else None
    if (
        not header(summary)
        or not header(detail)
        or "options" in summary
        or not isinstance(options, Mapping)
        or not handle_one(options.get("handle"))
        or not isinstance(actions, list)
        or len(actions) != 1
        or not isinstance(actions[0], Mapping)
        or actions[0].get("kind") != "gact"
    ):
        return False
    control = actions[0].get("control_action")
    return (
        isinstance(control, Mapping)
        and control.get("type") in {"drop", "shot"}
    )


def parse_exact_gateway(
    raw: Any,
    physical_interface: str,
) -> dict[str, int | None] | None:
    if not isinstance(raw, str):
        return None
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    command, separator, stats = lines[0].partition(" # ")
    expected = [
        "cangw",
        "-A",
        "-s",
        physical_interface,
        "-d",
        PRIVATE_RECEIVE_INTERFACE,
    ]
    if command.split() != expected:
        return None
    if not separator:
        return {
            "handled": None,
            "dropped": None,
            "deleted": None,
        }
    match = GATEWAY_STATS_RE.fullmatch(stats)
    if match is None:
        return None
    return {
        key: int(match.group(key), 10)
        for key in ("handled", "dropped", "deleted")
    }


def exact_gateway(raw: Any, physical_interface: str) -> bool:
    return parse_exact_gateway(raw, physical_interface) is not None

def production_topology_check(
    evidence: Any,
    interface: str,
) -> dict[str, Any]:
    try:
        if not isinstance(evidence, Mapping):
            raise EvidenceUnavailable(
                "production topology evidence is unavailable"
            )
        if evidence.get("schema_version") != TOPOLOGY_SCHEMA_VERSION:
            raise EvidenceUnavailable(
                "production topology evidence version is unsupported"
            )
        if evidence.get("service") != NAMESPACE_SERVICE:
            return check(
                "can.production-topology-v2",
                FAIL,
                "Production CAN evidence used the wrong namespace service.",
                interface=interface,
            )

        namespace = evidence.get("namespace")
        if not isinstance(namespace, Mapping):
            raise EvidenceUnavailable("CAN namespace evidence is unavailable")
        pid_before = namespace.get("pid_before")
        pid_after = namespace.get("pid_after")
        identities = [
            namespace.get("identity_before"),
            namespace.get("identity_inside_before"),
            namespace.get("identity_inside_after"),
            namespace.get("identity_after"),
        ]
        if any(
            not isinstance(value, str)
            or not NAMESPACE_ID_RE.fullmatch(value)
            for value in identities
        ):
            raise EvidenceUnavailable(
                "CAN namespace identity evidence is unavailable"
            )
        if (
            pid_before != pid_after
            or identities[0] != identities[3]
            or identities[1] != identities[2]
        ):
            return check(
                "can.production-topology-v2",
                UNVERIFIED,
                "CAN namespace changed while topology evidence was collected.",
                interface=interface,
            )
        if identities[0] != identities[1]:
            return check(
                "can.production-topology-v2",
                FAIL,
                "Topology commands did not inspect the fixed CAN namespace.",
                interface=interface,
            )

        host = evidence.get("host")
        if not isinstance(host, Mapping):
            raise EvidenceUnavailable(
                "host CAN topology evidence is incomplete"
            )
        if host.get("physical_present") is True:
            return check(
                "can.production-topology-v2",
                FAIL,
                "Physical CAN remains visible in the host namespace.",
                interface=interface,
            )
        if host.get("physical_present") is not False:
            raise EvidenceUnavailable(
                "host physical CAN visibility evidence is unavailable"
            )
        private = evidence.get("private")
        if not isinstance(private, Mapping):
            raise EvidenceUnavailable(
                "private CAN topology evidence is incomplete"
            )

        host_receive = strict_one_link(
            host.get("receive_link"),
            HOST_RECEIVE_INTERFACE,
        )
        peer = strict_one_link(
            private.get("peer_link"),
            PRIVATE_RECEIVE_INTERFACE,
        )
        physical = strict_one_link(
            private.get("physical_link"),
            interface,
        )
        if (
            topology_link_kind(host_receive) != "vxcan"
            or topology_link_kind(peer) != "vxcan"
        ):
            return check(
                "can.production-topology-v2",
                FAIL,
                "CAN receive proxy is not the intended vxcan pair.",
                interface=interface,
            )

        indexes = (
            host_receive.get("ifindex"),
            host_receive.get("link_index"),
            peer.get("ifindex"),
            peer.get("link_index"),
        )
        if (
            not all(
                isinstance(value, int)
                and not isinstance(value, bool)
                and value > 0
                for value in indexes
            )
            or indexes[1] != indexes[2]
            or indexes[3] != indexes[0]
        ):
            return check(
                "can.production-topology-v2",
                FAIL,
                "CAN receive proxy peer identity is inconsistent.",
                interface=interface,
            )

        if (
            topology_link_kind(physical) != "can"
            or physical.get("link_type") != "can"
        ):
            return check(
                "can.production-topology-v2",
                FAIL,
                "Private production interface is not a physical CAN link.",
                interface=interface,
            )
        mode_evidence = topology_ctrlmode(physical)
        if mode_evidence is None:
            raise EvidenceUnavailable(
                "SocketCAN controller mode evidence is unavailable"
            )
        ctrlmode, ctrlmode_supported = mode_evidence
        if "LISTEN-ONLY" in ctrlmode:
            return check(
                "can.production-topology-v2",
                FAIL,
                "Private physical CAN controller is still LISTEN-ONLY.",
                interface=interface,
                ctrlmode=ctrlmode,
            )

        parent = topology_parent_device(physical)
        controller_name = topology_controller_name(physical)
        if parent is None or controller_name is None:
            raise EvidenceUnavailable(
                "physical CAN controller identity evidence is unavailable"
            )
        parentbus, parentdev = parent
        driver_name = topology_driver_name(
            private.get("physical_driver"),
            parentbus,
        )
        if driver_name is None:
            raise EvidenceUnavailable(
                "physical CAN driver evidence is unavailable"
            )

        for item, label in (
            (host_receive, "host receive proxy"),
            (peer, "private receive peer"),
            (physical, "private physical CAN"),
        ):
            flags = topology_link_flags(item)
            if flags is None:
                raise EvidenceUnavailable(
                    f"{label} link-state evidence is unavailable"
                )
            if "UP" not in flags:
                return check(
                    "can.production-topology-v2",
                    UNVERIFIED,
                    f"{label} is not UP; live reception is not established.",
                    interface=interface,
                )

        barriers = (
            (
                host.get("receive_qdisc"),
                host.get("receive_filter"),
                "host receive proxy",
            ),
            (
                private.get("physical_qdisc"),
                private.get("physical_filter"),
                "private physical CAN",
            ),
        )
        for qdisc, filters, label in barriers:
            if not exact_clsact(qdisc) or not exact_egress_drop(filters):
                return check(
                    "can.production-topology-v2",
                    FAIL,
                    f"{label} egress DROP barrier is missing or weakened.",
                    interface=interface,
                )
        gateway = parse_exact_gateway(
            private.get("gateway"),
            interface,
        )
        if gateway is None:
            return check(
                "can.production-topology-v2",
                FAIL,
                "Private CAN gateway is not exactly one-way toward the receive peer.",
                interface=interface,
            )
        handled = gateway.get("handled")
        if not isinstance(handled, int) or isinstance(handled, bool):
            raise EvidenceUnavailable(
                "private CAN live-reception counters are unavailable"
            )
        if handled <= 0:
            return check(
                "can.production-topology-v2",
                UNVERIFIED,
                "CAN topology is enforced but live reception has not been observed.",
                interface=interface,
            )

        return check(
            "can.production-topology-v2",
            PASS,
            "Independent live evidence matches the private ACK-capable receive topology.",
            interface=interface,
            namespace_identity=identities[0],
            ctrlmode=ctrlmode,
            ctrlmode_supported=ctrlmode_supported,
            controller_name=controller_name,
            driver_name=driver_name,
            parentbus=parentbus,
            parentdev=parentdev,
            gateway_handled=handled,
            host_receive_interface=HOST_RECEIVE_INTERFACE,
            private_receive_interface=PRIVATE_RECEIVE_INTERFACE,
        )
    except EvidenceUnavailable as exc:
        return check(
            "can.production-topology-v2",
            UNVERIFIED,
            "Production CAN topology could not be independently established.",
            interface=interface,
            reason=str(exc),
        )
    except CanTrustError as exc:
        return check(
            "can.production-topology-v2",
            FAIL,
            "Production CAN topology evidence is contradictory or malformed.",
            interface=interface,
            reason=str(exc),
        )


def vcan_interface_check(document: Any, interface: str) -> dict[str, Any]:
    try:
        item = one_link(document, interface)
        linkinfo = item.get("linkinfo")
        if (
            not isinstance(linkinfo, Mapping)
            or linkinfo.get("info_kind") != "vcan"
        ):
            raise EvidenceUnavailable(
                "challenge interface is not independently identified as vcan"
            )

        return check(
            "can.challenge-isolation",
            PASS,
            "Challenge interface is an explicitly selected virtual CAN device.",
            interface=interface,
            info_kind="vcan",
        )
    except EvidenceUnavailable as exc:
        return check(
            "can.challenge-isolation",
            UNVERIFIED,
            "Challenge interface isolation could not be established.",
            interface=interface,
            reason=str(exc),
        )


def pack_can_frame(can_id: int, payload: bytes) -> bytes:
    if not 0 <= can_id <= 0x7FF:
        raise CanTrustError("challenge CAN id must be an 11-bit identifier")
    if not 1 <= len(payload) <= 8:
        raise CanTrustError("challenge CAN payload length is invalid")

    return CAN_FRAME.pack(
        can_id,
        len(payload),
        payload.ljust(8, b"\x00"),
    )


def unpack_can_frame(raw: bytes) -> tuple[int, bytes]:
    if len(raw) != CAN_FRAME.size:
        raise CanTrustError("unexpected SocketCAN frame size")

    can_id, dlc, payload = CAN_FRAME.unpack(raw)
    if dlc > 8:
        raise CanTrustError("unexpected CAN DLC")

    return can_id & CAN_ID_MASK, payload[:dlc]


def make_challenge() -> dict[str, Any]:
    values: list[int] = []
    while len(values) < CHALLENGE_STEPS:
        value = secrets.randbelow(256)
        if value not in values:
            values.append(value)

    challenge = {
        "schema_version": 1,
        "can_id": 0x500 + secrets.randbelow(0x100),
        "values": values,
    }
    challenge["digest"] = sha256_bytes(canonical_json(challenge))
    return challenge


def challenge_profile(interface: str, can_id: int) -> dict[str, Any]:
    return {
        "default_bus": "trust-challenge",
        "can_buses": {
            "trust-challenge": {
                "interface": interface,
                "provisioning": "manual",
            }
        },
        "rules": [],
        "presence": [],
        "status": [
            {
                "id": f"0x{can_id:X}",
                "bus": "trust-challenge",
                "byte": 0,
                "type": "raw",
                "path": "engine.speed_raw",
            }
        ],
    }


def read_status(path: Path) -> Mapping[str, Any] | None:
    try:
        metadata = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CanTrustError("challenge status file cannot be inspected") from exc

    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > MAX_STATUS_BYTES
    ):
        raise CanTrustError("challenge status file metadata is unsafe")

    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None

    return payload if isinstance(payload, Mapping) else None


def nested_status_value(payload: Mapping[str, Any] | None) -> int | None:
    if not isinstance(payload, Mapping):
        return None

    state = payload.get("state")
    if not isinstance(state, Mapping):
        return None

    engine = state.get("engine")
    if not isinstance(engine, Mapping):
        return None

    value = engine.get("speed_raw")
    if isinstance(value, bool) or not isinstance(value, int):
        return None

    return value


def runtime_ready(
    payload: Mapping[str, Any] | None,
    interface: str,
) -> bool:
    if not isinstance(payload, Mapping):
        return False

    runtime = payload.get("runtime")
    return (
        isinstance(runtime, Mapping)
        and runtime.get("state") == "ready"
        and runtime.get("interface") == interface
        and runtime.get("active_bus") == "trust-challenge"
    )


def drain_frames(sock: socket.socket, duration: float) -> list[tuple[int, bytes]]:
    frames: list[tuple[int, bytes]] = []
    deadline = time.monotonic() + duration

    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        sock.settimeout(min(0.05, remaining))
        try:
            raw = sock.recv(CAN_FRAME.size)
        except socket.timeout:
            continue
        except OSError as exc:
            raise EvidenceUnavailable("independent CAN observation failed") from exc

        frames.append(unpack_can_frame(raw))

    return frames


def classify_challenge_observation(
    challenge: Mapping[str, Any],
    observed_status_values: Sequence[int],
    observed_frames: Sequence[tuple[int, bytes]],
) -> dict[str, Any]:
    can_id = int(challenge["can_id"])
    values = [int(value) for value in challenge["values"]]

    expected_frames = [
        (can_id, bytes([value]))
        for value in values
    ]

    evidence = {
        "challenge_digest": challenge["digest"],
        "can_id": f"0x{can_id:X}",
        "steps": len(values),
        "observed_status_values": list(observed_status_values),
        "expected_frame_count": len(expected_frames),
        "observed_frame_count": len(observed_frames),
        "observed_frames_sha256": sha256_bytes(
            canonical_json(
                [
                    [frame_id, payload.hex()]
                    for frame_id, payload in observed_frames
                ]
            )
        ),
    }

    if list(observed_status_values) != values:
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "The target did not reproduce the fresh receive-side challenge exactly.",
            **evidence,
        )

    if list(observed_frames) != expected_frames:
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "The isolated challenge bus contained missing, duplicate, or additional traffic.",
            **evidence,
        )

    return check(
        "can.challenge-bound-observation",
        PASS,
        "The target consumed the fresh challenge while independent observation saw only checker-injected frames.",
        **evidence,
    )


def target_environment(
    temporary: Path,
    interface: str,
    profile_path: Path,
    bindings_path: Path,
    status_path: Path,
) -> dict[str, str]:
    env = dict(os.environ)

    for key in list(env):
        if key.startswith("OPEN_MMI_"):
            env.pop(key, None)

    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    home = temporary / "home"
    runtime = temporary / "runtime"
    config = temporary / "config"
    home.mkdir(mode=0o700)
    runtime.mkdir(mode=0o700)
    config.mkdir(mode=0o700)

    env.update(
        {
            "HOME": str(home),
            "XDG_RUNTIME_DIR": str(runtime),
            "OPEN_MMI_VEHICLE": "independent-can-trust-challenge",
            "OPEN_MMI_BINDINGS": "independent-can-trust-challenge",
            "OPEN_MMI_VEHICLE_CONFIG": str(profile_path),
            "OPEN_MMI_BINDINGS_FILE": str(bindings_path),
            "OPEN_MMI_CAN_BUS": "trust-challenge",
            "OPEN_MMI_CAN_INTERFACE": interface,
            "OPEN_MMI_STATUS_PATH": str(status_path),
            "OPEN_MMI_CONFIG_DIR": str(config),
            "OPEN_MMI_LOG_LEVEL": "WARNING",
            "PYTHONUNBUFFERED": "1",
        }
    )

    return env


def run_challenge(
    interface: str,
    *,
    target_python: Path,
    target_working_directory: Path,
    startup_timeout: float,
    step_timeout: float,
) -> dict[str, Any]:
    validate_interface(interface, vcan=True)

    sys_path = Path("/sys/class/net") / interface
    try:
        resolved = sys_path.resolve(strict=True)
    except OSError:
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "Challenge vcan interface is unavailable.",
            interface=interface,
        )

    if "/virtual/net/" not in str(resolved):
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "Challenge interface is not a kernel virtual network device.",
            interface=interface,
            resolved=str(resolved),
        )

    if not target_python.is_file() or not os.access(target_python, os.X_OK):
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "Target Open MMI Python executable is unavailable.",
            target_python=str(target_python),
        )

    if not target_working_directory.is_dir():
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "Target Open MMI working directory is unavailable.",
            target_working_directory=str(target_working_directory),
        )

    if not all(
        hasattr(socket, name)
        for name in ("PF_CAN", "CAN_RAW")
    ):
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "This Python/kernel does not expose raw SocketCAN.",
        )

    challenge = make_challenge()

    try:
        sender = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        monitor = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        sender.bind((interface,))
        monitor.bind((interface,))
    except OSError as exc:
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "Raw SocketCAN challenge sockets could not be opened.",
            error=str(exc),
        )

    process: subprocess.Popen[bytes] | None = None

    try:
        preexisting = drain_frames(monitor, 0.25)
        if preexisting:
            return check(
                "can.challenge-bound-observation",
                UNVERIFIED,
                "Challenge interface was not quiet before the target started.",
                observed_frame_count=len(preexisting),
            )

        with tempfile.TemporaryDirectory(
            prefix="open-mmi-independent-can-"
        ) as directory:
            temporary = Path(directory)
            profile_path = temporary / "challenge-profile.json"
            bindings_path = temporary / "challenge-bindings.json"
            status_path = temporary / "status.json"
            stdout_path = temporary / "target.stdout"
            stderr_path = temporary / "target.stderr"

            profile_path.write_text(
                json.dumps(
                    challenge_profile(
                        interface,
                        int(challenge["can_id"]),
                    ),
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            bindings_path.write_text("{}\n", encoding="utf-8")

            env = target_environment(
                temporary,
                interface,
                profile_path,
                bindings_path,
                status_path,
            )

            with (
                stdout_path.open("wb") as stdout,
                stderr_path.open("wb") as stderr,
            ):
                try:
                    process = subprocess.Popen(
                        [
                            str(target_python),
                            "-m",
                            "canbusd.core",
                        ],
                        cwd=str(target_working_directory),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout,
                        stderr=stderr,
                    )
                except OSError as exc:
                    return check(
                        "can.challenge-bound-observation",
                        UNVERIFIED,
                        "Target Open MMI daemon could not be started for isolated challenge.",
                        error=str(exc),
                    )

                deadline = time.monotonic() + startup_timeout
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        return check(
                            "can.challenge-bound-observation",
                            UNVERIFIED,
                            "Target Open MMI daemon exited before challenge readiness.",
                            returncode=process.returncode,
                        )

                    if runtime_ready(read_status(status_path), interface):
                        break

                    time.sleep(0.02)
                else:
                    return check(
                        "can.challenge-bound-observation",
                        UNVERIFIED,
                        "Target Open MMI daemon did not publish ready challenge runtime.",
                    )

                ambient = drain_frames(monitor, 0.15)
                if ambient:
                    return check(
                        "can.challenge-bound-observation",
                        UNVERIFIED,
                        "Challenge interface was not quiet immediately before injection.",
                        observed_frame_count=len(ambient),
                    )

                observed_status_values: list[int] = []
                observed_frames: list[tuple[int, bytes]] = []

                for value in challenge["values"]:
                    frame = pack_can_frame(
                        int(challenge["can_id"]),
                        bytes([int(value)]),
                    )

                    try:
                        sender.send(frame)
                    except OSError as exc:
                        return check(
                            "can.challenge-bound-observation",
                            UNVERIFIED,
                            "Independent checker could not inject challenge frame.",
                            error=str(exc),
                        )

                    step_deadline = time.monotonic() + step_timeout
                    observed_value: int | None = None

                    while time.monotonic() < step_deadline:
                        if process.poll() is not None:
                            return check(
                                "can.challenge-bound-observation",
                                UNVERIFIED,
                                "Target Open MMI daemon exited during challenge.",
                                returncode=process.returncode,
                            )

                        observed_value = nested_status_value(
                            read_status(status_path)
                        )
                        if observed_value == value:
                            break

                        time.sleep(0.01)

                    if observed_value != value:
                        return check(
                            "can.challenge-bound-observation",
                            UNVERIFIED,
                            "Target did not consume one fresh challenge transition.",
                            challenge_digest=challenge["digest"],
                            expected_value=value,
                            observed_value=observed_value,
                            completed_steps=len(observed_status_values),
                        )

                    observed_status_values.append(observed_value)
                    observed_frames.extend(
                        drain_frames(monitor, 0.04)
                    )

                observed_frames.extend(
                    drain_frames(monitor, 0.25)
                )

                return classify_challenge_observation(
                    challenge,
                    observed_status_values,
                    observed_frames,
                )

    except (CanTrustError, EvidenceUnavailable) as exc:
        return check(
            "can.challenge-bound-observation",
            UNVERIFIED,
            "Independent CAN challenge evidence could not be completed.",
            reason=str(exc),
        )

    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)

        sender.close()
        monitor.close()


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    if args.mode in {"full", "production"}:
        try:
            interface = args.production_interface
            evidence = collect_production_topology(interface)
            checks.append(
                production_topology_check(
                    evidence,
                    interface,
                )
            )
        except (CanTrustError, EvidenceUnavailable) as exc:
            checks.append(
                check(
                    "can.production-topology-v2",
                    UNVERIFIED,
                    "Production CAN topology could not be independently established.",
                    interface=args.production_interface,
                    reason=str(exc),
                )
            )

    challenge_isolated = True
    ip_program: Path | None = None

    if args.mode in {"full", "challenge"}:
        try:
            ip_program = trusted_ip_program(args.ip_program)
        except EvidenceUnavailable as exc:
            challenge_isolated = False
            checks.append(
                check(
                    "can.challenge-isolation",
                    UNVERIFIED,
                    "Challenge interface type could not be independently established.",
                    reason=str(exc),
                )
            )

    if ip_program is not None and args.mode in {"full", "challenge"}:
        try:
            interface = validate_interface(
                args.challenge_interface,
                vcan=True,
            )
            document = ip_link_document(ip_program, interface)
            isolation = vcan_interface_check(document, interface)
            checks.append(isolation)
            challenge_isolated = isolation["status"] == PASS
        except (CanTrustError, EvidenceUnavailable) as exc:
            challenge_isolated = False
            checks.append(
                check(
                    "can.challenge-isolation",
                    UNVERIFIED,
                    "Challenge interface type could not be independently established.",
                    reason=str(exc),
                )
            )

    if args.mode in {"full", "challenge"}:
        if not challenge_isolated:
            checks.append(
                check(
                    "can.challenge-bound-observation",
                    UNVERIFIED,
                    "Challenge was not run because isolated vcan evidence was unavailable.",
                )
            )
        else:
            checks.append(
                run_challenge(
                    args.challenge_interface,
                    target_python=Path(args.target_python).resolve(),
                    target_working_directory=Path(
                        args.target_working_directory
                    ).resolve(),
                    startup_timeout=args.startup_timeout,
                    step_timeout=args.step_timeout,
                )
            )

    return {
        "checker": "open-mmi-independent-can-trust-test-v2",
        "mode": args.mode,
        "overall_status": overall_status(checks),
        "checks": checks,
        "note": (
            "Production PASS requires stable private-namespace topology and both "
            "egress barriers. The isolated vcan challenge is a separate "
            "receive-side evidence dimension."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independent live Open MMI CAN trust test"
    )
    parser.add_argument(
        "--mode",
        choices=("full", "production", "challenge"),
        default="full",
    )
    parser.add_argument(
        "--production-interface",
        default="can0",
    )
    parser.add_argument(
        "--challenge-interface",
        default="vcan99",
    )
    parser.add_argument(
        "--target-python",
        default="/opt/open-mmi/venv/bin/python",
    )
    parser.add_argument(
        "--target-working-directory",
        default="/opt/open-mmi",
    )
    parser.add_argument(
        "--ip-program",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--step-timeout",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--json",
        action="store_true",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.startup_timeout <= 0 or args.step_timeout <= 0:
        raise SystemExit("timeouts must be positive")

    report = inspect(args)

    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(f"Overall: {report['overall_status']}")
        for item in report["checks"]:
            print(
                f"{item['status']:10s} "
                f"{item['id']}: "
                f"{item['summary']}"
            )
        print(report["note"])

    return {
        PASS: 0,
        FAIL: 1,
        UNVERIFIED: 2,
    }[report["overall_status"]]


if __name__ == "__main__":
    raise SystemExit(main())
