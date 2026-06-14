# Vehicle profiles

`open-mmi` separates generic runtime logic from vehicle-specific CAN knowledge.

The backend should understand how to load profiles, decode configured rules, publish state,
and survive interface reconnects. It should not contain hard-coded assumptions for a
specific vehicle platform.

Vehicle-specific information belongs in:

```text
vehicles/<profile>/config.json
```

---

## Reference profile

The maintainer-tested reference vehicle is currently:

* Seat Leon 1P
* VAG PQ35 platform
* comfort CAN at 100000 bitrate
* SocketCAN interface currently provisioned as `can0`

This does not mean `open-mmi` is a finished Seat/VW infotainment product. The project is
currently alpha/backend software with an experimentally tested reference profile.

---

## Profile shape

A vehicle profile may contain:

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
  },
  "rules": [],
  "presence": [],
  "status": []
}
```

`default_bus` is the named bus used by profile entries that do not explicitly declare
`bus`.

`can_buses` documents named CAN bus metadata and gives the daemon runtime selection
guidance.

The daemon still consumes an already-provisioned SocketCAN interface. It does not silently
configure bitrate and does not silently bring interfaces up.

---

## Applying a profile

Normal setup should apply the selected vehicle profile as the source of truth:

```bash
sudo ./scripts/manage.sh config apply-profile seat_1p default
```

This creates user-owned profile/bindings files when missing, writes the daemon
runtime drop-in, and generates udev rules from `can_buses` metadata.

`config init` only creates user config files. `config edit-can` remains available
as an advanced override for unusual hardware or replay testing.

---

## What belongs in a vehicle profile

Vehicle profiles may define:

* named CAN bus metadata
* tested capture points
* expected bitrate metadata
* CAN IDs used by that vehicle
* byte positions
* masks
* scaling rules
* status meanings
* display labels
* known quirks
* unknown or rapidly changing bytes observed during testing

Examples include:

* handbrake status
* lamp status
* steering angle
* indicator state
* washer fluid warning
* pad wear warning

---

## Per-entry bus selection

Rules, presence rules, and status rules may optionally declare `bus`.

Example:

```json
{
  "id": "0x470",
  "bus": "comfort",
  "byte": 1,
  "type": "bitfield",
  "path": "doors"
}
```

If `bus` is missing, the entry belongs to the profile `default_bus`.

This keeps one-bus profiles simple while leaving room for future profiles that use comfort,
powertrain, infotainment, OBD, or replay buses.

---

## What does not belong in core logic

Core logic must not hard-code:

* Seat-specific CAN IDs
* VAG-specific byte meanings
* fixed interface names such as `can0`
* fixed bitrates such as `100000`
* dashboard labels that only make sense for one vehicle

The core should stay vehicle-independent.

Core logic may provide reusable primitives such as:

* named bus resolution
* rule loading
* presence tracking
* status publishing
* generic status rule types

Vehicle-specific CAN knowledge should remain profile-driven.

---

## Status rules

Status rules describe how raw CAN data becomes useful state.

Current supported rule styles include boolean rules, masked boolean rules, bitfield rules,
enum rules, percent rules, raw values, and signed or scaled values.

### Boolean rules

A boolean rule checks whether a byte or value represents an on/off state.

### Masked boolean rules

A masked boolean rule checks whether a specific bit is set within a byte.

Example use case:

```text
handbrake active when mask 0x20 is set
```

This allows one byte to contain several independent status flags.

### Signed or scaled values

Some values are not simple on/off states. Steering angle is an example where the profile
may need to describe direction, magnitude, scaling, or byte layout.

These rules should remain profile-driven where possible.

---

## Unknown bytes

Unknown bytes should be documented rather than guessed.

Use comments, notes, or roadmap documentation to record:

* bytes that change rapidly regardless of state
* bytes that appear stable
* states tested on a real vehicle
* values captured from replay logs
* values that need more samples

Avoid turning guesses into core behaviour.

---

## Adding a new profile

A new vehicle profile should start small.

Recommended process:

1. Copy an existing profile only if the platform is genuinely related.
2. Record the vehicle, platform, model year, and tested CAN bus.
3. Document named bus metadata and capture point.
4. Add one signal at a time.
5. Test against replay data where possible.
6. Test on a real vehicle only when safe.
7. Keep uncertain mappings clearly marked.
8. Do not modify core logic unless the rule type is genuinely reusable.

---

## Safety and expectations

Vehicle profiles are experimental.

A profile may be incomplete, wrong, or specific to a trim, module coding, model year, or
retrofit state. `open-mmi` should not be treated as safety-critical software.
