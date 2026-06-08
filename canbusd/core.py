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

VEHICLE = os.getenv("OPEN_MMI_VEHICLE", "seat_1p")
BINDINGS = os.getenv("OPEN_MMI_BINDINGS", "default")

CFG_PATH = BASE_DIR / "vehicles" / VEHICLE / "config.json"
BINDINGS_PATH = BASE_DIR / "bindings" / f"{BINDINGS}.json"

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


def _load_bindings() -> Dict[str, Dict[str, Any]]:
    try:
        with open(BINDINGS_PATH, "r") as f:
            bindings = json.load(f)
        logger.info(f"Loaded {len(bindings)} bindings")
        return bindings
    except Exception as e:
        logger.error(f"Bindings load failed: {e}")
        return {}


def _load_config(
    prev_rules=None,
    prev_mtime=None,
    prev_presence=None,
    prev_status_rules=None,
):
    global _need_reload

    try:
        mtime = CFG_PATH.stat().st_mtime
    except FileNotFoundError:
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
        )

    with _reload_lock:
        reload_requested = _need_reload

    if prev_mtime == mtime and not reload_requested:
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
        )

    try:
        cfg = json.load(open(CFG_PATH))

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
            })

        status_rules = parse_status_rules(cfg.get("status", []))

        with _reload_lock:
            _need_reload = False

        logger.info(
            "Loaded config: %d CAN ids, %d presence rules, %d status CAN ids",
            len(rules),
            len(presence),
            len(status_rules),
        )

        return (rules, mtime, presence, status_rules)

    except Exception as e:
        logger.error(f"Config load failed: {e}")
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
        )


def main():
    rules, mtime, presence, status_rules = _load_config(None, None)
    bindings = _load_bindings()

    last_seen = {}
    last_codes = {}
    present_state = {}

    bus = None
    last_check = 0

    logger.info("canbusd starting")

    while True:
        now = time.monotonic()

        if now - last_check > RELOAD_INTERVAL:
            rules, mtime, presence, status_rules = _load_config(
                rules,
                mtime,
                presence,
                status_rules,
            )
            bindings = _load_bindings()
            last_check = now

        if not Path(f"/sys/class/net/{IFACE}").exists():
            if bus:
                bus.shutdown()
                bus = None
            time.sleep(1)
            continue

        if bus is None:
            bus = can.interface.Bus(channel=IFACE, bustype="socketcan")

        msg = bus.recv(timeout=0.2)
        if msg is None:
            continue

        now = time.monotonic()
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


if __name__ == "__main__":
    main()