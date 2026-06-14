# CAN bus model

`open-mmi` treats CAN inputs as named buses.

The current daemon still consumes one SocketCAN interface at a time, but the profile model
should describe that interface using a stable bus name such as `comfort`, `powertrain`,
`infotainment`, or `replay`.

This keeps vehicle CAN knowledge out of core logic and avoids baking `can0` into profile
rules.

---

## Current alpha model

The current single-bus runtime resolves:

```text
named bus label  ->  SocketCAN interface
comfort          ->  can0
```

The daemon consumes an already-provisioned SocketCAN interface. It does not silently
configure bitrate and does not bring interfaces up.

For the maintainer-tested Seat Leon 1P / VAG PQ35 setup, udev currently provisions:

```text
can0 at 100000
```

The daemon then opens that interface.

---

## Profile fields

Vehicle profiles may declare:

```json
{
  "default_bus": "comfort",
  "can_buses": {
    "comfort": {
      "interface": "can0",
      "bitrate": 100000,
      "capture_point": "maintainer-tested comfort CAN connection",
      "provisioning": "udev",
      "bring_up": false
    }
  }
}
```

`default_bus` is the named bus used by rules, presence rules, and status rules when they do
not explicitly set `bus`.

`can_buses` is metadata and runtime selection guidance. `bitrate` documents the expected
bus speed, but the daemon does not configure that bitrate.

---

## Environment overrides

`OPEN_MMI_CAN_BUS` selects the active named bus.

`OPEN_MMI_CAN_INTERFACE` selects the SocketCAN interface consumed by the daemon.

The interface override wins over profile metadata. This allows testing the same logical
bus against another already-provisioned interface, for example:

```text
OPEN_MMI_CAN_BUS=comfort
OPEN_MMI_CAN_INTERFACE=vcan0
```

---

## Per-rule bus fields

Rules may optionally declare a bus:

```json
{
  "id": "0x470",
  "bus": "comfort",
  "byte": 1,
  "type": "bitfield",
  "path": "doors"
}
```

If `bus` is missing, the rule belongs to `default_bus`.

This keeps existing profiles compatible while allowing future profiles to distinguish
comfort, powertrain, infotainment, OBD, or replay traffic.

---

## Profile-driven provisioning

Profile selection now drives local CAN provisioning.

The normal user-facing workflow is:

```bash
sudo ./scripts/manage.sh config apply-profile seat_1p default
```

That command reads the selected profile's `default_bus` and `can_buses`
metadata, then generates the matching daemon runtime drop-in and udev
provisioning rule.

This avoids splitting one vehicle choice across several unrelated commands.

The daemon remains passive. Provisioning is performed only by explicit management
tooling.

---

## Non-goals

The current model does not yet implement:

* multiple simultaneous SocketCAN listeners
* automatic bitrate configuration
* automatic interface bring-up
* CAN transmit/control
* vehicle auto-detection

Those should remain separate reviewed changes.
