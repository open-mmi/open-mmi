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
