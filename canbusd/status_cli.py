#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
from typing import Any, Dict


def _default_status_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "open-mmi" / "status.json"
    return Path("/tmp/open-mmi-status.json")


STATUS_PATH = Path(os.getenv("OPEN_MMI_STATUS_PATH", str(_default_status_path())))


def _load_status() -> Dict[str, Any]:
    try:
        with open(STATUS_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"updated_at": None, "state": {}}
    except json.JSONDecodeError:
        return {"updated_at": None, "state": {"error": "invalid status json"}}


def _clear() -> None:
    print("\033[2J\033[H", end="")


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


def _render(payload: Dict[str, Any]) -> None:
    _clear()
    print("Open MMI Status")
    print("===============")
    print()

    state = payload.get("state", {})
    if state:
        _print_tree(state)
    else:
        print("No status received yet.")

    print()
    updated_at = payload.get("updated_at")
    if updated_at:
        print(f"Last update: {time.time() - float(updated_at):.1f}s ago")
    else:
        print("Last update: never")
    print(f"Status file: {STATUS_PATH}")


def main() -> None:
    while True:
        _render(_load_status())
        time.sleep(0.5)


if __name__ == "__main__":
    main()
