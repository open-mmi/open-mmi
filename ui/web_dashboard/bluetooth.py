#!/usr/bin/env python3
"""BlueZ Bluetooth media discovery and allowlisted remote controls.

This module owns the system D-Bus boundary, opaque player identifiers, cached
status payloads, request validation, and allowlisted AVRCP controls. It has no
dependency on the dashboard HTTP handler; ``server.py`` supplies a handler only
for same-origin JSON request parsing.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse


# --- Open MMI Bluetooth media source start ---
import collections as _bluetooth_collections
import hashlib as _bluetooth_hashlib
import hmac as _bluetooth_hmac
import shlex as _bluetooth_shlex
import shutil as _bluetooth_shutil
import subprocess as _bluetooth_subprocess
import threading as _bluetooth_threading

BLUETOOTH_BUSCTL_TIMEOUT_SECONDS = 2.0
BLUETOOTH_STATUS_CACHE_SECONDS = 0.65
BLUETOOTH_MAX_BODY_BYTES = 4096
_BLUETOOTH_ID_SECRET = os.urandom(32)
_BLUETOOTH_ID_REGISTRY: Any = _bluetooth_collections.OrderedDict()
_BLUETOOTH_ID_LOCK = _bluetooth_threading.Lock()
_BLUETOOTH_CACHE_LOCK = _bluetooth_threading.Lock()
_BLUETOOTH_STATUS_CACHE: Dict[str, Any] = {"at": 0.0, "payload": None}
_BLUETOOTH_ID_REGISTRY_MAX = 64


def _bluetooth_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bluetooth_timeout() -> float:
    try:
        value = float(os.getenv("OPEN_MMI_BLUETOOTH_DBUS_TIMEOUT", "2.0"))
    except (TypeError, ValueError):
        value = BLUETOOTH_BUSCTL_TIMEOUT_SECONDS
    return max(0.25, min(value, 8.0))


def _bluetooth_busctl_executable() -> str | None:
    configured = os.getenv("OPEN_MMI_BLUETOOTH_BUSCTL", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return _bluetooth_shutil.which("busctl")


def _bluetooth_busctl(*arguments: str) -> str:
    executable = _bluetooth_busctl_executable()
    if not executable:
        raise FileNotFoundError("busctl is not installed")
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    try:
        completed = _bluetooth_subprocess.run(
            [executable, "--system", "--no-pager", *arguments],
            check=False,
            stdout=_bluetooth_subprocess.PIPE,
            stderr=_bluetooth_subprocess.PIPE,
            text=True,
            timeout=_bluetooth_timeout(),
            env=env,
        )
    except _bluetooth_subprocess.TimeoutExpired as exc:
        raise TimeoutError("BlueZ did not respond in time") from exc
    if completed.returncode != 0:
        raise RuntimeError("BlueZ media control is unavailable")
    return completed.stdout.strip()


def _bluetooth_player_paths() -> list[str]:
    output = _bluetooth_busctl("tree", "org.bluez")
    paths = re.findall(
        r"(/org/bluez/[A-Za-z0-9_./-]+/player[0-9]+)\b",
        output,
    )
    return sorted(set(paths))


def _bluetooth_parse_scalar(output: str) -> Any:
    tokens = _bluetooth_shlex.split(str(output or "").strip())
    if len(tokens) < 2:
        raise ValueError("Invalid busctl property output")
    signature = tokens[0]
    value = tokens[1]
    if signature in {"s", "o", "g"}:
        return value
    if signature == "b":
        return value.lower() == "true"
    if signature in {"y", "n", "q", "i", "u", "x", "t"}:
        return int(value, 10)
    if signature == "d":
        return float(value)
    raise ValueError("Unsupported busctl property type")


def _bluetooth_parse_variant_value(tokens: list[str], index: int) -> tuple[Any, int]:
    if index >= len(tokens):
        raise ValueError("Missing D-Bus variant type")
    signature = tokens[index]
    index += 1
    if signature in {"s", "o", "g"}:
        if index >= len(tokens):
            raise ValueError("Missing D-Bus string value")
        return tokens[index], index + 1
    if signature == "b":
        if index >= len(tokens):
            raise ValueError("Missing D-Bus boolean value")
        return tokens[index].lower() == "true", index + 1
    if signature in {"y", "n", "q", "i", "u", "x", "t"}:
        if index >= len(tokens):
            raise ValueError("Missing D-Bus integer value")
        return int(tokens[index], 10), index + 1
    if signature == "d":
        if index >= len(tokens):
            raise ValueError("Missing D-Bus floating-point value")
        return float(tokens[index]), index + 1
    if signature == "as":
        if index >= len(tokens):
            raise ValueError("Missing D-Bus array size")
        count = int(tokens[index], 10)
        start = index + 1
        end = start + count
        if end > len(tokens):
            raise ValueError("Truncated D-Bus string array")
        return tokens[start:end], end
    raise ValueError("Unsupported D-Bus variant type")


def _bluetooth_parse_track(output: str) -> Dict[str, Any]:
    tokens = _bluetooth_shlex.split(str(output or "").strip())
    if len(tokens) < 2 or tokens[0] != "a{sv}":
        raise ValueError("Invalid BlueZ Track property")
    count = int(tokens[1], 10)
    index = 2
    result: Dict[str, Any] = {}
    for _entry in range(count):
        if index >= len(tokens):
            raise ValueError("Truncated BlueZ Track property")
        key = tokens[index]
        value, index = _bluetooth_parse_variant_value(tokens, index + 1)
        result[str(key)] = value
    return result


def _bluetooth_property(path: str, interface: str, name: str) -> Any:
    output = _bluetooth_busctl(
        "get-property",
        "org.bluez",
        path,
        interface,
        name,
    )
    if name == "Track":
        return _bluetooth_parse_track(output)
    return _bluetooth_parse_scalar(output)


def _bluetooth_optional_property(
    path: str,
    interface: str,
    name: str,
    default: Any = None,
) -> Any:
    try:
        return _bluetooth_property(path, interface, name)
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError, OSError):
        return default


def _bluetooth_clean_text(value: Any, fallback: str = "", limit: int = 256) -> str:
    text = str(value or "")
    text = "".join(character for character in text if character >= " " and character not in "\r\n")
    text = text.strip()
    return (text or fallback)[:limit]


def _bluetooth_player_id(path: str) -> str:
    digest = _bluetooth_hmac.new(
        _BLUETOOTH_ID_SECRET,
        path.encode("utf-8"),
        _bluetooth_hashlib.sha256,
    ).hexdigest()[:40]
    token = f"b{digest}"
    with _BLUETOOTH_ID_LOCK:
        _BLUETOOTH_ID_REGISTRY[token] = path
        _BLUETOOTH_ID_REGISTRY.move_to_end(token)
        while len(_BLUETOOTH_ID_REGISTRY) > _BLUETOOTH_ID_REGISTRY_MAX:
            _BLUETOOTH_ID_REGISTRY.popitem(last=False)
    return token


def _bluetooth_resolve_player_id(value: Any) -> str:
    token = str(value or "").strip()
    if not re.fullmatch(r"b[0-9a-f]{40}", token):
        raise ValueError("Invalid Bluetooth player ID")
    with _BLUETOOTH_ID_LOCK:
        path = _BLUETOOTH_ID_REGISTRY.get(token)
        if path is not None:
            _BLUETOOTH_ID_REGISTRY.move_to_end(token)
    if path is None:
        raise FileNotFoundError("Bluetooth player expired; refresh the source")
    return str(path)


def _bluetooth_player_record(path: str) -> Dict[str, Any]:
    interface = "org.bluez.MediaPlayer1"
    status = _bluetooth_clean_text(
        _bluetooth_optional_property(path, interface, "Status", "stopped"),
        "stopped",
        32,
    ).lower()
    if status not in {"playing", "paused", "stopped", "forward-seek", "reverse-seek", "error"}:
        status = "stopped"
    position_ms = _bluetooth_optional_property(path, interface, "Position", 0)
    try:
        position_ms = max(0, int(position_ms or 0))
    except (TypeError, ValueError):
        position_ms = 0
    track = _bluetooth_optional_property(path, interface, "Track", {})
    if not isinstance(track, dict):
        track = {}
    device_path = _bluetooth_optional_property(path, interface, "Device", "")
    if not isinstance(device_path, str) or not device_path.startswith("/org/bluez/"):
        device_path = path.rsplit("/player", 1)[0]
    device_name = _bluetooth_optional_property(device_path, "org.bluez.Device1", "Alias", "")
    if not device_name:
        device_name = _bluetooth_optional_property(device_path, "org.bluez.Device1", "Name", "")
    player_name = _bluetooth_optional_property(path, interface, "Name", "")

    duration_ms = track.get("Duration", 0)
    try:
        duration_ms = max(0, int(duration_ms or 0))
    except (TypeError, ValueError):
        duration_ms = 0

    return {
        "path": path,
        "status": status,
        "position_ms": position_ms,
        "duration_ms": duration_ms,
        "title": _bluetooth_clean_text(track.get("Title"), "", 256),
        "artist": _bluetooth_clean_text(track.get("Artist"), "", 256),
        "album": _bluetooth_clean_text(track.get("Album"), "", 256),
        "device_name": _bluetooth_clean_text(device_name, "Bluetooth device", 128),
        "player_name": _bluetooth_clean_text(player_name, "Remote media player", 128),
    }


def _bluetooth_select_player(records: list[Dict[str, Any]]) -> Dict[str, Any] | None:
    selector = os.getenv("OPEN_MMI_BLUETOOTH_PLAYER", "").strip().casefold()
    if selector:
        matching = [
            record
            for record in records
            if selector in str(record.get("path", "")).casefold()
            or selector in str(record.get("device_name", "")).casefold()
            or selector in str(record.get("player_name", "")).casefold()
        ]
        if matching:
            records = matching
    priority = {
        "playing": 0,
        "forward-seek": 1,
        "reverse-seek": 1,
        "paused": 2,
        "stopped": 3,
        "error": 4,
    }
    return min(
        records,
        key=lambda record: (
            priority.get(str(record.get("status", "stopped")), 5),
            str(record.get("device_name", "")).casefold(),
            str(record.get("player_name", "")).casefold(),
        ),
        default=None,
    )


def _bluetooth_invalidate_cache() -> None:
    with _BLUETOOTH_CACHE_LOCK:
        _BLUETOOTH_STATUS_CACHE["at"] = 0.0
        _BLUETOOTH_STATUS_CACHE["payload"] = None


def _bluetooth_unavailable_payload(
    subtitle: str,
    *,
    configured: bool,
    status: str,
) -> Dict[str, Any]:
    return {
        "configured": configured,
        "available": False,
        "source": "bluetooth",
        "status": status,
        "state_label": "not connected" if configured else "unavailable",
        "title": "Bluetooth Media",
        "subtitle": subtitle,
        "player_id": None,
        "device_name": None,
        "player_name": None,
        "playback_status": "stopped",
        "position_seconds": 0.0,
        "duration_seconds": 0.0,
        "track": None,
        "controls": {
            "play_pause": False,
            "play": False,
            "pause": False,
            "stop": False,
            "previous": False,
            "next": False,
            "seek": False,
        },
    }


def _bluetooth_status_payload(*, force: bool = False) -> Dict[str, Any]:
    if _bluetooth_bool_env("OPEN_MMI_BLUETOOTH_DISABLE", False):
        return _bluetooth_unavailable_payload(
            "Bluetooth media control is disabled by OPEN_MMI_BLUETOOTH_DISABLE",
            configured=False,
            status="disabled",
        )
    if not _bluetooth_busctl_executable():
        return _bluetooth_unavailable_payload(
            "Install systemd busctl to use BlueZ Bluetooth media control",
            configured=False,
            status="unsupported",
        )

    now = time.monotonic()
    if not force:
        with _BLUETOOTH_CACHE_LOCK:
            cached = _BLUETOOTH_STATUS_CACHE.get("payload")
            cached_at = float(_BLUETOOTH_STATUS_CACHE.get("at") or 0.0)
            if isinstance(cached, dict) and now - cached_at < BLUETOOTH_STATUS_CACHE_SECONDS:
                return dict(cached)

    try:
        records = [_bluetooth_player_record(path) for path in _bluetooth_player_paths()]
        record = _bluetooth_select_player(records)
        if record is None:
            payload = _bluetooth_unavailable_payload(
                "Connect a phone with Bluetooth audio and AVRCP media control enabled",
                configured=True,
                status="disconnected",
            )
        else:
            player_id = _bluetooth_player_id(str(record["path"]))
            status = str(record.get("status") or "stopped")
            title = str(record.get("title") or "")
            artist = str(record.get("artist") or "")
            album = str(record.get("album") or "")
            duration_seconds = round(float(record.get("duration_ms") or 0) / 1000.0, 3)
            position_seconds = round(float(record.get("position_ms") or 0) / 1000.0, 3)
            metadata_key = "\0".join((title, artist, album, str(record.get("duration_ms") or 0)))
            track_token = _bluetooth_hashlib.sha256(metadata_key.encode("utf-8")).hexdigest()[:16]
            has_track = bool(title or artist or album or duration_seconds > 0)
            track = None
            if has_track:
                track = {
                    "id": f"{player_id}-{track_token}",
                    "source": "bluetooth",
                    "kind": "remote",
                    "name": title or "Bluetooth audio",
                    "artist": artist or str(record.get("device_name") or "Bluetooth device"),
                    "album": album or str(record.get("player_name") or "Remote media player"),
                    "duration_seconds": duration_seconds,
                    "position_seconds": position_seconds,
                    "image_url": None,
                    "is_remote": True,
                }
            payload = {
                "configured": True,
                "available": True,
                "source": "bluetooth",
                "status": status,
                "state_label": status.replace("-", " "),
                "title": "Bluetooth Media",
                "subtitle": f"{record['device_name']} · {record['player_name']}",
                "player_id": player_id,
                "device_name": record["device_name"],
                "player_name": record["player_name"],
                "playback_status": status,
                "position_seconds": position_seconds,
                "duration_seconds": duration_seconds,
                "track": track,
                "controls": {
                    "play_pause": True,
                    "play": True,
                    "pause": True,
                    "stop": True,
                    "previous": True,
                    "next": True,
                    "seek": False,
                },
            }
    except (FileNotFoundError, RuntimeError, TimeoutError, ValueError, OSError):
        payload = _bluetooth_unavailable_payload(
            "The dashboard could not access BlueZ on the system D-Bus",
            configured=False,
            status="error",
        )

    with _BLUETOOTH_CACHE_LOCK:
        _BLUETOOTH_STATUS_CACHE["at"] = time.monotonic()
        _BLUETOOTH_STATUS_CACHE["payload"] = dict(payload)
    return payload


_BLUETOOTH_ACTION_METHODS = {
    "play": "Play",
    "pause": "Pause",
    "stop": "Stop",
    "previous": "Previous",
    "next": "Next",
}


def _bluetooth_control(player_id: Any, action: Any) -> Dict[str, Any]:
    selected_action = str(action or "").strip().lower().replace("-", "_")
    if selected_action != "play_pause" and selected_action not in _BLUETOOTH_ACTION_METHODS:
        raise ValueError("Unsupported Bluetooth media action")
    path = _bluetooth_resolve_player_id(player_id)
    current_paths = set(_bluetooth_player_paths())
    if path not in current_paths:
        raise FileNotFoundError("Bluetooth player is no longer available")
    if selected_action == "play_pause":
        status = str(
            _bluetooth_optional_property(
                path,
                "org.bluez.MediaPlayer1",
                "Status",
                "stopped",
            )
        ).lower()
        method = "Pause" if status in {"playing", "forward-seek", "reverse-seek"} else "Play"
    else:
        method = _BLUETOOTH_ACTION_METHODS[selected_action]
    _bluetooth_busctl(
        "call",
        "org.bluez",
        path,
        "org.bluez.MediaPlayer1",
        method,
    )
    _bluetooth_invalidate_cache()
    resulting_status = {
        "Play": "playing",
        "Pause": "paused",
        "Stop": "stopped",
    }.get(method)
    return {
        "ok": True,
        "source": "bluetooth",
        "action": selected_action,
        "performed_action": method.lower(),
        "playback_status": resulting_status,
        "player_id": str(player_id),
    }


def _bluetooth_same_origin(handler: Any) -> bool:
    origin = str(handler.headers.get("Origin") or "").strip()
    if not origin:
        return True
    host = str(handler.headers.get("Host") or "").strip().casefold()
    try:
        parsed = urlparse(origin)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and parsed.netloc.casefold() == host


def _bluetooth_json_body(handler: Any) -> Dict[str, Any]:
    content_type = str(handler.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ValueError("Bluetooth controls require application/json")
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid request length") from exc
    if length <= 0 or length > BLUETOOTH_MAX_BODY_BYTES:
        raise ValueError("Invalid request length")
    try:
        payload = json.loads(handler.rfile.read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON request") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON request must be an object")
    return payload
# --- Open MMI Bluetooth media source end ---
