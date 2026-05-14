#!/usr/bin/env python3

import time
import json
import importlib
import sys
import os
import signal
import can

# -------------------------------------------------
# PATHS
# -------------------------------------------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

VEHICLE = "seat_1p"
BINDINGS = "default"

CFG_PATH = os.path.join(
    BASE_DIR,
    "vehicles",
    VEHICLE,
    "config.json"
)

BINDINGS_PATH = os.path.join(
    BASE_DIR,
    "bindings",
    f"{BINDINGS}.json"
)

# -------------------------------------------------
# SETTINGS
# -------------------------------------------------

IFACE = "can0"
RELOAD_INTERVAL = 0.3

_need_reload = False


# -------------------------------------------------
# SIGNAL HANDLER
# -------------------------------------------------

def _sig_hup(_signo, _frame):
    global _need_reload

    _need_reload = True

    print(
        "[canbusd] SIGHUP received -> reload config",
        flush=True
    )


signal.signal(signal.SIGHUP, _sig_hup)


# -------------------------------------------------
# LOAD BINDINGS
# -------------------------------------------------

def _load_bindings():

    try:
        with open(BINDINGS_PATH, "r") as f:
            bindings = json.load(f)

        print(
            f"[canbusd] loaded {len(bindings)} bindings",
            flush=True
        )

        return bindings

    except Exception as e:

        print(
            f"[canbusd] failed to load bindings: {e}",
            flush=True
        )

        return {}


# -------------------------------------------------
# LOAD CONFIG
# -------------------------------------------------

def _load_config_safely(
    prev_rules,
    prev_mtime,
    prev_presence
):
    """
    Load rules + presence blocks from config.json
    Hot-reload friendly.
    """

    global _need_reload

    try:
        mtime = os.path.getmtime(CFG_PATH)

    except FileNotFoundError:

        if prev_rules is None and prev_presence is None:

            print(
                f"[canbusd] config missing {CFG_PATH}",
                flush=True
            )

        return (
            prev_rules,
            prev_mtime,
            prev_presence
        )

    if (
        prev_mtime is not None
        and mtime == prev_mtime
        and not _need_reload
    ):
        return (
            prev_rules,
            prev_mtime,
            prev_presence
        )

    try:

        with open(CFG_PATH, "r") as f:
            cfg = json.load(f)

        # -----------------------------------------
        # CAN RULES
        # -----------------------------------------

        rules = {}
        count = 0

        for rule in cfg.get("rules", []):

            cid = (
                int(rule["id"], 16)
                if isinstance(rule["id"], str)
                else int(rule["id"])
            )

            bidx = int(rule.get("byte", 0))

            raw_val = rule.get("value", None)

            # Support "any" / None
            if (
                isinstance(raw_val, str)
                and raw_val.lower() == "any"
            ):
                val = None

            elif raw_val is None:
                val = None

            else:
                val = int(raw_val)

            event = rule["event"]

            rules.setdefault(cid, []).append(
                (bidx, val, event)
            )

            count += 1

        print(
            f"[canbusd] loaded {count} rules",
            flush=True
        )

        # -----------------------------------------
        # PRESENCE RULES
        # -----------------------------------------

        presence = []
        pcount = 0

        for pr in cfg.get("presence", []):

            cid = (
                int(pr["id"], 16)
                if isinstance(pr["id"], str)
                else int(pr["id"])
            )

            tms = int(pr.get("timeout_ms", 1000))

            onp = pr.get("on_present")
            ona = pr.get("on_absent")

            presence.append({
                "id": cid,
                "timeout_ms": tms,
                "on_present": onp,
                "on_absent": ona
            })

            pcount += 1

        if pcount:

            print(
                f"[canbusd] loaded {pcount} presence rules",
                flush=True
            )

        _need_reload = False

        return (
            rules,
            mtime,
            presence
        )

    except Exception as e:

        print(
            f"[canbusd] reload failed: {e}",
            flush=True
        )

        return (
            prev_rules,
            prev_mtime,
            prev_presence
        )


# -------------------------------------------------
# ACTION EXECUTION
# -------------------------------------------------

def _call_action(action):

    import traceback

    try:

        mod = importlib.import_module(
            f"actions.{action['module']}"
        )

        fn = getattr(mod, action["func"])

        args = action.get("args", [])

        fn(*args)

    except Exception as e:

        print(
            f"[canbusd] action error {action}: {e}",
            flush=True
        )

        traceback.print_exc()


# -------------------------------------------------
# EVENT DISPATCHER
# -------------------------------------------------

def _dispatch_event(
    bindings,
    event,
    extra_args=None
):

    action = bindings.get(event)

    if not action:

        print(
            f"[canbusd] no binding for event '{event}'",
            flush=True
        )

        return

    act = dict(action)

    if extra_args:

        if (
            "args" in act
            and isinstance(act["args"], list)
        ):
            act["args"] = act["args"] + extra_args

        else:
            act["args"] = extra_args

    print(
        f"[canbusd] event -> {event}",
        flush=True
    )

    _call_action(act)


