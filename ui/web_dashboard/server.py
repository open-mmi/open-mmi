#!/usr/bin/env python3
"""Open MMI factory-style web dashboard.

Read-only local web UI for the persistent Open MMI status snapshot.
It does not subscribe to CAN directly and does not transmit/control the car.
"""

from __future__ import annotations

import ssl
import argparse
import json
import math
import os
import re
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

STALE_AFTER_SECONDS = 3.0


def default_status_path() -> Path:
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "open-mmi" / "status.json"
    return Path("/tmp/open-mmi-status.json")


def load_status(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r") as f:
            payload = json.load(f)
    except FileNotFoundError:
        return {
            "updated_at": None,
            "state": {},
            "error": "status file not found",
            "path": str(path),
        }
    except json.JSONDecodeError:
        return {
            "updated_at": None,
            "state": {},
            "error": "invalid status json",
            "path": str(path),
        }
    except Exception as exc:  # pragma: no cover - defensive path
        return {
            "updated_at": None,
            "state": {},
            "error": str(exc),
            "path": str(path),
        }

    if not isinstance(payload, dict):
        payload = {"updated_at": None, "state": {}, "error": "status root is not an object"}

    payload.setdefault("state", {})
    payload["path"] = str(path)
    return payload


def health_for(payload: Dict[str, Any]) -> Dict[str, Any]:
    updated_at = payload.get("updated_at")
    now = time.time()

    if payload.get("error"):
        return {
            "status": "error",
            "age_seconds": None,
            "stale": True,
            "message": payload["error"],
        }

    if updated_at is None:
        return {
            "status": "waiting",
            "age_seconds": None,
            "stale": True,
            "message": "waiting for status snapshot",
        }

    try:
        age = max(0.0, now - float(updated_at))
    except (TypeError, ValueError):
        return {
            "status": "error",
            "age_seconds": None,
            "stale": True,
            "message": "invalid updated_at value",
        }

    stale = age > STALE_AFTER_SECONDS
    return {
        "status": "stale" if stale else "live",
        "age_seconds": age,
        "stale": stale,
        "message": "stale" if stale else "live",
    }


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _wave(t: float, period: float, phase: float = 0.0) -> float:
    """Smooth -1..1 sine wave used by the dynamic demo generator."""
    return math.sin((t / period) * math.tau + phase)


def demo_status(scenario: str, started_at: float) -> Dict[str, Any]:
    """Return a synthetic, changing status payload for UI work away from the car.

    The real dashboard polls /api/status regularly. By generating values from
    elapsed time here, demo mode exercises the existing frontend without a fake
    CAN source, browser framework, or status writer process.
    """

    scenario = (scenario or "drive").strip().lower()
    aliases = {
        "1": "drive",
        "true": "drive",
        "live": "drive",
        "doors": "doors-open",
        "door": "doors-open",
        "warning": "warnings",
        "fault": "warnings",
    }
    scenario = aliases.get(scenario, scenario)

    now = time.time()
    t = max(0.0, now - started_at)

    # A gentle driving trace: accelerate, cruise, lift, repeat. Keep it smooth so
    # the current simple gauges do not jitter too much while still looking alive.
    speed_kmh = 62.0 + 38.0 * _wave(t, 18.0) + 8.0 * _wave(t, 5.5, 0.6)
    speed_kmh = _clamp(speed_kmh, 0.0, 135.0)

    # Approximate RPM response with small gear-change dips. It is deliberately
    # plausible-looking, not a vehicle model.
    shift_dip = max(0.0, _wave(t, 7.0, 1.2)) * 420.0
    rpm = 780.0 + speed_kmh * 31.0 + 280.0 * _wave(t, 4.0, 0.25) - shift_dip
    rpm = _clamp(rpm, 720.0, 5200.0)

    coolant_c = 88.0 + 5.0 * (1.0 - math.exp(-t / 80.0)) + 1.2 * _wave(t, 45.0)
    voltage_v = 13.85 + 0.12 * _wave(t, 9.0)
    outside_c = 12.2 + 0.6 * _wave(t, 60.0)
    blower_pct = 34.0 + 22.0 * (0.5 + 0.5 * _wave(t, 11.0, 0.7))
    dimmer_pct = 55.0 + 25.0 * (0.5 + 0.5 * _wave(t, 15.0, 0.9))
    range_km = max(0.0, 402.0 - (speed_kmh * t / 3600.0) * 0.9)
    odometer_km = 214302.4 + speed_kmh * t / 3600.0
    blink_on = int(t * 2.0) % 2 == 0

    vehicle = {
        "speed_kmh": round(speed_kmh, 1),
        "odometer_km": round(odometer_km, 1),
        "handbrake": False,
        "reverse": False,
    }
    engine = {
        "speed_rpm": round(rpm),
        "coolant_temp_c": round(coolant_c, 1),
    }
    electrical = {
        "supply_voltage_v": round(voltage_v, 2),
        "terminal30_voltage_v": round(voltage_v, 2),
    }
    climate = {
        "outside_temp_regulation_c": round(outside_c, 1),
        "outside_temp_unfiltered_c": round(outside_c + 0.3 * _wave(t, 8.0), 1),
        "blower_load_percent": round(blower_pct, 1),
        "rear_window_heater_requested": 20.0 < (t % 80.0) < 35.0,
        "front_demist_air_request": False,
        "compressor_active": _wave(t, 30.0) > -0.35,
        "air_intake": "Recirc" if 45.0 < (t % 90.0) < 58.0 else "Normal",
    }
    lighting = {
        "mode": "Auto",
        "lights_on": _wave(t, 40.0) < 0.1,
        "left_indicator": False,
        "right_indicator": False,
        "hazards": False,
        "bulb_out": False,
        "dimmer_percent": round(dimmer_pct, 1),
    }
    doors = {
        "front_left": False,
        "front_right": False,
        "rear_left": False,
        "rear_right": False,
        "boot": False,
        "bonnet": False,
        "any_open": False,
    }

    if scenario == "traffic":
        stop_go = 0.5 + 0.5 * _wave(t, 16.0, -1.4)
        vehicle["speed_kmh"] = round(_clamp(stop_go * 42.0, 0.0, 48.0), 1)
        engine["speed_rpm"] = round(780.0 + stop_go * 1600.0 + 90.0 * _wave(t, 2.5))
        lighting["left_indicator"] = blink_on and 8.0 < (t % 28.0) < 16.0
        lighting["right_indicator"] = blink_on and 18.0 < (t % 34.0) < 26.0
    elif scenario == "doors-open":
        vehicle["speed_kmh"] = 0.0
        engine["speed_rpm"] = round(805.0 + 25.0 * _wave(t, 3.0))
        vehicle["handbrake"] = True
        doors["front_left"] = True
        doors["boot"] = (int(t / 4.0) % 2) == 0
        doors["any_open"] = any(doors.values())
    elif scenario == "reverse":
        vehicle["speed_kmh"] = round(3.0 + 2.0 * (0.5 + 0.5 * _wave(t, 5.0)), 1)
        engine["speed_rpm"] = round(880.0 + 130.0 * _wave(t, 3.5))
        vehicle["reverse"] = True
    elif scenario == "warnings":
        vehicle["speed_kmh"] = 0.0
        engine["speed_rpm"] = round(830.0 + 35.0 * _wave(t, 3.0))
        engine["coolant_temp_c"] = round(112.0 + 5.5 * (0.5 + 0.5 * _wave(t, 10.0)), 1)
        electrical["supply_voltage_v"] = round(11.4 + 0.15 * _wave(t, 6.0), 2)
        electrical["terminal30_voltage_v"] = electrical["supply_voltage_v"]
        vehicle["handbrake"] = True
        lighting["hazards"] = blink_on
        lighting["left_indicator"] = blink_on
        lighting["right_indicator"] = blink_on
        lighting["bulb_out"] = True
        doors["front_left"] = True
        doors["boot"] = True
        doors["any_open"] = True
    elif scenario == "stale":
        # Values move in the JSON, but updated_at is deliberately old so the
        # existing health indicator can be checked.
        pass

    updated_at = now - (STALE_AFTER_SECONDS + 3.0) if scenario == "stale" else now

    return {
        "updated_at": updated_at,
        "state": {
            "vehicle": vehicle,
            "engine": engine,
            "electrical": electrical,
            "climate": climate,
            "lighting": lighting,
            "fuel": {
                "range_km_candidate": round(range_km, 1),
                "range_km_rounded_candidate": round(range_km / 10.0) * 10.0,
            },
            "doors": doors,
        },
        "path": f"demo://{scenario}",
        "demo": {
            "enabled": True,
            "scenario": scenario,
            "elapsed_seconds": round(t, 1),
        },
    }






# --- Open MMI Jellyfin local audio client start ---
JELLYFIN_TIMEOUT_SECONDS = 4.0
JELLYFIN_ACTIVE_WITHIN_SECONDS = 600
JELLYFIN_AUDIO_CHUNK_BYTES = 64 * 1024
JELLYFIN_CLIENT_NAME = "Open MMI"
JELLYFIN_DEVICE_ID = "open-mmi-dashboard"
JELLYFIN_CLIENT_VERSION = "0.1.0"
_JELLYFIN_LOGIN_CACHE: Dict[str, Dict[str, Any]] = {}


def _jellyfin_config() -> Dict[str, Any]:
    url = os.getenv("OPEN_MMI_JELLYFIN_URL", "").strip().rstrip("/")
    token = os.getenv("OPEN_MMI_JELLYFIN_TOKEN", "").strip()
    username = os.getenv("OPEN_MMI_JELLYFIN_USERNAME", "").strip()
    password_set = "OPEN_MMI_JELLYFIN_PASSWORD" in os.environ
    password = os.getenv("OPEN_MMI_JELLYFIN_PASSWORD", "")
    session_id = os.getenv("OPEN_MMI_JELLYFIN_SESSION_ID", "").strip()
    device_name = os.getenv("OPEN_MMI_JELLYFIN_DEVICE", "").strip().casefold()
    user_id = os.getenv("OPEN_MMI_JELLYFIN_USER_ID", "").strip()
    library_id = os.getenv("OPEN_MMI_JELLYFIN_LIBRARY_ID", "").strip()
    username_configured = bool(username and password_set)
    return {
        "configured": bool(url and (token or username_configured)),
        "url": url,
        "token": token,
        "username": username,
        "password": password,
        "username_configured": username_configured,
        "auth_mode": "token" if token else "username" if username_configured else "",
        "session_id": session_id,
        "device_name": device_name,
        "user_id": user_id,
        "library_id": library_id,
        "allow_global": _env_flag("OPEN_MMI_JELLYFIN_ALLOW_GLOBAL"),
        "insecure_tls": _env_flag("OPEN_MMI_JELLYFIN_INSECURE_TLS"),
    }

def _jellyfin_header_value(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\"')


def _jellyfin_login_auth_header(config: Dict[str, Any]) -> str:
    device_name = os.getenv("OPEN_MMI_JELLYFIN_DEVICE", "").strip() or "Dashboard"
    device_id = os.getenv("OPEN_MMI_JELLYFIN_DEVICE_ID", "").strip() or JELLYFIN_DEVICE_ID
    return (
        f'MediaBrowser Client="{_jellyfin_header_value(JELLYFIN_CLIENT_NAME)}", '
        f'Device="{_jellyfin_header_value(device_name)}", '
        f'DeviceId="{_jellyfin_header_value(device_id)}", '
        f'Version="{_jellyfin_header_value(JELLYFIN_CLIENT_VERSION)}"'
    )


def _jellyfin_login(config: Dict[str, Any]) -> Dict[str, Any]:
    from urllib.error import HTTPError, URLError
    from urllib.request import Request

    if not config.get("username_configured"):
        raise RuntimeError("Jellyfin username/password is not configured")

    device_id = os.getenv("OPEN_MMI_JELLYFIN_DEVICE_ID", "").strip() or JELLYFIN_DEVICE_ID
    cache_key = "|".join([str(config.get("url") or ""), str(config.get("username") or ""), device_id])
    cached = _JELLYFIN_LOGIN_CACHE.get(cache_key)
    if cached and cached.get("token"):
        return cached

    url = f"{config['url']}/Users/AuthenticateByName"
    body = json.dumps({"Username": config.get("username", ""), "Pw": config.get("password", "")}).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": _jellyfin_login_auth_header(config),
        },
        method="POST",
    )

    try:
        with _jellyfin_urlopen(request, config, timeout=JELLYFIN_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Jellyfin login HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Jellyfin login connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Jellyfin login timed out") from exc

    if not isinstance(payload, dict) or not payload.get("AccessToken"):
        raise RuntimeError("Jellyfin login did not return an access token")

    user = payload.get("User") if isinstance(payload.get("User"), dict) else {}
    login = {
        "token": str(payload["AccessToken"]),
        "user_id": str(user.get("Id") or ""),
        "user_name": str(user.get("Name") or config.get("username") or ""),
    }
    _JELLYFIN_LOGIN_CACHE[cache_key] = login
    return login


def _jellyfin_access_token(config: Dict[str, Any]) -> str:
    token = str(config.get("token") or "")
    if token:
        return token

    login = _jellyfin_login(config)
    token = str(login.get("token") or "")
    if not token:
        raise RuntimeError("Jellyfin login did not return an access token")

    config["token"] = token
    if login.get("user_id") and not config.get("user_id"):
        config["user_id"] = login["user_id"]
    return token


def _jellyfin_auth_headers(config: Dict[str, Any]) -> Dict[str, str]:
    token = _jellyfin_access_token(config)
    return {
        "Accept": "application/json",
        "Authorization": f"MediaBrowser Token={token}",
        "X-MediaBrowser-Token": token,
        "X-Emby-Token": token,
    }

def _jellyfin_urlopen(request: Any, config: Dict[str, Any], *, timeout: float):
    from urllib.request import urlopen

    if config.get("insecure_tls"):
        context = ssl._create_unverified_context()
        return urlopen(request, timeout=timeout, context=context)
    return urlopen(request, timeout=timeout)


def _jellyfin_request_json(config: Dict[str, Any], path: str) -> Any:
    from urllib.error import HTTPError, URLError
    from urllib.request import Request

    url = f"{config['url']}{path}"
    request = Request(url, headers=_jellyfin_auth_headers(config))
    try:
        with _jellyfin_urlopen(request, config, timeout=JELLYFIN_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = exc.read(512).decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Jellyfin HTTP {exc.code}{suffix}") from exc
    except URLError as exc:
        raise RuntimeError(f"Jellyfin connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Jellyfin request timed out") from exc

def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_jellyfin_id(value: Any, label: str = "item") -> str:
    candidate = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", candidate):
        raise ValueError(f"Invalid Jellyfin {label} id")
    return candidate


def _jellyfin_media_filter(value: str) -> str:
    aliases = {
        "favorite": "favorites",
        "favourite": "favorites",
        "favourites": "favorites",
        "a-z": "az",
        "name": "az",
    }
    candidate = aliases.get(str(value or "recent").strip().lower(), str(value or "recent").strip().lower())
    if candidate not in {"recent", "favorites", "az"}:
        raise ValueError("Unsupported media filter; use recent, favorites, or az")
    return candidate


def _jellyfin_scope_params(config: Dict[str, Any]) -> Dict[str, str]:
    params: Dict[str, str] = {}
    user_id = _jellyfin_user_id(config)
    if user_id:
        params["UserId"] = user_id
    library_id = config.get("library_id")
    if library_id:
        params["ParentId"] = _safe_jellyfin_id(library_id, "library")
    return params

def _jellyfin_user_id(config: Dict[str, Any]) -> str | None:
    configured_user_id = str(config.get("user_id") or "").strip()

    # Assigned-user login returns the authoritative Jellyfin user. Preserve that
    # flow and reject an explicit conflicting scope override.
    if config.get("username_configured") and not config.get("token"):
        login = _jellyfin_login(config)
        login_user_id = _safe_jellyfin_id(login.get("user_id"), "user")
        if configured_user_id:
            explicit_user_id = _safe_jellyfin_id(configured_user_id, "user")
            if explicit_user_id != login_user_id:
                raise RuntimeError(
                    "OPEN_MMI_JELLYFIN_USER_ID does not match the assigned-user login"
                )
        config["user_id"] = login_user_id
        return login_user_id

    if configured_user_id:
        return _safe_jellyfin_id(configured_user_id, "user")

    # A server API key is not a user session, so /Users/Me is not a reliable way
    # to derive scope. Allow an exact username to act as a friendly scope selector.
    if config.get("token"):
        scope_username = str(config.get("username") or "").strip()
        if scope_username:
            users = _jellyfin_request_json(config, "/Users")
            if not isinstance(users, list):
                raise RuntimeError("Jellyfin /Users did not return a user list")
            matches = [
                user
                for user in users
                if isinstance(user, dict)
                and user.get("Id")
                and str(user.get("Name") or "").casefold() == scope_username.casefold()
            ]
            if len(matches) != 1:
                raise RuntimeError(
                    "OPEN_MMI_JELLYFIN_USERNAME must exactly match one Jellyfin user "
                    "when used with OPEN_MMI_JELLYFIN_TOKEN"
                )
            user_id = _safe_jellyfin_id(matches[0]["Id"], "user")
            config["user_id"] = user_id
            return user_id

        if config.get("allow_global"):
            return None
        raise RuntimeError(
            "Jellyfin user scope is required for an API key. Set "
            "OPEN_MMI_JELLYFIN_USER_ID or OPEN_MMI_JELLYFIN_USERNAME, or explicitly "
            "set OPEN_MMI_JELLYFIN_ALLOW_GLOBAL=1 for legacy global access."
        )

    if config.get("allow_global"):
        return None
    raise RuntimeError(
        "Jellyfin user scope is required. Set OPEN_MMI_JELLYFIN_USER_ID or use "
        "assigned-user login."
    )

def _jellyfin_validate_item_access(config: Dict[str, Any], item_id: str) -> str | None:
    from urllib.parse import urlencode

    safe_item_id = _safe_jellyfin_id(item_id)
    scope = _jellyfin_scope_params(config)
    params = {
        **scope,
        "Ids": safe_item_id,
        "IncludeItemTypes": "Audio",
        "Recursive": "true",
        "Limit": "1",
        "EnableImages": "false",
    }
    data = _jellyfin_request_json(config, "/Items?" + urlencode(params))
    items = data.get("Items", []) if isinstance(data, dict) else []
    for item in items:
        if not isinstance(item, dict) or str(item.get("Id", "")) != safe_item_id:
            continue
        if item.get("Type") == "Audio" or item.get("MediaType") == "Audio":
            return scope.get("UserId")
    raise PermissionError("Jellyfin item is outside the configured user/library scope")

def _ticks_to_seconds(value: Any) -> float | None:
    try:
        ticks = float(value)
    except (TypeError, ValueError):
        return None
    return ticks / 10_000_000.0


def _format_jellyfin_item(item: Dict[str, Any]) -> Dict[str, Any]:
    artists = item.get("Artists") or []
    album_artist = item.get("AlbumArtist")
    artist = album_artist or ", ".join(map(str, artists[:3]))
    album = item.get("Album") or item.get("AlbumName")
    runtime_seconds = _ticks_to_seconds(item.get("RunTimeTicks"))
    item_id = str(item.get("Id") or "")
    image_url = None
    if item_id and (item.get("ImageTags", {}) or {}).get("Primary"):
        image_url = f"/api/jellyfin/image/{item_id}"
    return {
        "id": item_id,
        "name": item.get("Name") or "Untitled",
        "artist": artist or "Unknown artist",
        "album": album or "",
        "duration_seconds": runtime_seconds,
        "image_url": image_url,
    }


def _jellyfin_demo_tracks() -> Dict[str, Any]:
    return {
        "configured": True,
        "demo": True,
        "items": [
            {"id": "demo-night-drive", "name": "Night Drive", "artist": "Open MMI Demo", "album": "Synthetic Radio", "duration_seconds": 224, "image_url": None},
            {"id": "demo-morning-commute", "name": "Morning Commute", "artist": "Open MMI Demo", "album": "Synthetic Radio", "duration_seconds": 188, "image_url": None},
            {"id": "demo-road-trip", "name": "Road Trip Mix", "artist": "Open MMI Demo", "album": "Synthetic Radio", "duration_seconds": 256, "image_url": None},
        ],
    }


def _jellyfin_demo_status() -> Dict[str, Any]:
    now = time.time()
    duration = 224.0
    position = now % duration
    return {
        "configured": True,
        "demo": True,
        "status": "idle",
        "state_label": "local player ready",
        "server_name": "demo://jellyfin",
        "title": "Jellyfin demo",
        "subtitle": "Local audio player layout preview",
        "client": "Open MMI",
        "device_name": "Dashboard",
        "user_name": "demo",
        "position_seconds": round(position, 1),
        "runtime_seconds": duration,
        "progress_percent": round((position / duration) * 100.0, 1),
        "image_url": None,
    }


def _pick_jellyfin_session(
    sessions: list[Dict[str, Any]],
    config: Dict[str, Any],
    user_id: str | None = None,
) -> Dict[str, Any] | None:
    # Never expose an arbitrary active session. A session must match an explicit
    # selector, and user-scoped deployments only accept sessions for that user.
    candidates = [session for session in sessions if isinstance(session, dict)]
    if user_id:
        candidates = [
            session
            for session in candidates
            if str(session.get("UserId") or "") == user_id
        ]

    session_id = str(config.get("session_id") or "")
    if session_id:
        return next(
            (session for session in candidates if str(session.get("Id") or "") == session_id),
            None,
        )

    device_name = str(config.get("device_name") or "").casefold()
    if device_name:
        return next(
            (
                session
                for session in candidates
                if str(session.get("DeviceName") or "").casefold() == device_name
                or str(session.get("Client") or "").casefold() == device_name
            ),
            None,
        )

    return None

def _jellyfin_status_payload(demo_mode: bool = False) -> Dict[str, Any]:
    config = _jellyfin_config()
    if not config["configured"]:
        if demo_mode:
            return _jellyfin_demo_status()
        return {
            "configured": False,
            "status": "unconfigured",
            "state_label": "not configured",
            "title": "Jellyfin not configured",
            "subtitle": "Set Jellyfin URL with token or username/password",
        }

    try:
        user_id = _jellyfin_user_id(config)
        scope = {
            "user_scoped": bool(user_id),
            "library_scoped": bool(config.get("library_id")),
            "global_access": bool(config.get("allow_global")),
        }
        if not config.get("session_id") and not config.get("device_name"):
            return {
                "configured": True,
                "status": "ready",
                "state_label": "local player ready",
                "title": "Jellyfin ready",
                "subtitle": "Pick a track below to play locally",
                "scope": scope,
            }

        sessions = _jellyfin_request_json(
            config,
            f"/Sessions?activeWithinSeconds={JELLYFIN_ACTIVE_WITHIN_SECONDS}",
        )
        if not isinstance(sessions, list):
            sessions = []
        session = _pick_jellyfin_session(sessions, config, user_id)
        if not session:
            return {
                "configured": True,
                "status": "ready",
                "state_label": "local player ready",
                "title": "Jellyfin ready",
                "subtitle": "No matching remote session; local playback is available",
                "scope": scope,
            }

        item = session.get("NowPlayingItem") or {}
        play_state = session.get("PlayState") or {}
        paused = play_state.get("IsPaused") is True
        position_seconds = _ticks_to_seconds(play_state.get("PositionTicks"))
        runtime_seconds = _ticks_to_seconds(item.get("RunTimeTicks"))
        progress = None
        if position_seconds is not None and runtime_seconds and runtime_seconds > 0:
            progress = (position_seconds / runtime_seconds) * 100.0
        formatted = _format_jellyfin_item(item) if item else {}
        status = "paused" if paused else "playing" if item else "ready"
        return {
            "configured": True,
            "status": status,
            "state_label": status,
            "title": formatted.get("name") or "Jellyfin ready",
            "subtitle": " · ".join(
                part for part in [formatted.get("artist"), formatted.get("album")] if part
            )
            or "Pick a track below to play locally",
            "client": session.get("Client"),
            "device_name": session.get("DeviceName"),
            "position_seconds": position_seconds,
            "runtime_seconds": runtime_seconds,
            "progress_percent": progress,
            "image_url": formatted.get("image_url"),
            "scope": scope,
        }
    except Exception as exc:
        return {
            "configured": True,
            "status": "error",
            "state_label": "error",
            "title": "Jellyfin unavailable",
            "subtitle": str(exc),
        }

def _jellyfin_search_payload(
    query: str = "",
    limit: int = 24,
    media_filter: str = "recent",
    demo_mode: bool = False,
) -> Dict[str, Any]:
    config = _jellyfin_config()
    if not config["configured"]:
        if demo_mode:
            payload = _jellyfin_demo_tracks()
            payload["filter"] = _jellyfin_media_filter(media_filter)
            return payload
        return {"configured": False, "items": [], "error": "Jellyfin is not configured"}

    try:
        from urllib.parse import urlencode

        selected_filter = _jellyfin_media_filter(media_filter)
        scope = _jellyfin_scope_params(config)
        params = {
            **scope,
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "Limit": str(max(1, min(int(limit), 60))),
            "SortBy": "DateCreated,SortName",
            "SortOrder": "Descending",
            "Fields": "PrimaryImageAspectRatio,MediaSources,AlbumArtist,Artists",
            "EnableImages": "true",
            "EnableUserData": "true" if scope.get("UserId") else "false",
        }
        query = (query or "").strip()
        if selected_filter == "favorites":
            params["IsFavorite"] = "true"
            params["SortBy"] = "SortName"
            params["SortOrder"] = "Ascending"
        elif selected_filter == "az":
            params["SortBy"] = "SortName"
            params["SortOrder"] = "Ascending"
        if query:
            params["SearchTerm"] = query
            params["SortBy"] = "SortName"
            params["SortOrder"] = "Ascending"

        data = _jellyfin_request_json(config, "/Items?" + urlencode(params))
        items = data.get("Items", []) if isinstance(data, dict) else []
        return {
            "configured": True,
            "filter": selected_filter,
            "items": [
                _format_jellyfin_item(item)
                for item in items
                if isinstance(item, dict)
                and item.get("Id")
                and (item.get("Type") == "Audio" or item.get("MediaType") == "Audio")
            ],
        }
    except Exception as exc:
        return {"configured": True, "items": [], "error": str(exc)}

def _jellyfin_proxy_audio(handler: Any, item_id: str) -> None:
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote, urlencode
    from urllib.request import Request

    config = _jellyfin_config()
    if not config["configured"]:
        handler.send_error(404, "Jellyfin is not configured")
        return
    try:
        safe_item_id = _safe_jellyfin_id(item_id)
        user_id = _jellyfin_validate_item_access(config, safe_item_id)
    except ValueError as exc:
        handler.send_error(400, str(exc))
        return
    except PermissionError as exc:
        handler.send_error(403, str(exc))
        return
    except Exception as exc:
        handler.send_error(502, str(exc))
        return

    params = {
        "static": "true",
        "deviceId": "open-mmi-dashboard",
        "allowAudioStreamCopy": "true",
        "enableAutoStreamCopy": "true",
    }
    if user_id:
        params["UserId"] = user_id
    url = f"{config['url']}/Audio/{quote(safe_item_id, safe='')}/stream?" + urlencode(params)
    headers = _jellyfin_auth_headers(config)
    headers["Accept"] = "audio/*,*/*"
    if handler.headers.get("Range"):
        headers["Range"] = handler.headers.get("Range")
    request = Request(url, headers=headers)
    try:
        with _jellyfin_urlopen(request, config, timeout=JELLYFIN_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            handler.send_response(status)
            for header in [
                "Content-Type",
                "Content-Length",
                "Content-Range",
                "Accept-Ranges",
                "Last-Modified",
                "ETag",
            ]:
                value = response.headers.get(header)
                if value:
                    handler.send_header(header, value)
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
            handler.end_headers()
            while True:
                chunk = response.read(JELLYFIN_AUDIO_CHUNK_BYTES)
                if not chunk:
                    break
                handler.wfile.write(chunk)
    except HTTPError as exc:
        handler.send_error(exc.code, f"Jellyfin stream HTTP {exc.code}")
    except (URLError, TimeoutError, BrokenPipeError) as exc:
        handler.send_error(502, str(exc))

def _jellyfin_proxy_image(handler: Any, item_id: str) -> None:
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote
    from urllib.request import Request

    config = _jellyfin_config()
    if not config["configured"]:
        handler.send_error(404, "Jellyfin is not configured")
        return
    try:
        safe_item_id = _safe_jellyfin_id(item_id)
        _jellyfin_validate_item_access(config, safe_item_id)
    except ValueError as exc:
        handler.send_error(400, str(exc))
        return
    except PermissionError as exc:
        handler.send_error(403, str(exc))
        return
    except Exception as exc:
        handler.send_error(502, str(exc))
        return

    image_url = (
        f"{config['url']}/Items/{quote(safe_item_id, safe='')}/Images/Primary"
        "?maxHeight=480&quality=84"
    )
    request = Request(image_url, headers=_jellyfin_auth_headers(config))
    try:
        with _jellyfin_urlopen(request, config, timeout=JELLYFIN_TIMEOUT_SECONDS) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "image/jpeg")
            handler.send_response(getattr(response, "status", 200))
            handler.send_header("Content-Type", content_type)
            handler.send_header("Cache-Control", "private, max-age=60")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
    except HTTPError as exc:
        handler.send_error(exc.code, f"Jellyfin image HTTP {exc.code}")
    except (URLError, TimeoutError) as exc:
        handler.send_error(502, str(exc))

# --- Open MMI Jellyfin local audio client end ---

# --- Open MMI Internet Radio source start ---
RADIO_BROWSER_DEFAULT_URL = "https://all.api.radio-browser.info"
RADIO_BROWSER_TIMEOUT_SECONDS = 6.0
RADIO_STREAM_TIMEOUT_SECONDS = 12.0
RADIO_STREAM_CHUNK_BYTES = 64 * 1024
RADIO_CATALOG_MAX_BYTES = 2 * 1024 * 1024
RADIO_USER_AGENT = "Open-MMI/0.1 (+https://github.com/open-mmi/open-mmi)"
RADIO_FILTERS = {
    "popular": ("clickcount", "Popular stations"),
    "votes": ("votes", "Top rated"),
    "recent": ("clicktimestamp", "Recently active"),
    # Favourites are stored and filtered in the browser; this value remains
    # accepted so stale requests degrade to a harmless catalogue ordering.
    "favorites": ("name", "Favourites"),
}
RADIO_FILTER_OPTION_LIMIT = 200


def _radio_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _radio_float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _radio_config() -> Dict[str, Any]:
    return {
        "url": os.getenv("OPEN_MMI_RADIO_BROWSER_URL", RADIO_BROWSER_DEFAULT_URL)
        .strip()
        .rstrip("/"),
        "user_agent": os.getenv("OPEN_MMI_RADIO_USER_AGENT", RADIO_USER_AGENT).strip()
        or RADIO_USER_AGENT,
        "catalog_timeout": _radio_float_env(
            "OPEN_MMI_RADIO_CATALOG_TIMEOUT", RADIO_BROWSER_TIMEOUT_SECONDS, 1.0, 30.0
        ),
        "stream_timeout": _radio_float_env(
            "OPEN_MMI_RADIO_STREAM_TIMEOUT", RADIO_STREAM_TIMEOUT_SECONDS, 2.0, 60.0
        ),
        "allow_private_streams": _radio_bool_env(
            "OPEN_MMI_RADIO_ALLOW_PRIVATE_STREAMS", False
        ),
    }


def _safe_radio_station_id(value: Any) -> str:
    import uuid

    text = str(value or "").strip()
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Invalid radio station ID") from exc
    return str(parsed)


def _radio_media_filter(value: Any) -> str:
    selected = str(value or "popular").strip().lower()
    return selected if selected in RADIO_FILTERS else "popular"


def _radio_country_code(value: Any) -> str:
    code = str(value or "").strip().upper()
    return code if len(code) == 2 and code.isalpha() else ""


def _radio_language_filter(value: Any) -> str:
    text = str(value or "").strip()
    if any(ord(character) < 32 for character in text):
        return ""
    return text[:64]


def _radio_station_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _radio_catalog_json(path: str, params: Dict[str, Any] | None = None) -> Any:
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    config = _radio_config()
    if not config["url"]:
        raise RuntimeError("Radio Browser URL is not configured")
    suffix = ""
    if params:
        suffix = "?" + urlencode(
            {key: value for key, value in params.items() if value is not None}
        )
    request = Request(
        f"{config['url']}{path}{suffix}",
        headers={
            "Accept": "application/json",
            "User-Agent": config["user_agent"],
        },
    )
    try:
        with urlopen(request, timeout=config["catalog_timeout"]) as response:
            body = response.read(RADIO_CATALOG_MAX_BYTES + 1)
            if len(body) > RADIO_CATALOG_MAX_BYTES:
                raise RuntimeError("Radio Browser response is too large")
            return json.loads(body.decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = exc.read(512).decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Radio Browser HTTP {exc.code}{suffix}") from exc
    except URLError as exc:
        raise RuntimeError(f"Radio Browser connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Radio Browser request timed out") from exc


def _format_radio_station(station: Dict[str, Any]) -> Dict[str, Any]:
    station_id = _safe_radio_station_id(station.get("stationuuid"))
    name = str(station.get("name") or "Unnamed station").strip()
    country = str(
        station.get("country") or station.get("countrycode") or "Internet radio"
    ).strip()
    country_code = _radio_country_code(station.get("countrycode"))
    language = str(station.get("language") or "").strip()
    language_codes = str(station.get("languagecodes") or "").strip()
    codec = str(station.get("codec") or "").strip().upper()
    try:
        bitrate = int(station.get("bitrate") or 0)
    except (TypeError, ValueError):
        bitrate = 0
    tags = [part.strip() for part in str(station.get("tags") or "").split(",")]
    tags = [part for part in tags if part][:2]
    details = []
    if tags:
        details.append(" / ".join(tags))
    if codec:
        details.append(codec)
    if bitrate > 0:
        details.append(f"{bitrate} kbps")
    return {
        "id": station_id,
        "source": "radio",
        "is_live": True,
        "name": name,
        "artist": country,
        "album": " · ".join(details) or "Live station",
        "duration_seconds": None,
        # Do not expose arbitrary third-party image or stream URLs to the browser.
        "image_url": None,
        "codec": codec or None,
        "bitrate": bitrate or None,
        "country": country,
        "country_code": country_code or None,
        "language": language or None,
        "language_codes": language_codes or None,
    }


def _radio_search_payload(
    query: str = "",
    limit: int = 60,
    media_filter: str = "popular",
    country_code: str = "",
    language: str = "",
) -> Dict[str, Any]:
    selected_filter = _radio_media_filter(media_filter)
    order, _label = RADIO_FILTERS[selected_filter]
    q = str(query or "").strip()
    try:
        bounded_limit = max(1, min(int(limit), 60))
    except (TypeError, ValueError):
        bounded_limit = 60
    params: Dict[str, Any] = {
        "hidebroken": "true",
        "limit": str(bounded_limit),
        "order": order,
        "reverse": "true",
    }
    if q:
        params["name"] = q
        params["nameExact"] = "false"
    selected_country = _radio_country_code(country_code)
    selected_language = _radio_language_filter(language)
    if selected_country:
        params["countrycode"] = selected_country
    if selected_language:
        params["language"] = selected_language
        params["languageExact"] = "false"
    try:
        data = _radio_catalog_json("/json/stations/search", params)
        stations = data if isinstance(data, list) else []
        items = []
        for station in stations:
            if not isinstance(station, dict) or not station.get("stationuuid"):
                continue
            try:
                items.append(_format_radio_station(station))
            except ValueError:
                continue
        return {
            "configured": True,
            "source": "radio",
            "filter": selected_filter,
            "country": selected_country or None,
            "language": selected_language or None,
            "items": items,
        }
    except Exception as exc:
        return {
            "configured": True,
            "source": "radio",
            "filter": selected_filter,
            "country": selected_country or None,
            "language": selected_language or None,
            "items": [],
            "error": str(exc),
        }


def _radio_filter_options_payload() -> Dict[str, Any]:
    params = {
        "hidebroken": "true",
        "order": "stationcount",
        "reverse": "true",
        "limit": str(RADIO_FILTER_OPTION_LIMIT),
    }
    countries_raw = _radio_catalog_json("/json/countrycodes", params)
    languages_raw = _radio_catalog_json("/json/languages", params)

    countries = []
    for entry in countries_raw if isinstance(countries_raw, list) else []:
        if not isinstance(entry, dict):
            continue
        code = _radio_country_code(entry.get("name"))
        if code:
            countries.append({
                "code": code,
                "station_count": _radio_station_count(entry.get("stationcount")),
            })

    languages = []
    seen_languages = set()
    for entry in languages_raw if isinstance(languages_raw, list) else []:
        if not isinstance(entry, dict):
            continue
        name = _radio_language_filter(entry.get("name"))
        if not name or name.casefold() in seen_languages:
            continue
        seen_languages.add(name.casefold())
        languages.append({
            "name": name,
            "code": str(entry.get("iso_639") or "").strip() or None,
            "station_count": _radio_station_count(entry.get("stationcount")),
        })

    return {
        "configured": True,
        "source": "radio",
        "countries": countries,
        "languages": languages,
    }


def _radio_status_payload() -> Dict[str, Any]:
    config = _radio_config()
    return {
        "configured": bool(config["url"]),
        "source": "radio",
        "status": "ready" if config["url"] else "unconfigured",
        "state_label": "radio ready" if config["url"] else "not configured",
        "title": "Internet Radio",
        "subtitle": (
            "Search or choose a station to play locally"
            if config["url"]
            else "Set OPEN_MMI_RADIO_BROWSER_URL"
        ),
    }


def _radio_station_by_uuid(station_id: str) -> Dict[str, Any]:
    from urllib.parse import quote

    safe_id = _safe_radio_station_id(station_id)
    data = _radio_catalog_json(f"/json/stations/byuuid/{quote(safe_id, safe='')}")
    stations = data if isinstance(data, list) else []
    for station in stations:
        if (
            isinstance(station, dict)
            and str(station.get("stationuuid") or "").lower() == safe_id
        ):
            return station
    raise LookupError("Radio station was not found")


def _radio_validate_stream_url(url: Any, allow_private: bool = False) -> str:
    import ipaddress
    import socket
    from urllib.parse import urlsplit

    text = str(url or "").strip()
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Radio stream must use HTTP or HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Radio stream URLs may not contain credentials")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Radio stream URL has no hostname")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValueError("Radio stream URL has an invalid port") from exc

    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RuntimeError(f"Could not resolve radio stream host: {exc}") from exc
    if not addresses:
        raise RuntimeError("Radio stream host did not resolve")

    for address in addresses:
        raw_ip = address[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError as exc:
            raise RuntimeError("Radio stream resolved to an invalid address") from exc
        if not allow_private and not ip.is_global:
            raise PermissionError(
                f"Radio stream resolved to a non-public address ({ip.compressed})"
            )
    return text


class _RadioRedirectHandler:
    """Factory wrapper so urllib redirect targets are validated before following."""

    @staticmethod
    def build(allow_private: bool):
        from urllib.request import HTTPRedirectHandler

        class SafeRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                _radio_validate_stream_url(newurl, allow_private=allow_private)
                return super().redirect_request(req, fp, code, msg, headers, newurl)

        return SafeRedirect()


def _radio_stream_url(station_id: str) -> str:
    from urllib.parse import quote

    safe_id = _safe_radio_station_id(station_id)
    station = _radio_station_by_uuid(safe_id)
    stream_url = str(station.get("url_resolved") or station.get("url") or "").strip()
    if not stream_url:
        raise LookupError("Radio station has no stream URL")
    config = _radio_config()
    validated = _radio_validate_stream_url(
        stream_url, allow_private=config["allow_private_streams"]
    )
    # Best effort: Radio Browser asks clients to count each station click.
    try:
        _radio_catalog_json(f"/json/url/{quote(safe_id, safe='')}")
    except Exception:
        pass
    return validated


def _radio_open_stream(url: str, range_header: str | None = None):
    from urllib.request import ProxyHandler, Request, build_opener

    config = _radio_config()
    validated = _radio_validate_stream_url(
        url, allow_private=config["allow_private_streams"]
    )
    headers = {
        "Accept": "audio/*,application/ogg,application/octet-stream;q=0.8,*/*;q=0.2",
        "User-Agent": config["user_agent"],
        "Icy-MetaData": "0",
    }
    if range_header:
        headers["Range"] = range_header
    opener = build_opener(
        ProxyHandler({}),
        _RadioRedirectHandler.build(config["allow_private_streams"]),
    )
    return opener.open(
        Request(validated, headers=headers), timeout=config["stream_timeout"]
    )


def _radio_proxy_audio(handler: Any, station_id: str) -> None:
    from urllib.error import HTTPError, URLError

    started = False
    try:
        stream_url = _radio_stream_url(station_id)
        with _radio_open_stream(stream_url, handler.headers.get("Range")) as response:
            content_type = str(
                response.headers.get("Content-Type") or "application/octet-stream"
            ).strip()
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type.startswith("text/") or media_type in {
                "application/json",
                "application/xml",
                "text/xml",
            }:
                raise RuntimeError(
                    f"Radio station returned unsupported content type {media_type}"
                )
            handler.send_response(getattr(response, "status", 200))
            started = True
            allowed_headers = [
                "Content-Type",
                "Content-Length",
                "Content-Range",
                "Accept-Ranges",
                "icy-name",
                "icy-genre",
                "icy-br",
                "icy-url",
            ]
            for header in allowed_headers:
                value = response.headers.get(header)
                if value:
                    safe_value = str(value).replace("\r", "").replace("\n", "")[:512]
                    handler.send_header(header, safe_value)
            handler.send_header("Cache-Control", "no-store")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
            handler.end_headers()
            while True:
                chunk = response.read(RADIO_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                handler.wfile.write(chunk)
    except ValueError as exc:
        if not started:
            handler.send_error(400, str(exc))
    except PermissionError as exc:
        if not started:
            handler.send_error(403, str(exc))
    except LookupError as exc:
        if not started:
            handler.send_error(404, str(exc))
    except HTTPError as exc:
        if not started:
            handler.send_error(exc.code, f"Radio stream HTTP {exc.code}")
    except (URLError, TimeoutError, RuntimeError, OSError) as exc:
        if not started:
            handler.send_error(502, str(exc))
    except (BrokenPipeError, ConnectionResetError):
        return
# --- Open MMI Internet Radio source end ---
class DashboardHandler(SimpleHTTPRequestHandler):
    status_path: Path = default_status_path()
    static_dir: Path = Path(__file__).with_name("static")
    demo_mode: bool = False
    demo_scenario: str = "drive"
    demo_started_at: float = time.time()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(self.static_dir), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("OPEN_MMI_WEB_LOG", "").strip():
            super().log_message(fmt, *args)

    def _send_json(self, body: Dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(body, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _current_payload(self, parsed_query: str) -> Dict[str, Any]:
        if self.demo_mode:
            query = parse_qs(parsed_query)
            scenario = query.get("demo", [self.demo_scenario])[0]
            return demo_status(scenario, self.demo_started_at)
        return load_status(self.status_path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)



        if parsed.path == "/api/jellyfin/status":
            self._send_json(_jellyfin_status_payload(self.demo_mode))
            return

        if parsed.path == "/api/jellyfin/search":
            query = parse_qs(parsed.query or "")
            q = query.get("q", [""])[0]
            media_filter = query.get("filter", ["recent"])[0]
            try:
                limit = int(query.get("limit", ["24"])[0])
            except (TypeError, ValueError):
                limit = 24
            self._send_json(
                _jellyfin_search_payload(q, limit, media_filter, self.demo_mode)
            )
            return

        if parsed.path.startswith("/api/jellyfin/stream/"):
            from urllib.parse import unquote
            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            _jellyfin_proxy_audio(self, item_id)
            return

        if parsed.path.startswith("/api/jellyfin/image/"):
            from urllib.parse import unquote

            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            _jellyfin_proxy_image(self, item_id)
            return

        if parsed.path == "/api/radio/status":
            self._send_json(_radio_status_payload())
            return
        if parsed.path == "/api/radio/options":
            try:
                self._send_json(_radio_filter_options_payload())
            except Exception as exc:
                self._send_json({"configured": True, "source": "radio", "error": str(exc)}, 502)
            return
        if parsed.path == "/api/radio/search":
            from urllib.parse import parse_qs

            query = parse_qs(parsed.query or "")
            q = query.get("q", [""])[0]
            media_filter = query.get("filter", ["popular"])[0]
            country_code = query.get("country", [""])[0]
            language = query.get("language", [""])[0]
            try:
                limit = int(query.get("limit", ["60"])[0])
            except (TypeError, ValueError):
                limit = 60
            self._send_json(
                _radio_search_payload(
                    q,
                    limit,
                    media_filter,
                    country_code=country_code,
                    language=language,
                )
            )
            return
        if parsed.path.startswith("/api/radio/stream/"):
            from urllib.parse import unquote

            station_id = unquote(parsed.path.rsplit("/", 1)[-1])
            _radio_proxy_audio(self, station_id)
            return

        if parsed.path == "/api/status":
            payload = self._current_payload(parsed.query)
            payload["health"] = health_for(payload)
            self._send_json(payload)
            return

        if parsed.path == "/api/health":
            payload = self._current_payload(parsed.query)
            self._send_json({"path": payload.get("path", str(self.status_path)), "health": health_for(payload)})
            return

        if parsed.path == "/":
            self.path = "/index.html"

        return super().do_GET()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Open MMI factory-style web dashboard")
    parser.add_argument("--host", default=os.getenv("OPEN_MMI_WEB_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OPEN_MMI_WEB_PORT", "8765")))
    parser.add_argument(
        "--path",
        type=Path,
        default=Path(os.getenv("OPEN_MMI_STATUS_PATH", str(default_status_path()))),
        help="status JSON path",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=os.getenv("OPEN_MMI_WEB_DEMO", "").strip().lower() in {"1", "true", "yes", "on"},
        help="serve a changing synthetic status snapshot instead of reading the status file",
    )
    parser.add_argument(
        "--demo-scenario",
        default=os.getenv("OPEN_MMI_WEB_DEMO_SCENARIO", "drive"),
        choices=("drive", "traffic", "doors-open", "reverse", "warnings", "stale"),
        help="demo scenario to use when --demo is enabled",
    )

    args = parser.parse_args()

    DashboardHandler.status_path = args.path
    DashboardHandler.demo_mode = args.demo
    DashboardHandler.demo_scenario = args.demo_scenario
    DashboardHandler.demo_started_at = time.time()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Open MMI web dashboard: http://{args.host}:{args.port}")
    if args.demo:
        print(f"Demo mode: {args.demo_scenario}")
    else:
        print(f"Status snapshot: {args.path}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
