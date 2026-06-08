#!/usr/bin/env python3
"""Open MMI vehicle status CLI dashboard.

Reads the persistent status snapshot written by canbusd.status_bus and renders a
small terminal dashboard. This is intentionally read-only: it does not subscribe
to CAN directly and cannot affect daemon behaviour.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


STALE_AFTER_SECONDS = 3.0
DEFAULT_REFRESH_SECONDS = 0.5


def _default_status_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "open-mmi" / "status.json"
    return Path("/tmp/open-mmi-status.json")


STATUS_PATH = Path(os.getenv("OPEN_MMI_STATUS_PATH", str(_default_status_path())))


def _load_status(path: Path = STATUS_PATH) -> Dict[str, Any]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"updated_at": None, "state": {}, "error": "status file not found"}
    except json.JSONDecodeError:
        return {"updated_at": None, "state": {}, "error": "invalid status json"}
    except Exception as exc:
        return {"updated_at": None, "state": {}, "error": str(exc)}


def _get_path(data: Dict[str, Any], dotted: str, default: Any = "-") -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _bool_label(value: Any, true: str = "ON", false: str = "OFF", unknown: str = "-") -> str:
    if value is True:
        return true
    if value is False:
        return false
    return unknown


def _open_label(value: Any) -> str:
    return _bool_label(value, true="OPEN", false="closed")


def _yes_no(value: Any) -> str:
    return _bool_label(value, true="yes", false="no")


def _age(payload: Dict[str, Any]) -> Optional[float]:
    updated_at = payload.get("updated_at")
    if updated_at is None:
        return None
    try:
        return max(0.0, time.time() - float(updated_at))
    except (TypeError, ValueError):
        return None


def _state_health(payload: Dict[str, Any]) -> str:
    if payload.get("error"):
        return "ERROR"
    age = _age(payload)
    if age is None:
        return "WAITING"
    if age > STALE_AFTER_SECONDS:
        return "STALE"
    return "LIVE"


def _clear() -> None:
    print("\033[2J\033[H", end="")


def _line(title: str = "") -> str:
    if not title:
        return "─" * 68
    label = f" {title} "
    return label.center(68, "─")


def _pair(left_label: str, left_value: Any, right_label: str = "", right_value: Any = "") -> str:
    left = f"{left_label:<18} {left_value:<14}"
    if right_label:
        right = f"{right_label:<18} {right_value:<14}"
        return f"{left} {right}"
    return left


def _render_dashboard(payload: Dict[str, Any], path: Path = STATUS_PATH) -> None:
    state = payload.get("state", {})
    age = _age(payload)
    health = _state_health(payload)

    doors = state.get("doors", {}) if isinstance(state.get("doors", {}), dict) else {}
    vehicle = state.get("vehicle", {}) if isinstance(state.get("vehicle", {}), dict) else {}
    lighting = state.get("lighting", {}) if isinstance(state.get("lighting", {}), dict) else {}

    _clear()
    print("Open MMI Vehicle Status")
    print(_line())

    if age is None:
        age_text = "never"
    else:
        age_text = f"{age:.1f}s ago"

    print(_pair("Status", health, "Last update", age_text))
    print(_pair("Vehicle present", _yes_no(_get_path(vehicle, "present", None)), "Snapshot", str(path)))

    if payload.get("error"):
        print()
        print(_line("Error"))
        print(payload["error"])
        print()
        print("Press Ctrl+C to exit.")
        return

    print()
    print(_line("Doors"))
    print(_pair("Front left", _open_label(doors.get("front_left")), "Front right", _open_label(doors.get("front_right"))))
    print(_pair("Rear left", _open_label(doors.get("rear_left")), "Rear right", _open_label(doors.get("rear_right"))))
    print(_pair("Boot", _open_label(doors.get("boot")), "Bonnet", _open_label(doors.get("bonnet"))))
    print(_pair("Any open", _yes_no(doors.get("any_open")), "Raw", doors.get("raw", "-")))

    print()
    print(_line("Vehicle"))
    print(_pair("Reverse", _bool_label(vehicle.get("reverse")), "Handbrake", _bool_label(vehicle.get("handbrake"))))
    print(_pair("Reverse raw", vehicle.get("reverse_raw", "-"), "Handbrake raw", vehicle.get("handbrake_raw", "-")))

    print()
    print(_line("Lighting"))
    dimmer = lighting.get("dimmer_percent", "-")
    if dimmer != "-":
        dimmer = f"{dimmer}%"
    indicator = _indicator_label(lighting)
    print(_pair("Mode", lighting.get("mode", "-"), "Dimmer", dimmer))
    print(_pair("Lights on", _bool_label(lighting.get("lights_on")), "Brake", _bool_label(lighting.get("brake"))))
    print(_pair("Indicators", indicator, "Hazards", _bool_label(lighting.get("hazards"))))
    print(_pair("Mode raw", lighting.get("mode_raw", "-"), "Secondary raw", lighting.get("secondary_raw", "-")))

    print()
    print(_line())
    print("Press Ctrl+C to exit.")


def _indicator_label(lighting: Dict[str, Any]) -> str:
    left = lighting.get("left_indicator")
    right = lighting.get("right_indicator")
    hazards = lighting.get("hazards")

    if hazards:
        return "hazards"
    if left and right:
        return "both"
    if left:
        return "left"
    if right:
        return "right"
    if left is False or right is False:
        return "off"
    return "-"


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _print_tree(value: Any, indent: int = 0) -> None:
    pad = "  " * indent
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            child = value[key]
            if isinstance(child, dict):
                print(f"{pad}{key}:")
                _print_tree(child, indent + 1)
            else:
                print(f"{pad}{key}: {_format_value(child)}")
    else:
        print(f"{pad}{_format_value(value)}")


def _render_raw(payload: Dict[str, Any], path: Path = STATUS_PATH) -> None:
    _clear()
    print("Open MMI Raw Status")
    print("===================")
    print()

    state = payload.get("state", {})
    if state:
        _print_tree(state)
    else:
        print("No status received yet.")

    print()
    age = _age(payload)
    print(f"Health: {_state_health(payload)}")
    print(f"Last update: {'never' if age is None else f'{age:.1f}s ago'}")
    print(f"Status file: {path}")
    if payload.get("error"):
        print(f"Error: {payload['error']}")


def _iter_once_or_forever(once: bool) -> Iterable[None]:
    yield None
    while not once:
        yield None


def main() -> None:
    parser = argparse.ArgumentParser(description="Show Open MMI vehicle status")
    parser.add_argument("--raw", action="store_true", help="show generic raw state tree")
    parser.add_argument("--once", action="store_true", help="render once and exit")
    parser.add_argument("--path", type=Path, default=STATUS_PATH, help="status JSON path")
    parser.add_argument("--refresh", type=float, default=DEFAULT_REFRESH_SECONDS, help="refresh interval in seconds")
    args = parser.parse_args()

    try:
        for _ in _iter_once_or_forever(args.once):
            payload = _load_status(args.path)
            if args.raw:
                _render_raw(payload, args.path)
            else:
                _render_dashboard(payload, args.path)
            if not args.once:
                time.sleep(max(0.1, args.refresh))
    except KeyboardInterrupt:
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