# -------------------------------------------------
# MAIN LOOP
# -------------------------------------------------

def main():

    rules, mtime, presence = _load_config_safely(
        None,
        None,
        []
    )

    bindings = _load_bindings()

    last_codes = {}

    # arbitration_id -> last seen timestamp
    last_seen = {}

    # arbitration_id -> current presence state
    present_state = {}

    bus = None

    last_check = 0.0

    offcar_logged = False

    while True:

        try:

            now = time.monotonic()

            # -------------------------------------
            # HOT RELOAD
            # -------------------------------------

            if now - last_check >= RELOAD_INTERVAL:

                rules, mtime, presence = (
                    _load_config_safely(
                        rules,
                        mtime,
                        presence
                    )
                )

                bindings = _load_bindings()

                last_check = now

            # -------------------------------------
            # OFF-CAR SAFE MODE
            # -------------------------------------

            car_env = os.path.exists(
                f"/sys/class/net/{IFACE}"
            )

            if not car_env:

                if bus is not None:

                    try:
                        bus.shutdown()

                    except Exception:
                        pass

                    bus = None

                if not offcar_logged:

                    print(
                        f"[canbusd] {IFACE} not present "
                        "-> idle mode",
                        flush=True
                    )

                    offcar_logged = True

                time.sleep(1.0)

                continue

            else:

                if offcar_logged:

                    print(
                        f"[canbusd] {IFACE} detected "
                        "-> resuming",
                        flush=True
                    )

                    offcar_logged = False

            # -------------------------------------
            # OPEN CAN BUS
            # -------------------------------------

            if bus is None:

                print(
                    f"[canbusd] opening {IFACE} …",
                    flush=True
                )

                bus = can.interface.Bus(
                    channel=IFACE,
                    bustype="socketcan"
                )

                print(
                    f"[canbusd] listening on {IFACE}",
                    flush=True
                )

            msg = bus.recv(timeout=0.2)

            # -------------------------------------
            # PRESENCE TRACKING
            # -------------------------------------

            if msg is not None:

                last_seen[msg.arbitration_id] = now

            # -------------------------------------
            # PRESENCE EVENTS
            # -------------------------------------

            if presence:

                for pr in presence:

                    cid = pr["id"]

                    tms = pr["timeout_ms"]

                    was = present_state.get(
                        cid,
                        None
                    )

                    is_now = (
                        (
                            now
                            - last_seen.get(cid, -1e9)
                        )
                        * 1000.0
                    ) <= tms

                    if was is None:

                        present_state[cid] = is_now

                    elif was != is_now:

                        present_state[cid] = is_now

                        event = (
                            pr["on_present"]
                            if is_now
                            else pr["on_absent"]
                        )

                        if event:

                            print(
                                f"[canbusd] presence "
                                f"{'ON' if is_now else 'OFF'} "
                                f"id=0x{cid:X} -> {event}",
                                flush=True
                            )

                            _dispatch_event(
                                bindings,
                                event
                            )

            # -------------------------------------
            # SHORT CIRCUITS
            # -------------------------------------

            if msg is None or not rules:
                continue

            cid = msg.arbitration_id

            if cid not in rules:
                continue

            # -------------------------------------
            # RULE MATCHING
            # -------------------------------------

            for (
                byte_index,
                value,
                event
            ) in rules[cid]:

                if msg.dlc <= byte_index:
                    continue

                code = msg.data[byte_index]

                key = (
                    cid,
                    byte_index,
                    value
                )

                last = last_codes.get(
                    key,
                    None
                )

                # ---------------------------------
                # ANY VALUE MODE
                # ---------------------------------

                if value is None:

                    if last != code:

                        _dispatch_event(
                            bindings,
                            event,
                            [code]
                        )

                        last_codes[key] = code

                    continue

                # ---------------------------------
                # EDGE TRIGGER MODE
                # ---------------------------------

                if (
                    last == 0x00
                    and code == value
                ):

                    print(
                        f"[canbusd] match "
                        f"id=0x{cid:X} "
                        f"byte{byte_index}=0x{value:02X} "
                        f"-> {event}",
                        flush=True
                    )

                    _dispatch_event(
                        bindings,
                        event
                    )

                if code in (0x00, value):

                    last_codes[key] = code

        except Exception as e:

            print(
                f"[canbusd] CAN error: {e} "
                "(retry in 1s)",
                flush=True
            )

            time.sleep(1)

            try:

                if bus is not None:
                    bus.shutdown()

            except Exception:
                pass

            bus = None


# -------------------------------------------------
# ENTRYPOINT
# -------------------------------------------------

if __name__ == "__main__":

    if (
        len(sys.argv) > 1
        and sys.argv[1] == "--check"
    ):

        r, _, p = _load_config_safely(
            None,
            None,
            []
        )

        ok = bool(r) or bool(p)

        print(
            "[canbusd] config OK"
            if ok
            else "[canbusd] no rules/presence loaded"
        )

        sys.exit(0 if ok else 1)

    main()