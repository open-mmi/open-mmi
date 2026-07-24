"""Verify that a SocketCAN USB adapter can wake the host."""

from __future__ import annotations

from pathlib import Path


DEFAULT_SYS_CLASS_NET = Path("/sys/class/net")


def _subsystem_name(path: Path) -> str:
    try:
        return (path / "subsystem").resolve(strict=True).name
    except OSError:
        return ""


def _enabled(path: Path) -> bool:
    try:
        return path.read_text(encoding="utf-8").strip() == "enabled"
    except OSError:
        return False


def remote_wake_ready(
    interface: str,
    sys_class_net: Path = DEFAULT_SYS_CLASS_NET,
) -> bool:
    """Return whether the adapter and host wake ancestry are enabled.

    The check is topology-driven. It does not assume a USB port or PCI address.
    A direct USB device and a PCI controller must both expose enabled wake nodes;
    every additional wake node found on the parent chain must also be enabled.
    """

    try:
        current = (sys_class_net / interface / "device").resolve(strict=True)
    except OSError:
        return False

    wake_nodes: list[tuple[Path, str, Path]] = []
    visited: set[Path] = set()
    while current not in visited:
        visited.add(current)
        wake = current / "power" / "wakeup"
        if wake.is_file():
            wake_nodes.append((current, _subsystem_name(current), wake))
        parent = current.parent
        if parent == current:
            break
        current = parent

    if not wake_nodes or any(not _enabled(wake) for _, _, wake in wake_nodes):
        return False

    direct_usb = any(
        subsystem == "usb"
        and not node.name.startswith("usb")
        and ":" not in node.name
        for node, subsystem, _ in wake_nodes
    )
    pci_controller = any(
        subsystem == "pci" for _, subsystem, _ in wake_nodes
    )
    return direct_usb and pci_controller
