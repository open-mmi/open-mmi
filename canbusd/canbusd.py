#!/usr/bin/env python3
"""
Open MMI CAN Bus Daemon

Reads CAN messages, matches them against rules, and dispatches events to actions.
Supports hot-reload of configuration via SIGHUP signal.
"""

import time
import json
import importlib
import sys
import os
import signal
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

try:
    import can
except ImportError:
    print("ERROR: python-can not installed. Install with: pip install python-can", file=sys.stderr)
    sys.exit(1)

# -------------------------------------------------
# LOGGING SETUP
# -------------------------------------------------

log_level = os.getenv("OPEN_MMI_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="[%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("canbusd")

# -------------------------------------------------
# PATHS & CONFIGURATION
# -------------------------------------------------

BASE_DIR = Path(__file__).parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Support environment variable override for vehicle and bindings
VEHICLE = os.getenv("OPEN_MMI_VEHICLE", "seat_1p")
BINDINGS = os.getenv("OPEN_MMI_BINDINGS", "default")

CFG_PATH = BASE_DIR / "vehicles" / VEHICLE / "config.json"
BINDINGS_PATH = BASE_DIR / "bindings" / f"{BINDINGS}.json"

# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------

IFACE = "can0"
RELOAD_INTERVAL = 60  # seconds
SUBPROCESS_TIMEOUT = 5  # seconds
PRESENCE_TIMEOUT_CLEANUP = 60000  # ms - clean up entries older than this
EDGE_TRIGGER_THRESHOLD = 0x00  # Trigger on edge from this value
ANY_VALUE_WILDCARD = "any"
DEFAULT_PRESENCE_TIMEOUT = 1000  # ms

# Global state
_need_reload = False
_reload_lock = __import__("threading").Lock()


# -------------------------------------------------
# SIGNAL HANDLER
# -------------------------------------------------

def _sig_hup(_signo: int, _frame: Any) -> None:
    """Handle SIGHUP signal for config reload."""
    global _need_reload
    with _reload_lock:
        _need_reload = True
    logger.info("SIGHUP received -> reload config")


signal.signal(signal.SIGHUP, _sig_hup)


# -------------------------------------------------
# LOAD BINDINGS
# -------------------------------------------------

def _load_bindings() -> Dict[str, Dict[str, Any]]:
    """Load event-to-action bindings from JSON file."""
    try:
        with open(BINDINGS_PATH, "r") as f:
            bindings = json.load(f)
        logger.info(f"Loaded {len(bindings)} bindings from {BINDINGS_PATH}")
        return bindings
    except FileNotFoundError:
        logger.error(f"Bindings file not found: {BINDINGS_PATH}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in bindings file: {e}")
        return {}
    except Exception as e:
        logger.error(f"Failed to load bindings: {e}")
        return {}


# -------------------------------------------------
# LOAD CONFIG
# -------------------------------------------------

def _load_config_safely(
    prev_rules: Optional[Dict[int, List[Tuple]]] = None,
    prev_mtime: Optional[float] = None,
    prev_presence: Optional[List[Dict]] = None
) -> Tuple[Optional[Dict], Optional[float], List[Dict]]:
    """
    Load rules + presence blocks from config.json.
    Hot-reload friendly - only reloads if file mtime changed or SIGHUP received.
    """
    global _need_reload

    try:
        mtime = CFG_PATH.stat().st_mtime
    except FileNotFoundError:
        if prev_rules is None and prev_presence is None:
            logger.warning(f"Config file not found: {CFG_PATH}")
        return (prev_rules, prev_mtime, prev_presence or [])

    # Skip reload if file unchanged and no SIGHUP
    with _reload_lock:
        reload_requested = _need_reload
        if not reload_requested:
            _need_reload = False

    if (prev_mtime is not None and mtime == prev_mtime and not reload_requested):
        return (prev_rules, prev_mtime, prev_presence or [])

    try:
        with open(CFG_PATH, "r") as f:
            cfg = json.load(f)

        # -----------------------------------------
        # CAN RULES
        # -----------------------------------------

        rules: Dict[int, List[Tuple]] = {}
        count = 0

        for rule in cfg.get("rules", []):
            try:
                # Parse CAN ID
                cid = (
                    int(rule["id"], 16)
                    if isinstance(rule["id"], str)
                    else int(rule["id"])
                )

                bidx = int(rule.get("byte", 0))

                # Parse value with wildcard support
                raw_val = rule.get("value", None)
                if isinstance(raw_val, str) and raw_val.lower() == ANY_VALUE_WILDCARD:
                    val = None
                elif raw_val is None:
                    val = None
                else:
                    val = int(raw_val)

                event = rule["event"]

                rules.setdefault(cid, []).append((bidx, val, event))
                count += 1
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid rule: {rule} - {e}")
                continue

        logger.info(f"Loaded {count} CAN rules")

        # -----------------------------------------
        # PRESENCE RULES
        # -----------------------------------------

        presence: List[Dict[str, Any]] = []
        pcount = 0

        for pr in cfg.get("presence", []):
            try:
                cid = (
                    int(pr["id"], 16)
                    if isinstance(pr["id"], str)
                    else int(pr["id"])
                )

                tms = int(pr.get("timeout_ms", DEFAULT_PRESENCE_TIMEOUT))
                onp = pr.get("on_present")
                ona = pr.get("on_absent")

                presence.append({
                    "id": cid,
                    "timeout_ms": tms,
                    "on_present": onp,
                    "on_absent": ona
                })
                pcount += 1
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping invalid presence rule: {pr} - {e}")
                continue

        if pcount:
            logger.info(f"Loaded {pcount} presence rules")

        with _reload_lock:
            _need_reload = False

        return (rules, mtime, presence)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config: {e}")
        return (prev_rules, prev_mtime, prev_presence or [])
    except Exception as e:
        logger.error(f"Config reload failed: {e}")
        return (prev_rules, prev_mtime, prev_presence or [])


# -------------------------------------------------
# ACTION EXECUTION
# -------------------------------------------------

def _validate_args(args: List[Any]) -> bool:
    """Validate action arguments to prevent injection attacks."""
    for arg in args:
        if not isinstance(arg, (str, int, float)):
            return False
        # Basic check: avoid shell metacharacters
        if isinstance(arg, str) and any(c in arg for c in [";", "&", "|", "$", "`"]):
            logger.warning(f"Suspicious argument rejected: {arg}")
            return False
    return True


def _call_action(action: Dict[str, Any]) -> None:
    """Execute an action module/function with error handling."""
    try:
        module_name = action.get("module")
        func_name = action.get("func")
        args = action.get("args", [])

        if not module_name or not func_name:
            logger.error(f"Invalid action config: {action}")
            return

        # Validate arguments
        if not _validate_args(args):
            logger.error(f"Invalid action arguments: {args}")
            return

        # Dynamic import and execution
        mod = importlib.import_module(f"actions.{module_name}")
        fn = getattr(mod, func_name)
        fn(*args)

        logger.debug(f"Action executed: {module_name}.{func_name}({args})")

    except ModuleNotFoundError as e:
        logger.error(f"Action module not found: {e}")
    except AttributeError as e:
        logger.error(f"Action function not found: {e}")
    except TimeoutError as e:
        logger.error(f"Action timeout: {e}")
    except Exception as e:
        logger.error(f"Action execution failed: {action} - {e}", exc_info=True)


# -------------------------------------------------
# EVENT DISPATCHER
# -------------------------------------------------

def _dispatch_event(
    bindings: Dict[str, Dict[str, Any]],
    event: str,
    extra_args: Optional[List[Any]] = None
) -> None:
    """Dispatch a semantic event to its bound action."""
    action = bindings.get(event)

    if not action:
        logger.debug(f"No binding for event: {event}")
        return

    # Make a copy to avoid modifying original
    act = dict(action)

    # Merge extra arguments (e.g., from CAN data)
    if extra_args:
        if "args" in act and isinstance(act["args"], list):
            act["args"] = act["args"] + extra_args
        else:
            act["args"] = extra_args

    logger.info(f"Event dispatched: {event}")
    _call_action(act)


# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

def main() -> None:
    """Main CAN bus daemon loop."""
    rules, mtime, presence = _load_config_safely(None, None, [])
    bindings = _load_bindings()

    last_codes: Dict[Tuple[int, int, Optional[int]], int] = {}
    last_seen: Dict[int, float] = {}  # arbitration_id -> timestamp
    present_state: Dict[int, Optional[bool]] = {}  # arbitration_id -> presence state

    bus: Optional[can.BusABC] = None
    last_check = 0.0
    offcar_logged = False

    logger.info(f"Starting canbusd (vehicle={VEHICLE}, bindings={BINDINGS})")

    while True:
        try:
            now = time.monotonic()

            # --------------------------------
            # HOT RELOAD
            # --------------------------------

            if now - last_check >= RELOAD_INTERVAL:
                rules, mtime, presence = _load_config_safely(rules, mtime, presence)
                bindings = _load_bindings()
                last_check = now

            # --------------------------------
            # OFF-CAR SAFE MODE
            # --------------------------------

            car_env = Path(f"/sys/class/net/{IFACE}").exists()

            if not car_env:
                if bus is not None:
                    try:
                        bus.shutdown()
                    except Exception as e:
                        logger.debug(f"Bus shutdown error: {e}")
                    bus = None

                if not offcar_logged:
                    logger.info(f"{IFACE} not detected -> idle mode")
                    offcar_logged = True

                time.sleep(1.0)
                continue
            else:
                if offcar_logged:
                    logger.info(f"{IFACE} detected -> resuming")
                    offcar_logged = False

            # --------------------------------
            # OPEN CAN BUS
            # --------------------------------

            if bus is None:
                try:
                    logger.info(f"Opening {IFACE}...")
                    bus = can.interface.Bus(
                        channel=IFACE,
                        bustype="socketcan"
                    )
                    logger.info(f"Listening on {IFACE}")
                except Exception as e:
                    logger.error(f"Failed to open CAN bus: {e}")
                    time.sleep(1)
                    continue

            msg = bus.recv(timeout=0.2)

            # --------------------------------
            # PRESENCE TRACKING
            # --------------------------------

            if msg is not None:
                last_seen[msg.arbitration_id] = now
                # Cleanup old entries to prevent memory leaks
                for cid in list(last_seen.keys()):
                    if (now - last_seen[cid]) * 1000 > PRESENCE_TIMEOUT_CLEANUP:
                        del last_seen[cid]

            # --------------------------------
            # PRESENCE EVENTS
            # --------------------------------

            if presence:
                for pr in presence:
                    cid = pr["id"]
                    tms = pr["timeout_ms"]

                    was = present_state.get(cid)
                    is_now = ((now - last_seen.get(cid, -1e9)) * 1000.0) <= tms

                    if was is None:
                        present_state[cid] = is_now
                    elif was != is_now:
                        present_state[cid] = is_now

                        event = pr["on_present"] if is_now else pr["on_absent"]

                        if event:
                            state_str = "ON" if is_now else "OFF"
                            logger.info(f"Presence {state_str}: id=0x{cid:X} -> {event}")
                            _dispatch_event(bindings, event)

            # --------------------------------
            # SHORT CIRCUITS
            # --------------------------------

            if msg is None or not rules:
                continue

            cid = msg.arbitration_id
            if cid not in rules:
                continue

            # --------------------------------
            # RULE MATCHING
            # --------------------------------

            for (byte_index, value, event) in rules[cid]:
                if msg.dlc <= byte_index:
                    continue

                code = msg.data[byte_index]
                key = (cid, byte_index, value)
                last = last_codes.get(key)

                # --------------------------
                # ANY VALUE MODE
                # --------------------------

                if value is None:
                    if last != code:
                        _dispatch_event(bindings, event, [code])
                        last_codes[key] = code
                    continue

                # --------------------------
                # EDGE TRIGGER MODE
                # --------------------------

                if last == EDGE_TRIGGER_THRESHOLD and code == value:
                    logger.debug(
                        f"Match: id=0x{cid:X} byte{byte_index}=0x{value:02X} -> {event}"
                    )
                    _dispatch_event(bindings, event)

                if code in (EDGE_TRIGGER_THRESHOLD, value):
                    last_codes[key] = code

        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            break
        except Exception as e:
            logger.error(f"CAN error: {e} (retry in 1s)", exc_info=True)
            time.sleep(1)

            try:
                if bus is not None:
                    bus.shutdown()
            except Exception as e:
                logger.debug(f"Bus shutdown error: {e}")
            bus = None

    # Cleanup
    if bus is not None:
        try:
            bus.shutdown()
        except Exception as e:
            logger.debug(f"Final shutdown error: {e}")
    logger.info("Canbusd stopped")


# -------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        r, _, p = _load_config_safely(None, None, [])
        ok = bool(r) or bool(p)
        print("[canbusd] config OK" if ok else "[canbusd] no rules/presence loaded")
        sys.exit(0 if ok else 1)

    main()
