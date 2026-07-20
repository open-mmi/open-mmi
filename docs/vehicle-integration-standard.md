# Open MMI vehicle integration standard

This standard keeps vehicle integrations interchangeable, reviewable and reusable.
A vehicle profile describes how manufacturer-specific CAN signals map into Open MMI's
canonical vocabulary. It does not describe which Python function should run.

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
2. **Canonical registry** — universal event meaning and payload contract.
3. **Bindings** — module, function and configured arguments for an application action.

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

## Universal before vendor-specific

Before proposing a new event, an integration author must check whether an existing event
already expresses the same intent. Differences in CAN ID, byte, value, button label or
vehicle terminology do not justify a new event.

A vendor extension may be proposed only when the underlying capability is genuinely not
universal. It still requires a registry entry, documentation and tests. Ad hoc unregistered
names are rejected.

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

Inspect one event:

```bash
open-mmi-config vehicle-setup events mute_toggle
```

Regenerate the event reference after an approved registry change:

```bash
python tools/generate_vehicle_event_docs.py
```

Verify that generated documentation is current:

```bash
python tools/generate_vehicle_event_docs.py --check
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
