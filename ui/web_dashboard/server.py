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

    The real dashboard polls /api/status every 500 ms. By generating values from
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


def _jellyfin_config() -> Dict[str, Any]:
    url = os.getenv("OPEN_MMI_JELLYFIN_URL", "").strip().rstrip("/")
    token = os.getenv("OPEN_MMI_JELLYFIN_TOKEN", "").strip()
    session_id = os.getenv("OPEN_MMI_JELLYFIN_SESSION_ID", "").strip()
    device_name = os.getenv("OPEN_MMI_JELLYFIN_DEVICE", "").strip().lower()
    user_id = os.getenv("OPEN_MMI_JELLYFIN_USER_ID", "").strip()
    insecure_tls = os.getenv("OPEN_MMI_JELLYFIN_INSECURE_TLS", "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "configured": bool(url and token),
        "url": url,
        "token": token,
        "session_id": session_id,
        "device_name": device_name,
        "user_id": user_id,
        "insecure_tls": insecure_tls,
    }


def _jellyfin_auth_headers(config: Dict[str, Any]) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"MediaBrowser Token={config['token']}",
        "X-MediaBrowser-Token": config["token"],
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
        raise RuntimeError(f"Jellyfin HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Jellyfin connection failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("Jellyfin request timed out") from exc


def _jellyfin_user_id(config: Dict[str, Any]) -> str | None:
    if config.get("user_id"):
        return str(config["user_id"])
    try:
        user = _jellyfin_request_json(config, "/Users/Me")
        if isinstance(user, dict) and user.get("Id"):
            return str(user["Id"])
    except Exception:
        # API keys generated outside a user session may not be associated with /Users/Me.
        # /Items can still work with an API key, so do not fail just because this lookup fails.
        return None
    return None


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


def _pick_jellyfin_session(sessions: list[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any] | None:
    if config.get("session_id"):
        for session in sessions:
            if str(session.get("Id", "")) == config["session_id"]:
                return session

    if config.get("device_name"):
        for session in sessions:
            device = str(session.get("DeviceName", "")).lower()
            client = str(session.get("Client", "")).lower()
            if config["device_name"] in device or config["device_name"] in client:
                return session

    for session in sessions:
        if session.get("NowPlayingItem"):
            return session

    return sessions[0] if sessions else None


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
            "subtitle": "Set OPEN_MMI_JELLYFIN_URL and OPEN_MMI_JELLYFIN_TOKEN",
        }

    try:
        sessions = _jellyfin_request_json(config, f"/Sessions?activeWithinSeconds={JELLYFIN_ACTIVE_WITHIN_SECONDS}")
        if not isinstance(sessions, list):
            sessions = []
        session = _pick_jellyfin_session(sessions, config)
        if not session:
            return {
                "configured": True,
                "status": "ready",
                "state_label": "ready",
                "server_url": config["url"],
                "server_name": config["url"].replace("https://", "").replace("http://", ""),
                "title": "Jellyfin ready",
                "subtitle": "Pick a track below to play locally",
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
            "server_url": config["url"],
            "server_name": config["url"].replace("https://", "").replace("http://", ""),
            "title": formatted.get("name") or "Jellyfin ready",
            "subtitle": " · ".join(part for part in [formatted.get("artist"), formatted.get("album")] if part) or "Pick a track below to play locally",
            "client": session.get("Client"),
            "device_name": session.get("DeviceName"),
            "user_name": session.get("UserName"),
            "position_seconds": position_seconds,
            "runtime_seconds": runtime_seconds,
            "progress_percent": progress,
            "image_url": formatted.get("image_url"),
        }
    except Exception as exc:
        return {
            "configured": True,
            "status": "error",
            "state_label": "error",
            "server_url": config["url"],
            "server_name": config["url"],
            "title": "Jellyfin unavailable",
            "subtitle": str(exc),
        }


def _jellyfin_search_payload(query: str = "", limit: int = 24, demo_mode: bool = False) -> Dict[str, Any]:
    config = _jellyfin_config()
    if not config["configured"]:
        if demo_mode:
            return _jellyfin_demo_tracks()
        return {"configured": False, "items": [], "error": "Jellyfin is not configured"}

    try:
        from urllib.parse import urlencode

        user_id = _jellyfin_user_id(config)
        params = {
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "Limit": str(max(1, min(int(limit), 60))),
            "SortBy": "DateCreated,SortName",
            "SortOrder": "Descending",
            "Fields": "PrimaryImageAspectRatio,MediaSources,AlbumArtist,Artists",
            "EnableImages": "true",
        }
        if user_id:
            params["UserId"] = user_id
        query = (query or "").strip()
        if query:
            params["SearchTerm"] = query
            params["SortBy"] = "SortName"
            params["SortOrder"] = "Ascending"
        data = _jellyfin_request_json(config, "/Items?" + urlencode(params))
        items = data.get("Items", []) if isinstance(data, dict) else []
        return {
            "configured": True,
            "items": [_format_jellyfin_item(item) for item in items if isinstance(item, dict) and item.get("Id")],
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

    item_id = quote(item_id.strip(), safe="")
    params = {
        "static": "true",
        "deviceId": "open-mmi-dashboard",
        "allowAudioStreamCopy": "true",
        "enableAutoStreamCopy": "true",
    }
    user_id = _jellyfin_user_id(config)
    if user_id:
        params["UserId"] = user_id

    url = f"{config['url']}/Audio/{item_id}/stream?" + urlencode(params)
    headers = _jellyfin_auth_headers(config)
    headers["Accept"] = "audio/*,*/*"
    if handler.headers.get("Range"):
        headers["Range"] = handler.headers.get("Range")

    request = Request(url, headers=headers)
    try:
        with _jellyfin_urlopen(request, config, timeout=JELLYFIN_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            handler.send_response(status)
            for header in ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag"]:
                value = response.headers.get(header)
                if value:
                    handler.send_header(header, value)
            handler.send_header("Cache-Control", "no-store")
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
# --- Open MMI Jellyfin local audio client end ---


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
            from urllib.parse import parse_qs
            query = parse_qs(parsed.query or "")
            q = query.get("q", [""])[0]
            try:
                limit = int(query.get("limit", ["24"])[0])
            except (TypeError, ValueError):
                limit = 24
            self._send_json(_jellyfin_search_payload(q, limit, self.demo_mode))
            return

        if parsed.path.startswith("/api/jellyfin/stream/"):
            from urllib.parse import unquote
            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            _jellyfin_proxy_audio(self, item_id)
            return

        if parsed.path.startswith("/api/jellyfin/image/"):
            config = _jellyfin_config()
            if not config["configured"]:
                self.send_error(404, "Jellyfin is not configured")
                return
            item_id = parsed.path.rsplit("/", 1)[-1]
            from urllib.error import HTTPError, URLError
            from urllib.request import Request
            image_url = f"{config['url']}/Items/{item_id}/Images/Primary?maxHeight=480&quality=84"
            request = Request(image_url, headers={"Authorization": f"MediaBrowser Token={config['token']}", "X-MediaBrowser-Token": config["token"]})
            try:
                with _jellyfin_urlopen(request, config, timeout=JELLYFIN_TIMEOUT_SECONDS) as response:
                    body = response.read()
                    content_type = response.headers.get("Content-Type", "image/jpeg")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "private, max-age=60")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (HTTPError, URLError, TimeoutError) as exc:
                self.send_error(502, str(exc))
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
