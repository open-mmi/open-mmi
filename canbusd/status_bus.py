import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List


_subscribers: List[Callable[[Dict[str, Any]], None]] = []
_lock = threading.Lock()
_state: Dict[str, Any] = {}


def _default_status_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "open-mmi" / "status.json"

    return Path("/tmp/open-mmi-status.json")


STATUS_PATH = Path(os.getenv("OPEN_MMI_STATUS_PATH", str(_default_status_path())))


def _deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def _write_status_file(snapshot: Dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "updated_at": time.time(),
        "state": snapshot,
    }

    with tempfile.NamedTemporaryFile(
        "w",
        dir=str(STATUS_PATH.parent),
        delete=False,
    ) as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
        tmp_path = Path(f.name)

    tmp_path.replace(STATUS_PATH)


def subscribe(fn: Callable[[Dict[str, Any]], None]) -> None:
    with _lock:
        _subscribers.append(fn)


def publish(update: Dict[str, Any]) -> None:
    global _state

    with _lock:
        _deep_merge(_state, update)
        snapshot = dict(_state)

    _write_status_file(snapshot)

    for fn in _subscribers:
        fn(snapshot)


def snapshot() -> Dict[str, Any]:
    with _lock:
        return dict(_state)