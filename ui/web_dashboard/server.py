#!/usr/bin/env python3
"""Open MMI factory-style web dashboard.

Read-only local web UI for the persistent Open MMI status snapshot.
It does not subscribe to CAN directly and does not transmit/control the car.
"""

from __future__ import annotations

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






# Jellyfin media provider. Keep the fallback so
# ``python ui/web_dashboard/server.py`` continues to work when executed
# directly rather than as a package module.
try:
    from ui.web_dashboard import jellyfin as jellyfin_backend
except ModuleNotFoundError as exc:  # pragma: no cover - direct script fallback
    if exc.name not in {"ui", "ui.web_dashboard"}:
        raise
    import jellyfin as jellyfin_backend  # type: ignore[no-redef]

# Transitional private aliases preserve callers that imported Jellyfin helpers
# from ``server.py`` while routes and new tests use the provider directly.
JELLYFIN_TIMEOUT_SECONDS = jellyfin_backend.JELLYFIN_TIMEOUT_SECONDS
JELLYFIN_ACTIVE_WITHIN_SECONDS = jellyfin_backend.JELLYFIN_ACTIVE_WITHIN_SECONDS
JELLYFIN_AUDIO_CHUNK_BYTES = jellyfin_backend.JELLYFIN_AUDIO_CHUNK_BYTES
JELLYFIN_JSON_MAX_BYTES = jellyfin_backend.JELLYFIN_JSON_MAX_BYTES
JELLYFIN_IMAGE_MAX_BYTES = jellyfin_backend.JELLYFIN_IMAGE_MAX_BYTES
JELLYFIN_LOGIN_CACHE_SECONDS = jellyfin_backend.JELLYFIN_LOGIN_CACHE_SECONDS
JELLYFIN_IMAGE_CONTENT_TYPES = jellyfin_backend.JELLYFIN_IMAGE_CONTENT_TYPES
JELLYFIN_CLIENT_NAME = jellyfin_backend.JELLYFIN_CLIENT_NAME
JELLYFIN_DEVICE_ID = jellyfin_backend.JELLYFIN_DEVICE_ID
JELLYFIN_CLIENT_VERSION = jellyfin_backend.JELLYFIN_CLIENT_VERSION
_JELLYFIN_LOGIN_CACHE = jellyfin_backend._JELLYFIN_LOGIN_CACHE
_jellyfin_config = jellyfin_backend._jellyfin_config
_jellyfin_header_value = jellyfin_backend._jellyfin_header_value
_jellyfin_login_auth_header = jellyfin_backend._jellyfin_login_auth_header
_jellyfin_login_cache_key = jellyfin_backend._jellyfin_login_cache_key
_jellyfin_invalidate_login = jellyfin_backend._jellyfin_invalidate_login
_jellyfin_prune_login_cache = jellyfin_backend._jellyfin_prune_login_cache
_read_bounded_response = jellyfin_backend._read_bounded_response
_jellyfin_login = jellyfin_backend._jellyfin_login
_jellyfin_access_token = jellyfin_backend._jellyfin_access_token
_jellyfin_auth_headers = jellyfin_backend._jellyfin_auth_headers
_jellyfin_urlopen = jellyfin_backend._jellyfin_urlopen
_jellyfin_authenticated_urlopen = jellyfin_backend._jellyfin_authenticated_urlopen
_jellyfin_request_json = jellyfin_backend._jellyfin_request_json
_env_flag = jellyfin_backend._env_flag
_safe_jellyfin_id = jellyfin_backend._safe_jellyfin_id
_jellyfin_media_filter = jellyfin_backend._jellyfin_media_filter
_jellyfin_scope_params = jellyfin_backend._jellyfin_scope_params
_jellyfin_user_id = jellyfin_backend._jellyfin_user_id
_jellyfin_validate_item_access = jellyfin_backend._jellyfin_validate_item_access
_format_jellyfin_item = jellyfin_backend._format_jellyfin_item
_jellyfin_demo_tracks = jellyfin_backend._jellyfin_demo_tracks
_jellyfin_demo_status = jellyfin_backend._jellyfin_demo_status
_pick_jellyfin_session = jellyfin_backend._pick_jellyfin_session
_jellyfin_status_payload = jellyfin_backend._jellyfin_status_payload
_jellyfin_search_payload = jellyfin_backend._jellyfin_search_payload
_jellyfin_proxy_audio = jellyfin_backend._jellyfin_proxy_audio
_jellyfin_proxy_image = jellyfin_backend._jellyfin_proxy_image



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

# Bluetooth media provider. Keep the fallback so
# ``python ui/web_dashboard/server.py`` continues to work when executed
# directly rather than as a package module.
try:
    from ui.web_dashboard import bluetooth as bluetooth_backend
