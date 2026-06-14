#!/usr/bin/env python3
"""Open MMI CAN Bus Daemon."""

import json
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import can

from canbusd.can_runtime import CanRuntimeConfig, item_matches_bus, resolve_can_runtime
from canbusd.dispatcher import dispatch
from canbusd.status_bus import publish as publish_status
from canbusd.status_rules import evaluate_status_rules, parse_status_rules


log_level = os.getenv("OPEN_MMI_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="[%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("canbusd")


BASE_DIR = Path(__file__).parent.parent
USER_CONFIG_DIR = Path(
    os.getenv("OPEN_MMI_CONFIG_DIR", str(Path.home() / ".config" / "open-mmi"))
)

VEHICLE = os.getenv("OPEN_MMI_VEHICLE", "seat_1p")
BINDINGS = os.getenv("OPEN_MMI_BINDINGS", "default")

DEFAULT_CAN_BUS = "comfort"
DEFAULT_CAN_INTERFACE = "can0"

CAN_RUNTIME = resolve_can_runtime(
    {},
    os.environ,
    default_bus=DEFAULT_CAN_BUS,
    default_interface=DEFAULT_CAN_INTERFACE,
)
CAN_BUS = CAN_RUNTIME.name
IFACE = CAN_RUNTIME.interface

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

        logger.info("Loaded %d bindings from %s", len(bindings), path)
        return bindings

    except Exception as e:
        logger.error("Bindings load failed from %s: %s", path, e)
        return {}


def _filter_items_for_bus(
    items: List[Dict[str, Any]],
    runtime: CanRuntimeConfig,
) -> List[Dict[str, Any]]:
    return [
        item
        for item in items
        if item_matches_bus(item, runtime.name, runtime.default_bus)
    ]


def _load_config(
    prev_rules=None,
    prev_mtime=None,
    prev_presence=None,
    prev_status_rules=None,
    prev_path=None,
    prev_runtime=None,
):
    global _need_reload, CAN_RUNTIME, CAN_BUS, IFACE

    path = _resolve_vehicle_config_path()

    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        logger.error("Vehicle config not found: %s", path)
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
            prev_path,
            prev_runtime or CAN_RUNTIME,
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
            prev_runtime or CAN_RUNTIME,
        )

    try:
        with open(path, "r") as f:
            cfg = json.load(f)

        runtime = resolve_can_runtime(
            cfg,
            os.environ,
            default_bus=DEFAULT_CAN_BUS,
            default_interface=DEFAULT_CAN_INTERFACE,
        )

        all_rule_items = cfg.get("rules", [])
        rule_items = _filter_items_for_bus(all_rule_items, runtime)

        rules: Dict[int, List[Tuple[int, Optional[int], str]]] = {}
        for r in rule_items:
            cid = int(r["id"], 16) if isinstance(r["id"], str) else int(r["id"])
            b = int(r.get("byte", 0))
            v = r.get("value")

            if isinstance(v, str) and v.lower() == ANY_VALUE_WILDCARD:
                v = None
            elif v is not None:
                v = int(v)

            rules.setdefault(cid, []).append((b, v, r["event"]))

        all_presence_items = cfg.get("presence", [])
        presence_items = _filter_items_for_bus(all_presence_items, runtime)

        presence = []
        for p in presence_items:
            presence.append(
                {
                    "id": int(p["id"], 16) if isinstance(p["id"], str) else int(p["id"]),
                    "timeout_ms": int(p.get("timeout_ms", DEFAULT_PRESENCE_TIMEOUT)),
                    "on_present": p.get("on_present"),
                    "on_absent": p.get("on_absent"),
                    "status_path": p.get("status_path", "vehicle.present"),
                }
            )

        all_status_items = cfg.get("status", [])
        status_items = _filter_items_for_bus(all_status_items, runtime)
        status_rules = parse_status_rules(status_items)

        CAN_RUNTIME = runtime
        CAN_BUS = runtime.name
        IFACE = runtime.interface

        if runtime.profile_has_buses and not runtime.declared:
            logger.warning(
                "CAN bus '%s' is not declared in profile metadata; using interface '%s'",
                runtime.name,
                runtime.interface,
            )

        if runtime.bring_up:
            logger.warning(
                "CAN bus '%s' has bring_up=true metadata, but daemon-side interface "
                "configuration is intentionally not implemented",
                runtime.name,
            )

        with _reload_lock:
            _need_reload = False

        logger.info(
            "Loaded config from %s: bus=%s interface=%s interface_source=%s "
            "bitrate=%s provisioning=%s capture_point=%s rules=%d/%d "
            "presence=%d/%d status CAN ids=%d",
            path,
            runtime.name,
            runtime.interface,
            runtime.interface_source,
            runtime.bitrate,
            runtime.provisioning,
            runtime.capture_point,
            len(rule_items),
            len(all_rule_items),
            len(presence_items),
            len(all_presence_items),
            len(status_rules),
        )

        return (rules, mtime, presence, status_rules, path, runtime)

    except Exception as e:
        logger.error("Config load failed from %s: %s", path, e)
        return (
            prev_rules,
            prev_mtime,
            prev_presence or [],
            prev_status_rules or {},
            prev_path,
            prev_runtime or CAN_RUNTIME,
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
        logger.info(
            "Presence changed: 0x%X -> %s",
            cid,
            "present" if is_present else "absent",
        )
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
    rules, mtime, presence, status_rules, cfg_path, runtime = _load_config(None, None)
    bindings = _load_bindings()

    last_seen = {}
    last_codes = {}
    present_state = {}
    bus = None
    opened_interface: Optional[str] = None
    last_check = 0

    logger.info("canbusd starting")
    logger.info("vehicle=%s bindings=%s config_dir=%s", VEHICLE, BINDINGS, USER_CONFIG_DIR)

    while True:
        now = time.monotonic()

        if now - last_check > RELOAD_INTERVAL:
            rules, mtime, presence, status_rules, cfg_path, runtime = _load_config(
                rules,
                mtime,
                presence,
                status_rules,
                cfg_path,
                runtime,
            )
            bindings = _load_bindings()
            last_check = now

        if opened_interface != IFACE:
            if bus:
                bus.shutdown()
                bus = None

            opened_interface = IFACE
            last_seen.clear()
            present_state.clear()

        if not Path(f"/sys/class/net/{IFACE}").exists():
            if bus:
                bus.shutdown()
                bus = None

            _check_presence(presence, last_seen, present_state, bindings, now)
            time.sleep(1)
            continue

        if bus is None:
            logger.info("Opening CAN bus '%s' on interface '%s'", CAN_BUS, IFACE)
            bus = can.interface.Bus(channel=IFACE, interface="socketcan")

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
