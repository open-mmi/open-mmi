# CAN runtime configuration roadmap

`open-mmi` currently assumes a single SocketCAN interface.

This matches the current maintainer-tested Seat Leon 1P / VAG PQ35 setup, but it should not become the long-term model. Future vehicles and installs may need multiple CAN inputs at different bitrates.

Examples:

```text
comfort CAN       can0    100000
powertrain CAN    can1    500000
infotainment CAN  can2    vehicle-dependent
OBD capture       canX    vehicle-dependent
replay/testing    vcan0   no physical bitrate
```

This work belongs in a dedicated beta branch because CAN interface setup affects core runtime behaviour.

---

## Current behaviour

Current behaviour:

* the daemon expects `can0`
* the included udev rule brings up `can0` at `100000`
* the daemon currently opens one SocketCAN bus
* vehicle rules currently assume that single bus
* this matches the current Seat 1P / VAG PQ35 maintainer-tested setup

---

## Compatibility requirement: udev hotplug and reboot survival

The current setup relies on udev to make the tested CAN adapter usable across hotplug events and reboots.

That behaviour must not regress.

The first named-bus implementation should assume SocketCAN interfaces are provisioned externally by udev, systemd-networkd, or user setup scripts. The daemon should consume those interfaces; it should not silently replace the provisioning layer.

Required behaviour:

- if the configured interface is missing, the daemon keeps running and waits
- if the interface appears later, the daemon opens it
- if the interface disappears, the daemon closes the bus and waits for it to return
- after reboot, existing udev/system setup should still bring the interface back
- bitrate configuration must remain explicit and reviewable
- automatic interface setup must not silently change live vehicle CAN settings

A future optional helper may bring interfaces up, but that should be explicit user-chosen behaviour, not hidden daemon behaviour.

---

## Current provisioning split

The current implementation separates provisioning from consumption:

- `udev/80-canbus.rules` provisions the tested SocketCAN interface
- the current rule targets `can0`
- the current rule configures `can0` at `100000`
- `systemd/user/canbusd.service` starts the daemon but does not configure CAN
- `scripts/manage.sh` installs/removes the udev rule and user service
- the daemon waits for the configured interface to exist and reconnects if it disappears
- `scripts/manage.sh config edit-service` already allows local systemd service overrides

The first runtime-config pass should preserve this split.

Named buses should initially describe which already-provisioned interface the daemon should consume. They should not automatically replace the udev/system provisioning layer.

## Design direction

The future design should model CAN inputs as **named buses**, not just as one global interface.

A possible future runtime config shape:

```json
{
  "can_buses": {
    "comfort": {
      "interface": "can0",
      "bitrate": 100000,
      "bring_up": false,
      "capture_point": "radio harness"
    }
  },
  "default_bus": "comfort"
}
```

Vehicle profile rules may later declare which bus they belong to:

```json
{
  "id": "0x470",
  "bus": "comfort"
}
```

If a rule does not declare a bus, it should use the profile or runtime `default_bus`.

This keeps today’s one-bus setup simple while leaving a path toward multiple CAN inputs.

---

## Long-term goals

The long-term design should support:

* one CAN bus today
* multiple named CAN buses later
* different bitrates per bus
* different physical capture points per bus
* `vcan` replay/testing
* `slcan` and USB CAN adapters
* OBD-port capture
* radio-harness capture
* one decoded status snapshot built from all active buses

The status snapshot should remain vehicle-state focused. UI consumers should not need to know which CAN bus produced a decoded value unless they are in a debug/developer view.

---

## Open questions

Open questions:

* should runtime CAN config live in service environment, user config, vehicle profile metadata, or a dedicated runtime config file?
* should `open-mmi` bring interfaces up itself or expect SocketCAN to be ready before the daemon starts?
* should bitrate be controlled by udev, systemd, runtime config, profile metadata, or external setup scripts?
* how should `vcan`, `slcan`, USB adapters, OBD capture, and radio-harness capture be represented?
* how should tested capture points be documented per vehicle profile?
* how should conflicting decoded values from multiple buses be handled?
* how should bus freshness/staleness be represented in the status snapshot?
* should each bus have its own health/debug state?

---

## Suggested implementation phases

### Phase 1: single named bus

Keep one active SocketCAN interface, but model it internally as a named bus.

Example:

```text
default_bus = comfort
comfort.interface = can0
```

Existing vehicle profiles continue working because missing `bus` values default to `comfort`.

### Phase 2: runtime-configurable interface

Allow the single named bus interface to be changed without editing Python code.

Examples:

```text
can0
can1
vcan0
slcan0
```

This should preserve the current `can0` default.

### Phase 3: bus metadata in vehicle/profile docs

Document tested bus names, capture points, and bitrates for each vehicle profile.

Example:

```text
Seat Leon 1P / VAG PQ35
default bus: comfort
tested interface: can0
tested bitrate: 100000
tested capture point: radio harness
```

### Phase 4: per-rule bus field

Allow vehicle rules to specify a bus.

Example:

```json
{
  "id": "0x470",
  "bus": "comfort"
}
```

Profiles that do not specify `bus` continue using `default_bus`.

### Phase 5: multiple active buses

Allow the daemon to open and monitor multiple SocketCAN interfaces.

Decoded values from all active buses should be merged into one status snapshot.

---

## Non-goals for the first pass

Do not mix the first runtime-config work with:

* CAN transmit/control
* automatic bitrate guessing
* automatic vehicle detection
* full multi-bus arbitration
* large vehicle profile rewrites
* UI redesign
* release/tag work

The first pass should preserve the current Seat 1P behaviour while removing the hardcoded single-interface assumption.
