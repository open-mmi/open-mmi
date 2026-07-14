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
    recirculation_active = 45.0 < (t % 90.0) < 58.0
    climate = {
        "outside_temp_regulation_c": round(outside_c, 1),
        "outside_temp_unfiltered_c": round(outside_c + 0.3 * _wave(t, 8.0), 1),
        "blower_load_percent": round(blower_pct, 1),
        "rear_window_heater_requested": 20.0 < (t % 80.0) < 35.0,
        "recirculation_active": recirculation_active,
        # Compatibility alias for dashboard/status consumers from the alpha
        # schema. Remove only at a documented status-schema boundary.
        "front_demist_air_request": recirculation_active,
        "compressor_active": _wave(t, 30.0) > -0.35,
        "air_intake": "Recirc" if recirculation_active else "Normal",
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
JELLYFIN_JSON_MAX_BYTES = 4 * 1024 * 1024
JELLYFIN_IMAGE_MAX_BYTES = 8 * 1024 * 1024
JELLYFIN_LOGIN_CACHE_SECONDS = 15 * 60
JELLYFIN_IMAGE_CONTENT_TYPES = {
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}
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


def _jellyfin_login_cache_key(config: Dict[str, Any]) -> str:
    import hashlib

    device_id = os.getenv("OPEN_MMI_JELLYFIN_DEVICE_ID", "").strip() or JELLYFIN_DEVICE_ID
    material = "\0".join(
        [
            str(config.get("url") or ""),
            str(config.get("username") or ""),
            str(config.get("password") or ""),
            device_id,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _jellyfin_invalidate_login(config: Dict[str, Any]) -> None:
    _JELLYFIN_LOGIN_CACHE.pop(_jellyfin_login_cache_key(config), None)
    if config.get("auth_mode") == "username":
        config["token"] = ""


def _jellyfin_prune_login_cache(now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    for key, cached in list(_JELLYFIN_LOGIN_CACHE.items()):
        cached_at = float(cached.get("cached_at") or 0.0)
        if current - cached_at >= JELLYFIN_LOGIN_CACHE_SECONDS:
            _JELLYFIN_LOGIN_CACHE.pop(key, None)


def _read_bounded_response(response: Any, maximum: int, label: str) -> bytes:
    raw_length = response.headers.get("Content-Length")
    if raw_length:
        try:
            declared = int(raw_length)
        except (TypeError, ValueError):
            declared = -1
        if declared > maximum:
            raise RuntimeError(f"{label} exceeded the {maximum}-byte limit")

    chunks = []
    total = 0
    while total <= maximum:
        chunk = response.read(min(64 * 1024, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > maximum:
        raise RuntimeError(f"{label} exceeded the {maximum}-byte limit")
    return b"".join(chunks)


def _jellyfin_login(config: Dict[str, Any]) -> Dict[str, Any]:
    from urllib.error import HTTPError, URLError
    from urllib.request import Request

    if not config.get("username_configured"):
        raise RuntimeError("Jellyfin username/password is not configured")

    cache_key = _jellyfin_login_cache_key(config)
    now = time.monotonic()
    _jellyfin_prune_login_cache(now)
    cached = _JELLYFIN_LOGIN_CACHE.get(cache_key)
    if cached and cached.get("token"):
        cached_at = float(cached.get("cached_at") or 0.0)
        if now - cached_at < JELLYFIN_LOGIN_CACHE_SECONDS:
            return {
                key: value for key, value in cached.items() if key != "cached_at"
            }
        _JELLYFIN_LOGIN_CACHE.pop(cache_key, None)

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
            raw = _read_bounded_response(response, JELLYFIN_JSON_MAX_BYTES, "Jellyfin login response")
            payload = json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Jellyfin login HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Jellyfin login connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Jellyfin login timed out") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Jellyfin login returned invalid JSON") from exc

    if not isinstance(payload, dict) or not payload.get("AccessToken"):
        raise RuntimeError("Jellyfin login did not return an access token")

    user = payload.get("User") if isinstance(payload.get("User"), dict) else {}
    login = {
        "token": str(payload["AccessToken"]),
        "user_id": str(user.get("Id") or ""),
        "user_name": str(user.get("Name") or config.get("username") or ""),
    }
    _JELLYFIN_LOGIN_CACHE[cache_key] = {
        **login,
        "cached_at": now,
    }
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


def _jellyfin_authenticated_urlopen(
    config: Dict[str, Any],
    url: str,
    *,
    headers: Dict[str, str] | None = None,
    timeout: float = JELLYFIN_TIMEOUT_SECONDS,
):
    from urllib.error import HTTPError
    from urllib.request import Request

    base_headers = dict(headers or {})
    for attempt in range(2):
        request_headers = _jellyfin_auth_headers(config)
        request_headers.update(base_headers)
        request = Request(url, headers=request_headers)
        try:
            return _jellyfin_urlopen(request, config, timeout=timeout)
        except HTTPError as exc:
            should_retry = (
                attempt == 0
                and exc.code in {401, 403}
                and config.get("auth_mode") == "username"
            )
            if not should_retry:
                raise
            try:
                exc.close()
            except Exception:
                pass
            _jellyfin_invalidate_login(config)
    raise RuntimeError("Jellyfin authentication retry failed")


def _jellyfin_request_json(config: Dict[str, Any], path: str) -> Any:
    from urllib.error import HTTPError, URLError

    url = f"{config['url']}{path}"
    try:
        with _jellyfin_authenticated_urlopen(config, url) as response:
            raw = _read_bounded_response(response, JELLYFIN_JSON_MAX_BYTES, "Jellyfin JSON response")
            return json.loads(raw.decode("utf-8"))
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
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Jellyfin returned invalid JSON") from exc

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
    headers = {"Accept": "audio/*,*/*"}
    if handler.headers.get("Range"):
        headers["Range"] = handler.headers.get("Range")
    try:
        with _jellyfin_authenticated_urlopen(config, url, headers=headers) as response:
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
    try:
        with _jellyfin_authenticated_urlopen(
            config,
            image_url,
            headers={
                "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif"
            },
        ) as response:
            content_type = str(response.headers.get("Content-Type") or "").strip()
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type not in JELLYFIN_IMAGE_CONTENT_TYPES:
                raise RuntimeError(f"Jellyfin returned unsupported image type {media_type or 'unknown'}")
            body = _read_bounded_response(response, JELLYFIN_IMAGE_MAX_BYTES, "Jellyfin image")
            handler.send_response(getattr(response, "status", 200))
            handler.send_header("Content-Type", media_type)
            handler.send_header("Cache-Control", "private, max-age=60")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("Cross-Origin-Resource-Policy", "same-origin")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
    except HTTPError as exc:
        handler.send_error(exc.code, f"Jellyfin image HTTP {exc.code}")
    except (URLError, TimeoutError, RuntimeError) as exc:
        handler.send_error(502, str(exc))

# --- Open MMI Jellyfin local audio client end ---

# Radio is a separate provider module.  The absolute import supports package and
# spec-based test loading; the local fallback keeps ``python server.py`` working.
try:
    from ui.web_dashboard import radio as radio_backend
except ModuleNotFoundError as exc:  # pragma: no cover - direct script fallback
    if exc.name not in {"ui", "ui.web_dashboard"}:
        raise
    import radio as radio_backend  # type: ignore[no-redef]

# Transitional private aliases preserve callers that imported these helpers from
# server.py while routes and new tests use the provider module directly.
_safe_radio_station_id = radio_backend._safe_radio_station_id
_radio_validate_stream_url = radio_backend._radio_validate_stream_url
_radio_resolve_stream_target = radio_backend._radio_resolve_stream_target
_radio_connection = radio_backend._radio_connection
_radio_config = radio_backend._radio_config
_radio_catalog_json = radio_backend._radio_catalog_json
_radio_search_payload = radio_backend._radio_search_payload
_radio_filter_options_payload = radio_backend._radio_filter_options_payload
_radio_status_payload = radio_backend._radio_status_payload
_radio_station_by_uuid = radio_backend._radio_station_by_uuid
_radio_stream_url = radio_backend._radio_stream_url
_radio_open_stream = radio_backend._radio_open_stream
_radio_proxy_audio = radio_backend._radio_proxy_audio

# USB media provider. Keep the fallback so ``python ui/web_dashboard/server.py``
# continues to work when executed directly rather than as a package module.
try:
    from ui.web_dashboard import usb as usb_backend
except ModuleNotFoundError:  # pragma: no cover - direct-script compatibility
    import usb as usb_backend  # type: ignore[no-redef]

# Temporary private aliases preserve compatibility for callers that imported
# USB helpers from ``server.py`` before the provider extraction.
USB_AUDIO_EXTENSIONS = usb_backend.USB_AUDIO_EXTENSIONS
USB_ARTWORK_EXTENSIONS = usb_backend.USB_ARTWORK_EXTENSIONS
USB_ARTWORK_NAMES = usb_backend.USB_ARTWORK_NAMES
USB_STREAM_CHUNK_BYTES = usb_backend.USB_STREAM_CHUNK_BYTES
USB_MAX_ROOTS = usb_backend.USB_MAX_ROOTS
USB_MAX_RESULTS = usb_backend.USB_MAX_RESULTS
USB_DEFAULT_SCAN_LIMIT = usb_backend.USB_DEFAULT_SCAN_LIMIT
USB_ID_REGISTRY_MAX = usb_backend.USB_ID_REGISTRY_MAX
_USB_ID_SECRET = usb_backend._USB_ID_SECRET
_USB_ID_REGISTRY = usb_backend._USB_ID_REGISTRY
_USB_ID_LOCK = usb_backend._USB_ID_LOCK
_usb_bool_env = usb_backend._usb_bool_env
_usb_int_env = usb_backend._usb_int_env
_usb_split_paths = usb_backend._usb_split_paths
_usb_discovery_bases = usb_backend._usb_discovery_bases
_usb_root_id = usb_backend._usb_root_id
_usb_safe_label = usb_backend._usb_safe_label
_usb_candidate_root = usb_backend._usb_candidate_root
_usb_roots = usb_backend._usb_roots
_usb_normalize_relative = usb_backend._usb_normalize_relative
_usb_encode_id = usb_backend._usb_encode_id
_usb_decode_id = usb_backend._usb_decode_id
_usb_root_map = usb_backend._usb_root_map
_usb_reject_symlink_components = usb_backend._usb_reject_symlink_components
_usb_resolve_id = usb_backend._usb_resolve_id
_usb_include_entry = usb_backend._usb_include_entry
_usb_artwork_path = usb_backend._usb_artwork_path
_usb_track_metadata = usb_backend._usb_track_metadata
_usb_format_audio = usb_backend._usb_format_audio
_usb_format_directory = usb_backend._usb_format_directory
_usb_format_root = usb_backend._usb_format_root
_usb_sort_items = usb_backend._usb_sort_items
_usb_search_terms = usb_backend._usb_search_terms
_usb_search_matches = usb_backend._usb_search_matches
_usb_scan_directory = usb_backend._usb_scan_directory
_usb_breadcrumbs = usb_backend._usb_breadcrumbs
_usb_browse_payload = usb_backend._usb_browse_payload
_usb_status_payload = usb_backend._usb_status_payload
_usb_parse_range = usb_backend._usb_parse_range
_usb_content_type = usb_backend._usb_content_type
_usb_open_file = usb_backend._usb_open_file
_usb_send_file = usb_backend._usb_send_file

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


    # --- Open MMI Bluetooth media POST route start ---
    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/bluetooth/control":
            self.send_error(404)
            return
        if not _bluetooth_same_origin(self):
            self._send_json({"ok": False, "error": "Cross-origin control request rejected"}, 403)
            return
        try:
            payload = _bluetooth_json_body(self)
            result = _bluetooth_control(payload.get("player_id"), payload.get("action"))
            self._send_json(result)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 400)
        except FileNotFoundError as exc:
            self._send_json({"ok": False, "error": str(exc)}, 409)
        except (RuntimeError, TimeoutError, OSError):
            self._send_json({"ok": False, "error": "Bluetooth media control failed"}, 502)
    # --- Open MMI Bluetooth media POST route end ---

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
            self._send_json(radio_backend._radio_status_payload())
            return
        if parsed.path == "/api/radio/options":
            try:
                self._send_json(radio_backend._radio_filter_options_payload())
            except Exception as exc:
                self._send_json({"configured": True, "source": "radio", "error": str(exc)}, 502)
            return
        if parsed.path == "/api/radio/search":
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
                radio_backend._radio_search_payload(
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
            radio_backend._radio_proxy_audio(self, station_id)
            return


        # --- Open MMI USB media routes start ---
        if parsed.path == "/api/usb/status":
            self._send_json(usb_backend._usb_status_payload())
            return
        if parsed.path == "/api/usb/browse":
            query = parse_qs(parsed.query or "")
            directory_id = query.get("dir", [""])[0]
            q = query.get("q", [""])[0]
            media_filter = query.get("filter", ["browse"])[0]
            try:
                limit = int(query.get("limit", ["60"])[0])
                payload = usb_backend._usb_browse_payload(directory_id, q, limit, media_filter)
                self._send_json(payload)
            except ValueError as exc:
                self._send_json({"configured": True, "source": "usb", "items": [], "error": str(exc)}, 400)
            except PermissionError as exc:
                self._send_json({"configured": True, "source": "usb", "items": [], "error": str(exc)}, 403)
            except FileNotFoundError as exc:
                self._send_json({"configured": True, "source": "usb", "items": [], "error": str(exc)}, 404)
            except Exception:
                self._send_json({"configured": True, "source": "usb", "items": [], "error": "USB media browse failed"}, 500)
            return
        if parsed.path.startswith("/api/usb/stream/"):
            from urllib.parse import unquote

            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            usb_backend._usb_send_file(self, item_id)
            return
        if parsed.path.startswith("/api/usb/art/"):
            from urllib.parse import unquote

            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            usb_backend._usb_send_file(self, item_id, artwork=True)
            return
        # --- Open MMI USB media routes end ---

        # --- Open MMI Bluetooth media GET route start ---
        if parsed.path == "/api/bluetooth/status":
            self._send_json(_bluetooth_status_payload())
            return
        # --- Open MMI Bluetooth media GET route end ---
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
