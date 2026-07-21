# Open MMI vehicle integration standard

This standard keeps vehicle integrations interchangeable, reviewable and reusable.
A vehicle profile describes how manufacturer-specific CAN signals map into Open MMI's
canonical vocabulary. It does not describe which Python function should run.

> **The registry is a continuity checkpoint, not a walled garden.**

Anyone may research a CAN signal, share provisional findings and propose a new concept.
The checkpoint applies when a signal enters a maintained profile: reuse an existing shared
human meaning when one fits, or add a genuinely new universal descriptor in the same pull
request as the mapping. No separate permission request is required.

Open MMI is where hexadecimal vehicle data meets human form. Canonical names must be
clearer than the CAN data they replace, not a second layer of obscure machine terminology.
See [`vehicle-contribution-workflow.md`](vehicle-contribution-workflow.md) for the complete
discovery, reuse and proposal workflow.

## The three layers

```text
Vehicle-specific CAN signal
        ↓ profile decoding
Canonical Open MMI event or status
        ↓ bindings / consumers
Application behavior
```

Each layer has one responsibility:

1. **Vehicle profile** — CAN IDs, bytes, values, masks, scaling and bus metadata.
2. **Canonical registries** — universal event intent and persistent-status contracts.
3. **Bindings and consumers** — application actions and interfaces that use those contracts.

For example, Seat and Vauxhall may encode a steering-wheel mute request differently:

```json
{
  "id": "0x5C1",
  "byte": 0,
  "value": 43,
  "event": "mute_toggle"
}
```

```json
{
  "id": "0x231",
  "byte": 3,
  "value": 30,
  "event": "mute_toggle"
}
```

Both profiles emit the same universal intent. The binding remains independent:

```json
{
  "mute_toggle": {
    "module": "audio",
    "func": "mute_toggle"
  }
}
```

A profile entry such as `vauxhall_steering_volume_off` is not acceptable when
`mute_toggle` already describes the intent.

## Canonical event rules

The authoritative machine-readable source is:

```text
canbusd/data/vehicle-events.v1.json
```

The generated reference is:

```text
docs/vehicle-event-registry.md
```

Canonical event identifiers:

- describe intent or a state transition, not implementation;
- have one immutable meaning across all vehicles;
- do not contain a manufacturer, model, CAN ID, module or function name;
- declare whether they carry a payload;
- declare edge, repeatable, value or state-transition delivery semantics; and
- are added to the registry before a maintained profile or binding uses them.

Aliases are migration diagnostics only. New profiles and bindings must use the canonical
identifier directly.

## Canonical status rules

The authoritative machine-readable status source is:

```text
canbusd/data/vehicle-statuses.v1.json
```

Its generated reference is `docs/vehicle-status-registry.md`. A status path describes state
that remains meaningful between frames. Its contract records the value type, unit, bounds,
nullability and lifecycle independently of the vehicle-specific CAN decoder.

For example, different vehicles can decode different frames into the same boolean path:

```text
doors.front_right = true
```

Stable paths are consumer-facing API. `experimental` paths preserve useful interpretations
that still need confirmation. `diagnostic` paths retain raw evidence and are not stable UI
contracts. Deprecated aliases may be emitted only where a profile explicitly identifies them
as compatibility aliases.

## Event payloads

A profile rule with an exact `value` emits an event without a payload:

```json
{
  "id": "0x231",
  "byte": 3,
  "value": 30,
  "event": "mute_toggle"
}
```

A profile rule with `"value": "any"` forwards the selected CAN byte as the event payload.
It may therefore be used only with an event that declares a payload contract:

```json
{
  "id": "0x470",
  "byte": 2,
  "value": "any",
  "event": "brightness_level"
}
```

The `brightness_level` registry contract is an integer percentage from 0 to 100. A new
vehicle profile is responsible for decoding or transforming its vehicle-specific signal
into that canonical range. Raw manufacturer codes must not leak into the universal event
contract.

Presence transitions do not carry payloads and therefore may emit only no-payload events.

## Reuse or propose; do not invent a private dialect

Before proposing a new event, an integration author checks whether an existing event already
expresses the same intent. Differences in CAN ID, byte, value, button label or vehicle
terminology do not justify a second name.

When no existing event accurately describes the confirmed human concept, the contributor
may add a new universal entry to the registry in the same pull request as the profile. The
review checks clarity, event-versus-status classification, payload semantics and reuse across
manufacturers. It is not an approval gate for CAN research.

Raw captures, unknown bytes, manufacturer abbreviations and provisional names remain valid
in discovery notes. Ad hoc unregistered names are rejected only at the maintained profile
and binding boundary, where continuity becomes part of Open MMI's public interface.

A vendor extension may be proposed only when the underlying capability is genuinely not
universal. It still requires a registry entry, documentation and tests.

## Review checklist for a new profile

A maintained profile contribution must answer all of the following:

1. What vehicle, platform, model years, trim and module coding were tested?
2. Which physical bus and capture point were used?
3. Which CAN frames were observed, replayed and verified on a vehicle?
4. Which canonical event does each control represent?
5. Does any `value: "any"` rule satisfy the registry payload type, range and unit?
6. Are new event names truly universal and already registered?
7. Are uncertain signals clearly marked rather than guessed?
8. Does the profile pass registry validation and replay tests?
9. Does the default binding use canonical event keys only?
10. Does documentation explain omissions and known limitations?

## Tooling

Inspect the complete event registry:

```bash
open-mmi-config vehicle-setup events
```

Search by ordinary human wording:

```bash
open-mmi-config vehicle-setup events --search mute
open-mmi-config vehicle-setup events --search "audio volume"
```

Check whether to reuse or propose an identifier:

```bash
open-mmi-config vehicle-setup events --check mute_toggle
open-mmi-config vehicle-setup events --check pdc_signal
```

Inspect one exact event:

```bash
open-mmi-config vehicle-setup events mute_toggle
```

Search, check or inspect persistent status paths:

```bash
open-mmi-config vehicle-setup statuses --search "right door"
open-mmi-config vehicle-setup statuses --search pdc_signal
open-mmi-config vehicle-setup statuses --check doors.front_right
open-mmi-config vehicle-setup statuses parking.distance.rear_left
```

Regenerate the references after a registry change:

```bash
python tools/generate_vehicle_event_docs.py
python tools/generate_vehicle_status_docs.py
```

Verify that generated documentation is current:

```bash
python tools/generate_vehicle_event_docs.py --check
python tools/generate_vehicle_status_docs.py --check
```

Run the conformance tests:

```bash
PYTHONPATH=.:tests python -m unittest tests.test_vehicle_events tests.test_vehicle_setup
```

## Change control

The registry is an API. Once a stable event has shipped:

- its identifier and meaning remain stable;
- narrowing or changing its payload contract requires a new event;
- renaming uses an explicit deprecated alias and migration plan;
- removals require a major compatibility decision; and
- generated documentation and conformance tests must change in the same commit.
