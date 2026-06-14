# Status snapshot

`open-mmi` publishes decoded vehicle state as a local status snapshot.

This snapshot is the boundary between the backend daemon and UI/dashboard consumers.

```text
CAN frames
  ↓
vehicle profile decoding
  ↓
status_bus
  ↓
status snapshot
  ↓
CLI dashboard / future UI consumers
```

## Current status

The status snapshot interface is currently alpha.

It is useful for the included CLI dashboard and early UI work, but the schema may change before a stable public release.

Consumers should handle missing, unknown, stale, or extra fields gracefully.

## Current snapshot path

When `XDG_RUNTIME_DIR` is available, the current runtime snapshot path is:

```text
$XDG_RUNTIME_DIR/open-mmi/status.json
```

For a typical user session this may resolve to something like:

```text
/run/user/1000/open-mmi/status.json
```

If `XDG_RUNTIME_DIR` is not available, the fallback path is:

```text
/tmp/open-mmi-status.json
```

The included CLI dashboard uses the same lookup behaviour.

## Current top-level shape

The status snapshot is currently written as a wrapper object:

```json
{
  "updated_at": "2026-06-14T12:34:56.000000+00:00",
  "state": {}
}
```

`updated_at` records when the snapshot file was written.

`state` contains the decoded vehicle state published by the daemon.

## Purpose

The snapshot exists so UI consumers do not need to read raw CAN frames directly.

A UI should consume human-readable vehicle state such as:

```text
state.vehicle.present
state.vehicle.reverse
state.vehicle.handbrake
state.lighting.mode
state.lighting.dimmer_percent
state.doors.any_open
state.steering.angle_degrees
```

not raw CAN IDs and bytes.

Vehicle-specific CAN knowledge belongs in:

```text
vehicles/<profile>/config.json
```

not in UI code.

## Example state

A snapshot may contain state like:

```json
{
  "updated_at": "2026-06-14T12:34:56.000000+00:00",
  "state": {
    "vehicle": {
      "present": true,
      "reverse": false,
      "handbrake": true,
      "brake": false
    },
    "doors": {
      "front_left": false,
      "front_right": false,
      "rear_left": false,
      "rear_right": false,
      "boot": false,
      "bonnet": false,
      "any_open": false,
      "raw": 0
    },
    "lighting": {
      "mode": "dip",
      "mode_raw": 195,
      "dimmer_percent": 42,
      "dimmer_raw": 42,
      "indicator": "off",
      "hazards": false,
      "bulb_fault": false
    },
    "steering": {
      "angle_degrees": 0.0,
      "direction": "center",
      "magnitude_degrees": 0.0,
      "raw": 0
    }
  }
}
```

This example is illustrative. The exact fields depend on the active vehicle profile and decoded status rules.

## Field behaviour

Consumers should assume:

* fields may be missing
* values may be `null`
* unknown states may be reported as `"unknown"`
* raw debug values may exist alongside decoded values
* profile-specific fields may appear
* future versions may add fields

Consumers should not crash if a field is missing.

## Raw values

Profiles may publish raw values using paths such as:

```text
state.lighting.mode_raw
state.vehicle.handbrake_raw
state.steering.raw
```

Raw values are useful for debugging and profile development.

UI consumers may display raw values in debug modes, but normal user-facing UI should prefer decoded values.

## Freshness

`updated_at` should be used as a basic freshness indicator.

A UI should treat the snapshot as live vehicle state, not permanent truth.

If the snapshot is missing, invalid, or old, a UI should show a safe disconnected/stale state rather than displaying stale data as if it is current.

Future versions may expose clearer freshness metadata, such as:

```text
snapshot_age_ms
source_vehicle_profile
daemon_state
schema_version
```

Until that is stable, consumers should handle stale or missing snapshots safely.

## Safety

Decoded status is informational.

It must not be treated as a replacement for OEM warnings, diagnostics, safety systems, or driver judgement.

Incorrect profile mappings may misrepresent vehicle state.

## Consumer guidance

A dashboard or UI consumer should:

* read the status snapshot
* display decoded state
* handle missing fields
* handle stale or absent snapshots
* avoid parsing raw CAN frames directly
* avoid hardcoding vehicle-specific CAN IDs
* clearly label debug/raw values

## Stability promise

Before a stable release, the status snapshot schema may change.

After a stable schema is declared, breaking changes should be documented and versioned.
