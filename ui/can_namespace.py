"""Fail-closed CAN namespace and host-egress enforcement primitives.

The physical CAN controller lives in a systemd-owned private network namespace.
The normal user session sees only a receive proxy.  Host-originated CAN data is
blocked at the proxy and again at the physical controller, while a single
one-way CAN gateway exports received frames from the physical bus.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


HOST_RECEIVE_INTERFACE = "openmmi-rx"
PRIVATE_RECEIVE_INTERFACE = "openmmi-rxp"
NAMESPACE_SERVICE = "open-mmi-can-namespace.service"
PRIVATE_PROVISION_SERVICE = "open-mmi-can-private-provision.service"

PHYSICAL_CAN_RE = re.compile(r"^can[0-9]{1,3}$")
MAX_COMMAND_OUTPUT = 512 * 1024
COMMAND_TIMEOUT = 10.0

CommandRunner = Callable[[Sequence[str]], None]
OutputRunner = Callable[[Sequence[str]], bytes]


class CanNamespaceError(RuntimeError):
    """The fixed CAN namespace policy could not be established exactly."""


def _run(argv: Sequence[str]) -> None:
    try:
        result = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=COMMAND_TIMEOUT,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise CanNamespaceError("CAN namespace command could not run") from exc
    if result.returncode != 0:
        raise CanNamespaceError("CAN namespace command failed")


def _output(argv: Sequence[str]) -> bytes:
    try:
        result = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=COMMAND_TIMEOUT,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise CanNamespaceError("CAN namespace evidence command could not run") from exc
    if len(result.stdout) + len(result.stderr) > MAX_COMMAND_OUTPUT:
        raise CanNamespaceError("CAN namespace command output exceeds safety limit")
    # can-utils cangw LIST returns the successful netlink sendto() byte count
    # from main(), so a valid read-only listing can exit non-zero. Keep this
    # exception exact and let the strict gateway parser validate stdout.
    cangw_list_exit_quirk = (
        tuple(argv) == ("/usr/bin/cangw", "-L")
        and result.returncode > 0
        and not result.stderr
    )
    if result.returncode != 0 and not cangw_list_exit_quirk:
        raise CanNamespaceError("CAN namespace evidence command failed")
    return result.stdout


def _json_output(argv: Sequence[str], output_runner: OutputRunner) -> Any:
    raw = output_runner(argv)
    if len(raw) > MAX_COMMAND_OUTPUT:
        raise CanNamespaceError("CAN namespace JSON output exceeds safety limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CanNamespaceError("CAN namespace command returned invalid JSON") from exc


def namespace_anchor_pid(
    output_runner: Optional[OutputRunner] = None,
) -> int:
    output = output_runner or _output
    raw = output(
        (
            "/usr/bin/systemctl",
            "show",
            "--property=MainPID",
            "--value",
            NAMESPACE_SERVICE,
        )
    )
    try:
        value = int(raw.decode("ascii").strip(), 10)
    except (UnicodeError, ValueError) as exc:
        raise CanNamespaceError("CAN namespace anchor PID is invalid") from exc
    if value <= 1:
        raise CanNamespaceError("CAN namespace anchor is not running")
    return value


def _one_link(
    interface: str,
    output_runner: OutputRunner,
) -> Mapping[str, Any]:
    document = _json_output(
        (
            "/sbin/ip",
            "-details",
            "-json",
            "link",
            "show",
            "dev",
            interface,
        ),
        output_runner,
    )
    if not isinstance(document, list) or len(document) != 1:
        raise CanNamespaceError("CAN interface evidence is missing or ambiguous")
    item = document[0]
    if not isinstance(item, Mapping) or item.get("ifname") != interface:
        raise CanNamespaceError("CAN interface evidence identifies the wrong interface")
    return item


def _link_kind(item: Mapping[str, Any]) -> Optional[str]:
    linkinfo = item.get("linkinfo")
    return str(linkinfo.get("info_kind")) if isinstance(linkinfo, Mapping) and linkinfo.get("info_kind") else None


def _ctrlmode(item: Mapping[str, Any]) -> list[str]:
    linkinfo = item.get("linkinfo")
    info_data = linkinfo.get("info_data") if isinstance(linkinfo, Mapping) else None
    ctrlmode = info_data.get("ctrlmode") if isinstance(info_data, Mapping) else None
    if ctrlmode is None:
        return []
    if not isinstance(ctrlmode, list) or any(not isinstance(value, str) for value in ctrlmode):
        raise CanNamespaceError("CAN controller mode evidence is malformed")
    return sorted(set(ctrlmode))


def _tc_items(document: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(document, list) or any(not isinstance(item, Mapping) for item in document):
        raise CanNamespaceError(f"{label} evidence is malformed")
    return list(document)


def _drop_action(action: Mapping[str, Any]) -> bool:
    if action.get("kind") != "gact":
        return False
    control = action.get("control_action")
    if isinstance(control, Mapping):
        value = control.get("type")
        if isinstance(value, str) and value.lower() in {"drop", "shot"}:
            return True
    return False


def _handle_one(value: object) -> bool:
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


def _exact_drop_filter(document: Any) -> bool:
    items = _tc_items(document, "CAN egress filter")
    if not items:
        return False
    detailed: list[Mapping[str, Any]] = []
    for item in items:
        if item.get("kind") != "matchall" or item.get("protocol") != "all" or item.get("pref") != 1:
            return False
        options = item.get("options")
        if options is None:
            continue
        if not isinstance(options, Mapping) or not _handle_one(options.get("handle")):
            return False
        actions = options.get("actions")
        if (
            not isinstance(actions, list)
            or len(actions) != 1
            or not isinstance(actions[0], Mapping)
            or not _drop_action(actions[0])
        ):
            return False
        detailed.append(item)
    return len(detailed) == 1


def _exact_clsact(document: Any) -> bool:
    items = _tc_items(document, "CAN qdisc")
    return len(items) == 1 and items[0].get("kind") == "clsact"


def egress_drop_evidence(
    interface: str,
    *,
    output_runner: Optional[OutputRunner] = None,
) -> tuple[bool, bool]:
    output = output_runner or _output
    qdisc = _json_output(
        ("/sbin/tc", "-json", "qdisc", "show", "dev", interface, "clsact"),
        output,
    )
    filters = _json_output(
        ("/sbin/tc", "-json", "filter", "show", "dev", interface, "egress"),
        output,
    )
    return _exact_clsact(qdisc), _exact_drop_filter(filters)


def ensure_egress_drop(
    interface: str,
    *,
    command_runner: Optional[CommandRunner] = None,
    output_runner: Optional[OutputRunner] = None,
) -> None:
    """Install or repair the fixed egress DROP policy while caller keeps link DOWN."""

    run = command_runner or _run
    output = output_runner or _output

    qdisc_doc = _json_output(
        ("/sbin/tc", "-json", "qdisc", "show", "dev", interface, "clsact"),
        output,
    )
    qdiscs = _tc_items(qdisc_doc, "CAN qdisc")
    if not qdiscs:
        run(("/sbin/tc", "qdisc", "add", "dev", interface, "clsact"))
    elif not _exact_clsact(qdisc_doc):
        raise CanNamespaceError("CAN clsact state is ambiguous")

    filter_doc = _json_output(
        ("/sbin/tc", "-json", "filter", "show", "dev", interface, "egress"),
        output,
    )
    filters = _tc_items(filter_doc, "CAN egress filter")
    if not _exact_drop_filter(filter_doc):
        if filters:
            run(("/sbin/tc", "filter", "del", "dev", interface, "egress"))
        run(
            (
                "/sbin/tc",
                "filter",
                "add",
                "dev",
                interface,
                "egress",
                "pref",
                "1",
                "handle",
                "1",
                "protocol",
                "all",
                "matchall",
                "action",
                "drop",
            )
        )

    clsact_ok, filter_ok = egress_drop_evidence(interface, output_runner=output)
    if not clsact_ok or not filter_ok:
        raise CanNamespaceError("CAN egress DROP policy could not be verified")


def _sysfs_link(
    interface: str,
    *,
    sys_class_net: Path,
) -> tuple[Path, bool, int]:
    entry = sys_class_net / interface
    try:
        resolved = entry.resolve(strict=True)
        virtual_root = (sys_class_net.parent.parent / "devices" / "virtual" / "net").resolve(strict=True)
        try:
            resolved.relative_to(virtual_root)
            virtual = True
        except ValueError:
            virtual = False
        interface_type = int((entry / "type").read_text(encoding="ascii").strip(), 10)
    except (OSError, UnicodeError, ValueError) as exc:
        raise CanNamespaceError("CAN interface cannot be inspected safely") from exc
    return resolved, virtual, interface_type


def stage_host_network(
    physical_interface: str,
    *,
    anchor_pid: int,
    sys_class_net: Path = Path("/sys/class/net"),
    command_runner: Optional[CommandRunner] = None,
    output_runner: Optional[OutputRunner] = None,
) -> str:
    """Stage the host receive proxy and move a present physical controller private.

    The proxy and any present physical interface are kept DOWN until their
    enforcement state has been installed or until the private provisioner takes
    ownership.  A physical controller already in the private namespace appears
    absent here and is handled by the private stage.
    """

    if not PHYSICAL_CAN_RE.fullmatch(physical_interface):
        raise CanNamespaceError("physical CAN interface name is invalid")
    if anchor_pid <= 1:
        raise CanNamespaceError("CAN namespace anchor PID is invalid")

    run = command_runner or _run
    output = output_runner or _output
    host_proxy = sys_class_net / HOST_RECEIVE_INTERFACE
    private_peer = sys_class_net / PRIVATE_RECEIVE_INTERFACE

    host_present = host_proxy.exists()
    peer_present = private_peer.exists()
    if host_present != peer_present:
        # Normal steady state has only the host side in this namespace.  If the
        # private peer is also present, the pair has not yet crossed the boundary.
        if peer_present:
            raise CanNamespaceError("private CAN receive peer is unexpectedly in host namespace")
    if not host_present:
        run(
            (
                "/sbin/ip",
                "link",
                "add",
                HOST_RECEIVE_INTERFACE,
                "type",
                "vxcan",
                "peer",
                "name",
                PRIVATE_RECEIVE_INTERFACE,
            )
        )
        run(("/sbin/ip", "link", "set", "dev", HOST_RECEIVE_INTERFACE, "down"))
        run(("/sbin/ip", "link", "set", "dev", PRIVATE_RECEIVE_INTERFACE, "down"))
        ensure_egress_drop(
            HOST_RECEIVE_INTERFACE,
            command_runner=run,
            output_runner=output,
        )
        run(
            (
                "/sbin/ip",
                "link",
                "set",
                "dev",
                PRIVATE_RECEIVE_INTERFACE,
                "netns",
                str(anchor_pid),
            )
        )
    else:
        item = _one_link(HOST_RECEIVE_INTERFACE, output)
        if _link_kind(item) != "vxcan":
            raise CanNamespaceError("host CAN receive proxy is not vxcan")
        run(("/sbin/ip", "link", "set", "dev", HOST_RECEIVE_INTERFACE, "down"))
        ensure_egress_drop(
            HOST_RECEIVE_INTERFACE,
            command_runner=run,
            output_runner=output,
        )

    physical_entry = sys_class_net / physical_interface
    if physical_entry.exists():
        _resolved, virtual, interface_type = _sysfs_link(
            physical_interface,
            sys_class_net=sys_class_net,
        )
        if virtual or interface_type != 280:
            raise CanNamespaceError("selected physical CAN interface is not a physical SocketCAN link")
        run(("/sbin/ip", "link", "set", "dev", physical_interface, "down"))
        run(
            (
                "/sbin/ip",
                "link",
                "set",
                "dev",
                physical_interface,
                "netns",
                str(anchor_pid),
            )
        )
        return "moved"
    return "private-or-absent"


def activate_host_proxy(
    *,
    command_runner: Optional[CommandRunner] = None,
    output_runner: Optional[OutputRunner] = None,
) -> None:
    run = command_runner or _run
    output = output_runner or _output
    item = _one_link(HOST_RECEIVE_INTERFACE, output)
    if _link_kind(item) != "vxcan":
        raise CanNamespaceError("host CAN receive proxy is not vxcan")
    clsact_ok, filter_ok = egress_drop_evidence(
        HOST_RECEIVE_INTERFACE,
        output_runner=output,
    )
    if not clsact_ok or not filter_ok:
        raise CanNamespaceError("host CAN receive proxy egress policy is not verified")
    run(("/sbin/ip", "link", "set", "dev", HOST_RECEIVE_INTERFACE, "up"))


def quiesce_private_can(
    *,
    sys_class_net: Path = Path("/sys/class/net"),
    command_runner: Optional[CommandRunner] = None,
) -> int:
    """Bring every physical canN controller in the dedicated namespace DOWN."""

    run = command_runner or _run
    count = 0
    try:
        candidates = sorted(sys_class_net.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise CanNamespaceError("private CAN namespace cannot be enumerated") from exc
    for entry in candidates:
        if not PHYSICAL_CAN_RE.fullmatch(entry.name):
            continue
        try:
            _resolved, virtual, interface_type = _sysfs_link(entry.name, sys_class_net=sys_class_net)
        except CanNamespaceError:
            raise
        if virtual or interface_type != 280:
            continue
        run(("/sbin/ip", "link", "set", "dev", entry.name, "down"))
        count += 1
    return count


def _gateway_lines(raw: bytes) -> list[str]:
    if len(raw) > MAX_COMMAND_OUTPUT:
        raise CanNamespaceError("CAN gateway evidence exceeds safety limit")
    try:
        lines = [line.strip() for line in raw.decode("utf-8").splitlines() if line.strip()]
    except UnicodeError as exc:
        raise CanNamespaceError("CAN gateway evidence is not UTF-8") from exc
    return lines


def exact_one_way_gateway(
    physical_interface: str,
    *,
    output_runner: Optional[OutputRunner] = None,
) -> bool:
    output = output_runner or _output
    lines = _gateway_lines(output(("/usr/bin/cangw", "-L")))
    prefix = f"cangw -A -s {physical_interface} -d {PRIVATE_RECEIVE_INTERFACE}"
    return len(lines) == 1 and lines[0].startswith(prefix)


def provision_private_network(
    physical_interface: str,
    bitrate: int,
    *,
    sys_class_net: Path = Path("/sys/class/net"),
    command_runner: Optional[CommandRunner] = None,
    output_runner: Optional[OutputRunner] = None,
) -> str:
    """Configure the private physical CAN path and bring it UP only after verification."""

    if not PHYSICAL_CAN_RE.fullmatch(physical_interface):
        raise CanNamespaceError("physical CAN interface name is invalid")
    if isinstance(bitrate, bool) or not isinstance(bitrate, int) or bitrate <= 0:
        raise CanNamespaceError("physical CAN bitrate is invalid")

    run = command_runner or _run
    output = output_runner or _output
    physical_entry = sys_class_net / physical_interface
    if not physical_entry.exists():
        return "absent"

    _resolved, virtual, interface_type = _sysfs_link(
        physical_interface,
        sys_class_net=sys_class_net,
    )
    if virtual or interface_type != 280:
        raise CanNamespaceError("selected physical CAN interface is not a physical SocketCAN link")

    peer_entry = sys_class_net / PRIVATE_RECEIVE_INTERFACE
    if not peer_entry.exists():
        raise CanNamespaceError("private CAN receive peer is missing")
    peer_item = _one_link(PRIVATE_RECEIVE_INTERFACE, output)
    if _link_kind(peer_item) != "vxcan":
        raise CanNamespaceError("private CAN receive peer is not vxcan")

    run(("/sbin/ip", "link", "set", "dev", physical_interface, "down"))
    run(
        (
            "/sbin/ip",
            "link",
            "set",
            "dev",
            physical_interface,
            "type",
            "can",
            "bitrate",
            str(bitrate),
            "listen-only",
            "off",
        )
    )
    ensure_egress_drop(
        physical_interface,
        command_runner=run,
        output_runner=output,
    )

    run(("/sbin/ip", "link", "set", "dev", PRIVATE_RECEIVE_INTERFACE, "up"))
    run(("/usr/bin/cangw", "-F"))
    run(
        (
            "/usr/bin/cangw",
            "-A",
            "-s",
            physical_interface,
            "-d",
            PRIVATE_RECEIVE_INTERFACE,
        )
    )
    if not exact_one_way_gateway(physical_interface, output_runner=output):
        raise CanNamespaceError("private CAN gateway is not exactly one-way")

    physical_item = _one_link(physical_interface, output)
    if _link_kind(physical_item) != "can":
        raise CanNamespaceError("private physical interface is not CAN")
    if "LISTEN-ONLY" in _ctrlmode(physical_item):
        raise CanNamespaceError("private physical CAN controller is still listen-only")
    clsact_ok, filter_ok = egress_drop_evidence(physical_interface, output_runner=output)
    if not clsact_ok or not filter_ok:
        raise CanNamespaceError("private physical CAN egress policy is not verified")

    # This is deliberately last: any failure above leaves the vehicle-facing
    # controller down.
    run(("/sbin/ip", "link", "set", "dev", physical_interface, "up"))
    return "configured"