except ModuleNotFoundError as exc:  # pragma: no cover - direct script fallback
    if exc.name not in {"ui", "ui.web_dashboard"}:
        raise
    import bluetooth as bluetooth_backend  # type: ignore[no-redef]
except ImportError as exc:  # pragma: no cover - older installed package fallback
    if exc.name != "ui.web_dashboard":
        raise
    import bluetooth as bluetooth_backend  # type: ignore[no-redef]

# Transitional private aliases preserve callers that imported Bluetooth helpers
# from ``server.py`` while routes and new tests use the provider directly.
BLUETOOTH_BUSCTL_TIMEOUT_SECONDS = bluetooth_backend.BLUETOOTH_BUSCTL_TIMEOUT_SECONDS
BLUETOOTH_STATUS_CACHE_SECONDS = bluetooth_backend.BLUETOOTH_STATUS_CACHE_SECONDS
BLUETOOTH_MAX_BODY_BYTES = bluetooth_backend.BLUETOOTH_MAX_BODY_BYTES
_BLUETOOTH_ID_SECRET = bluetooth_backend._BLUETOOTH_ID_SECRET
_BLUETOOTH_ID_REGISTRY = bluetooth_backend._BLUETOOTH_ID_REGISTRY
_BLUETOOTH_ID_LOCK = bluetooth_backend._BLUETOOTH_ID_LOCK
_BLUETOOTH_CACHE_LOCK = bluetooth_backend._BLUETOOTH_CACHE_LOCK
_BLUETOOTH_STATUS_CACHE = bluetooth_backend._BLUETOOTH_STATUS_CACHE
_BLUETOOTH_ID_REGISTRY_MAX = bluetooth_backend._BLUETOOTH_ID_REGISTRY_MAX
_BLUETOOTH_ACTION_METHODS = bluetooth_backend._BLUETOOTH_ACTION_METHODS
_bluetooth_bool_env = bluetooth_backend._bluetooth_bool_env
_bluetooth_timeout = bluetooth_backend._bluetooth_timeout
_bluetooth_busctl_executable = bluetooth_backend._bluetooth_busctl_executable
_bluetooth_busctl = bluetooth_backend._bluetooth_busctl
_bluetooth_player_paths = bluetooth_backend._bluetooth_player_paths
_bluetooth_parse_scalar = bluetooth_backend._bluetooth_parse_scalar
_bluetooth_parse_variant_value = bluetooth_backend._bluetooth_parse_variant_value
_bluetooth_parse_track = bluetooth_backend._bluetooth_parse_track
_bluetooth_property = bluetooth_backend._bluetooth_property
_bluetooth_optional_property = bluetooth_backend._bluetooth_optional_property
_bluetooth_clean_text = bluetooth_backend._bluetooth_clean_text
_bluetooth_player_id = bluetooth_backend._bluetooth_player_id
_bluetooth_resolve_player_id = bluetooth_backend._bluetooth_resolve_player_id
_bluetooth_player_record = bluetooth_backend._bluetooth_player_record
_bluetooth_select_player = bluetooth_backend._bluetooth_select_player
_bluetooth_invalidate_cache = bluetooth_backend._bluetooth_invalidate_cache
_bluetooth_unavailable_payload = bluetooth_backend._bluetooth_unavailable_payload
_bluetooth_status_payload = bluetooth_backend._bluetooth_status_payload
_bluetooth_control = bluetooth_backend._bluetooth_control
_bluetooth_same_origin = bluetooth_backend._bluetooth_same_origin
_bluetooth_json_body = bluetooth_backend._bluetooth_json_body


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
        if not bluetooth_backend._bluetooth_same_origin(self):
            self._send_json({"ok": False, "error": "Cross-origin control request rejected"}, 403)
            return
        try:
            payload = bluetooth_backend._bluetooth_json_body(self)
            result = bluetooth_backend._bluetooth_control(payload.get("player_id"), payload.get("action"))
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
            self._send_json(jellyfin_backend._jellyfin_status_payload(self.demo_mode))
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
                jellyfin_backend._jellyfin_search_payload(q, limit, media_filter, self.demo_mode)
            )
            return

        if parsed.path.startswith("/api/jellyfin/stream/"):
            from urllib.parse import unquote
            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            jellyfin_backend._jellyfin_proxy_audio(self, item_id)
            return

        if parsed.path.startswith("/api/jellyfin/image/"):
            from urllib.parse import unquote

            item_id = unquote(parsed.path.rsplit("/", 1)[-1])
            jellyfin_backend._jellyfin_proxy_image(self, item_id)
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
            self._send_json(bluetooth_backend._bluetooth_status_payload())
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
