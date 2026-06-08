#!/usr/bin/env python3
"""
Open MMI CAN Bus Daemon
"""

import time
import json
import sys
import os
import signal
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import can

from canbusd.dispatcher import dispatch
from canbusd.status_bus import publish as publish_status
from canbusd.status_rules import parse_status_rules, evaluate_status_rules

log_level = os.getenv("OPEN_MMI_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="[%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("canbusd")

BASE_DIR = Path(__file__).parent.parent
USER_CONFIG_DIR = Path(
    os.getenv("OPEN_MMI_CONFIG_DIR", str(Path.home() / ".config" / "open-mmi"))
)

VEHICLE = os.getenv("OPEN_MMI_VEHICLE", "seat_1p")
BINDINGS = os.getenv("OPEN_MMI_BINDINGS", "default")

IFACE = "can0"
RELOAD_INTERVAL = 60

ANY_VALUE_WILDCARD = "any"
DEFAULT_PRESENCE_TIMEOUT = 1000

_need_reload = False
_reload_lock = __import__("threading").Lock()


def _sig_hup(_signo: int, _frame: Any) -> None:
    global _need_reload
    with _reload_lock:
        _need_reload = True
    logger.info("SIGHUP received -> reload config")


signal.signal(signal.SIGHUP, _sig_hup)


def _resolve_vehicle_config_path() -> Path:
    explicit = os.getenv("OPEN_MMI_VEHICLE_CONFIG")
    if explicit:
        return Path(explicit).expanduser()

    user_path = USER_CONFIG_DIR / "vehicles" / VEHICLE / "config.json"
    if user_path.exists():
        return user_path

    return BASE_DIR / "vehicles" / VEHICLE / "config.json"


def _resolve_bindings_path() -> Path:
    explicit = os.getenv("OPEN_MMI_BINDINGS_FILE")
    if explicit:
        return Path(explicit).expanduser()

    user_path = USER_CONFIG_DIR / "bindings" / f"{BINDINGS}.json"
    if user_path.exists():
        return user_path

    return BASE_DIR / "bindings" / f"{BINDINGS}.json"


def _set_path(dst: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        return

    cur = dst
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _load_bindings() -> Dict[str, Dict[str, Any]]:
    path = _resolve_bindings_path()

    try:
        with open(path, "r") as f:
            bindings = json.load(f)
        logger.info(f"Loaded {len(bindings)} bindings from {path}")
        return bindings
    except Exception as e:
        logger.error(f"Bindings load failed from {path}: {e}")
        return {}


def _load_config(
    prev_rules=None,
    prev_mtime=None,
    prev_presence=None,
    prev_status_rules=None,
    prev_path=None,
):
    global _need_reload

    path = _resolve_vehicle_config_path()

    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        logger.error(f"Vehicle config not found: {path}")
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
            prev_path,
        )

    with _reload_lock:
        reload_requested = _need_reload

    path_changed = prev_path is not None and Path(prev_path) != path

    if prev_mtime == mtime and not reload_requested and not path_changed:
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
            path,
        )

    try:
        with open(path, "r") as f:
            cfg = json.load(f)

        rules: Dict[int, List[Tuple]] = {}
        presence = []

        for r in cfg.get("rules", []):
            cid = int(r["id"], 16) if isinstance(r["id"], str) else int(r["id"])
            b = int(r.get("byte", 0))
            v = r.get("value")

            if isinstance(v, str) and v.lower() == ANY_VALUE_WILDCARD:
                v = None
            elif v is not None:
                v = int(v)

            rules.setdefault(cid, []).append((b, v, r["event"]))

        for p in cfg.get("presence", []):
            presence.append({
                "id": int(p["id"], 16) if isinstance(p["id"], str) else int(p["id"]),
                "timeout_ms": int(p.get("timeout_ms", DEFAULT_PRESENCE_TIMEOUT)),
                "on_present": p.get("on_present"),
                "on_absent": p.get("on_absent"),
                "status_path": p.get("status_path", "vehicle.present"),
            })

        status_rules = parse_status_rules(cfg.get("status", []))

        with _reload_lock:
            _need_reload = False

        logger.info(
            "Loaded config from %s: %d CAN ids, %d presence rules, %d status CAN ids",
            path,
            len(rules),
            len(presence),
            len(status_rules),
        )

        return (rules, mtime, presence, status_rules, path)

    except Exception as e:
        logger.error(f"Config load failed from {path}: {e}")
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
            prev_path,
        )


def _publish_presence(
    presence_rule: Dict[str, Any],
    is_present: bool,
    bindings: Dict[str, Dict[str, Any]],
) -> None:
    cid = presence_rule["id"]
    event = presence_rule.get("on_present") if is_present else presence_rule.get("on_absent")

    update: Dict[str, Any] = {
        "presence": {
            f"0x{cid:X}": is_present,
        }
    }
    _set_path(update, presence_rule.get("status_path", "vehicle.present"), is_present)

    publish_status(update)

    if event:
        logger.info("Presence changed: 0x%X -> %s", cid, "present" if is_present else "absent")
        dispatch(event, bindings.get(event))


def _check_presence(
    presence: List[Dict[str, Any]],
    last_seen: Dict[int, float],
    present_state: Dict[int, Optional[bool]],
    bindings: Dict[str, Dict[str, Any]],
    now: float,
) -> None:
    for p in presence:
        cid = p["id"]
        timeout_s = p["timeout_ms"] / 1000.0

        is_present = cid in last_seen and (now - last_seen[cid]) <= timeout_s
        previous = present_state.get(cid)

        if previous is None or previous != is_present:
            present_state[cid] = is_present
            _publish_presence(p, is_present, bindings)


def main():
    rules, mtime, presence, status_rules, cfg_path = _load_config(None, None)
    bindings = _load_bindings()

    last_seen = {}
    last_codes = {}
    present_state = {}

    bus = None
    last_check = 0

    logger.info("canbusd starting")
    logger.info("vehicle=%s bindings=%s config_dir=%s", VEHICLE, BINDINGS, USER_CONFIG_DIR)

    while True:
        now = time.monotonic()

        if now - last_check > RELOAD_INTERVAL:
            rules, mtime, presence, status_rules, cfg_path = _load_config(
                rules,
                mtime,
                presence,
                status_rules,
                cfg_path,
            )
            bindings = _load_bindings()
            last_check = now

        if not Path(f"/sys/class/net/{IFACE}").exists():
            if bus:
                bus.shutdown()
                bus = None
            _check_presence(presence, last_seen, present_state, bindings, now)
            time.sleep(1)
            continue

        if bus is None:
            bus = can.interface.Bus(channel=IFACE, bustype="socketcan")

        msg = bus.recv(timeout=0.2)

        now = time.monotonic()

        if msg is None:
            _check_presence(presence, last_seen, present_state, bindings, now)
            continue

        last_seen[msg.arbitration_id] = now

        cid = msg.arbitration_id

        if cid in status_rules:
            status_update = evaluate_status_rules(
                status_rules[cid],
                msg.data,
                msg.dlc,
            )
            if status_update:
                publish_status(status_update)

        if cid in rules:
            for b, v, event in rules[cid]:
                if msg.dlc <= b:
                    continue

                code = msg.data[b]
                key = (cid, b, v)

                if v is None:
                    if last_codes.get(key) != code:
                        dispatch(event, bindings.get(event), [code])
                        last_codes[key] = code
                    continue

                if last_codes.get(key) == 0 and code == v:
                    dispatch(event, bindings.get(event))
                last_codes[key] = code

        _check_presence(presence, last_seen, present_state, bindings, now)


if __name__ == "__main__":
    main()
