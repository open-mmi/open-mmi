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

## Maintained catalogue identity and evidence

Normal custom profiles remain lightweight and editable. A profile distributed in the maintained `vehicles/` catalogue must also carry `schema_version: 1` and the metadata envelope defined by [`maintained-profile-standard.md`](maintained-profile-standard.md). The envelope records vehicle identity, model-year range, maturity, maintainers, qualification scope, date, evidence and honest limitations.

Check the source catalogue with:

```bash
open-mmi-config vehicle-setup conform --root .
```

The command is stricter than ordinary custom-profile validation by design. It gates a maintained compatibility claim; it does not restrict discovery.

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

This selects the maintained profile and bindings from the installed Open MMI tree,
writes the daemon runtime drop-in, and generates udev rules from `can_buses` metadata.
It does not create or activate custom copies.

`config init` explicitly creates user-owned custom copies from the installed maintained
files without activating them. `config edit-can` remains available as an advanced
override for unusual hardware or replay testing.

---

## Universal events, not vehicle-specific actions

A profile translates vehicle-specific CAN signals into canonical Open MMI events. It must
not embed Python modules, function names, or manufacturer-specific synonyms for an existing
universal intent.

For example, different Seat and Vauxhall CAN messages may both emit `mute_toggle`; the
application behavior belongs in the separate bindings file as a canonical action such as
`media.mute.toggle`. The action registry, not the binding, owns the private Python
module/function mapping. Event contracts are documented in
[`vehicle-event-registry.md`](vehicle-event-registry.md), action contracts in
[`vehicle-action-registry.md`](vehicle-action-registry.md), and the complete contribution
rules in [`vehicle-integration-standard.md`](vehicle-integration-standard.md).

Unknown event names, deprecated aliases, payload-bearing `any` rules for no-payload events,
and no-payload rules for value events fail profile validation.

## Universal statuses, not vehicle-specific paths

Status rules translate vehicle-specific bytes, masks and scaling into canonical persistent
state. The machine-readable source is `canbusd/data/vehicle-statuses.v1.json`; the generated
reference is [`vehicle-status-registry.md`](vehicle-status-registry.md).

For example, one vehicle may publish `doors.front_right` from a bitfield while another uses a
dedicated boolean byte. The CAN decoder changes; dashboards and other consumers receive the
same human-readable path and value contract.

The registry records value type, unit, nullability and lifecycle. Stable paths are public
consumer contracts. Experimental paths are provisional interpretations, while diagnostic
paths preserve raw reverse-engineering evidence without presenting it as stable human state.
Unregistered paths and incompatible decoder types fail maintained-profile validation.

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

### Toggle-latched boolean rules

Some CAN bits represent a momentary button/request edge rather than a held state. A boolean
rule may declare `"state": "toggle_latch"` so each rising edge toggles the published value:

```json
{
  "id": "0x3E1",
  "byte": 0,
  "type": "bool",
  "path": "climate.rear_window_heater_requested",
  "mask": "0x04",
  "true": "0x04",
  "false": "0x00",
  "state": "toggle_latch",
  "initial": false
}
```

The daemon owns latch state per active profile runtime. State is reset when the daemon starts,
when status rules are reloaded, or when the active CAN interface changes. Inactive frames and
ordinary periods without traffic preserve the current latch value.

Configuration reloads are fail-safe: an unreadable or invalid replacement profile leaves the
last known-good rules and CAN runtime active. The test suite also replays frames over
python-can's virtual interface so profile parsing, daemon reception, status publication,
and event dispatch are exercised together without vehicle hardware.

By default, state identity includes the CAN id, byte, output path, mask, and true/false values.
An explicit `state_key` may be used only when multiple rules intentionally share one latch.

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

A new vehicle profile should start small. The registry is a continuity checkpoint, not a
walled garden: raw research and provisional observations are welcome, while maintained
profiles translate confirmed signals into one shared human-readable vocabulary.

Read [`vehicle-contribution-workflow.md`](vehicle-contribution-workflow.md) before promoting
an observation into a maintained rule.

Recommended process:

1. Record raw CAN evidence, physical actions and uncertainty without waiting for a final name.
2. Read the vehicle integration standard and canonical event registry.
3. Copy an existing profile only if the platform is genuinely related.
4. Record the vehicle, platform, model year, and tested CAN bus.
5. Document named bus metadata and capture point.
6. Confirm what each signal means to a person and classify it as event or persistent status.
7. Search the registry and reuse an existing canonical event when its meaning matches.
8. When the human concept is genuinely new, add a universal registry proposal in the same pull request.
9. Add one signal at a time and test against replay data where possible.
10. Test on a real vehicle only when safe and keep uncertain mappings clearly marked.
11. Do not modify core logic unless the rule type is genuinely reusable.

A contributor who finds the same mute control in another vehicle should normally copy the
canonical `mute_toggle` meaning and replace only the CAN ID, byte and value. Names such as
`PDC_signal` remain acceptable discovery labels, but need a clear event or status meaning
before they cross the maintained-profile boundary.

---

## Safety and expectations

Vehicle profiles are experimental.

A profile may be incomplete, wrong, or specific to a trim, module coding, model year, or
retrofit state. `open-mmi` should not be treated as safety-critical software.


See also: [`docs/profile-ownership.md`](profile-ownership.md).

## Status-path compatibility aliases

Scalar status rules may define temporary aliases while a decoded field is being renamed:

```json
{
  "id": "0x3E3",
  "byte": 4,
  "type": "bool",
  "path": "climate.recirculation_active",
  "aliases": ["climate.front_demist_air_request"],
  "raw_path": "climate.recirculation_raw",
  "raw_aliases": ["climate.front_demist_air_request_raw"],
  "mask": "0x80",
  "true": "0x80",
  "false": "0x00"
}
```

`aliases` and `raw_aliases` may be a string or a list of strings. The decoder publishes the
same value to the canonical and alias paths. Use aliases only for planned schema migrations;
new profile rules should otherwise have one canonical path.

The Seat 1P `0x3E3` bit previously named `front_demist_air_request` is now identified as the
HVAC recirculation state. `climate.recirculation_active` is the canonical field. The former
field remains as a temporary alpha compatibility alias for existing UI/status consumers.
