# Thermal, clock, and charging diagnostics

| Field | Value |
| --- | --- |
| Branch | `v1-runtime-hardening` |
| Status | Proposed |
| Owners | Dashboard server, Settings → Diagnostics |

## Problem

Hot-condition qualification on the Surface Pro 1796 showed a platform thermal event that was difficult to distinguish from an application fault without SSH:

- all four CPU threads fell to approximately 400 MHz;
- the platform `GEN4` zone crossed its active/passive trip near 48.05°C;
- Chromium and CAN work became visibly sluggish at the reduced clock;
- AC remained connected while battery status changed to `Not charging`;
- charging resumed automatically only after the tablet cooled.

The cold-condition vehicle test was healthy. The immediate requirement is therefore visibility: a user should be able to open Diagnostics and see whether the system is slow because of application work, platform clock restriction, temperature, or charging suspension.

## Goals

- Show CPU current, minimum, and maximum frequencies.
- Show available thermal zones and relevant trip points.
- Show AC connection, battery state, capacity, and charging status.
- Present cautious derived states such as `Warm`, `Thermal limit active`, or `Clock constrained`.
- Poll only while Diagnostics is visible.
- Work on non-Surface Linux systems and degrade cleanly when data is absent.
- Read only allowlisted local system files.

## Non-goals

- Changing governors, turbo settings, thermal trips, or charging policy.
- Claiming that every low CPU frequency is thermal throttling.
- Requiring Intel `pstate` or Surface-specific sensor names.
- Controlling fans in this branch.
- Persistently logging detailed thermal telemetry by default.

## Data sources

The server may read the following Linux interfaces when present.

### CPU frequency

Per online CPU:

```text
/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
/sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq
/sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq
/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

Optional Intel detail:

```text
/sys/devices/system/cpu/intel_pstate/status
/sys/devices/system/cpu/intel_pstate/no_turbo
/sys/devices/system/cpu/intel_pstate/min_perf_pct
/sys/devices/system/cpu/intel_pstate/max_perf_pct
```

### Thermal zones

For each zone:

```text
/sys/class/thermal/thermal_zone*/type
/sys/class/thermal/thermal_zone*/temp
/sys/class/thermal/thermal_zone*/trip_point_*_temp
/sys/class/thermal/thermal_zone*/trip_point_*_type
```

### Cooling devices

Optional diagnostic detail:

```text
/sys/class/thermal/cooling_device*/type
/sys/class/thermal/cooling_device*/cur_state
/sys/class/thermal/cooling_device*/max_state
```

### Power supplies

For allowlisted properties beneath `/sys/class/power_supply/*`:

```text
type
online
status
capacity
energy_now
energy_full
power_now
current_now
voltage_now
temp
```

### Load context

A low frequency while idle is normal. Derived clock-constrained states need load context from a read-only source such as `/proc/loadavg` or sampled `/proc/stat` utilisation.

## Server API

Add a read-only endpoint such as:

```text
GET /api/system/diagnostics/runtime
```

Example shape:

```json
{
  "sampled_at": "2026-07-16T22:29:54+01:00",
  "cpu": {
    "current_mhz": [400, 399, 400, 400],
    "minimum_mhz": 400,
    "maximum_mhz": 3500,
    "governor": "powersave",
    "load_1m": 6.21
  },
  "thermal": {
    "summary": "thermal-limit-active",
    "selected_zone": "GEN4",
    "temperature_c": 52.5,
    "nearest_trip_c": 48.05,
    "zones": []
  },
  "power": {
    "ac_online": true,
    "battery_status": "Not charging",
    "capacity_percent": 65,
    "energy_wh": 21.13
  }
}
```

The exact endpoint name may follow existing system-settings routing conventions, but it must remain read-only and return no arbitrary filesystem paths.

## Sensor selection

Do not hard-code `GEN4` or assume the hottest numeric sensor is the most relevant.

The summary sensor should be selected by useful thermal margin:

1. ignore unreadable or clearly invalid values;
2. prefer zones with valid active, passive, hot, or critical trip points;
3. calculate the margin between current temperature and the nearest applicable trip;
4. select the zone with the smallest positive margin or greatest exceeded margin;
5. expose every readable zone in expandable detail.

A zone without trip metadata may still be shown, but should not drive a confident `thermal-limit-active` label.

## Derived states

Derived states are advisory and must include enough raw values for the user to verify them.

### Temperature state

- `Unavailable`: no usable thermal zones.
- `Normal`: selected zone is comfortably below its nearest relevant trip.
- `Warm`: within approximately 3°C of a relevant trip.
- `Thermal limit active`: at or above an active or passive trip.
- `Hot`: at or above a reported hot trip.
- `Critical`: at or above a reported critical trip.

### Clock state

- `Normal/variable`: frequency is changing within the configured range.
- `Idle at minimum`: clocks are near minimum while load is low.
- `Clock constrained`: all or nearly all online CPUs remain near minimum for multiple samples while load is materially high.
- `Unknown`: frequency or load context is unavailable.

The UI must not label `Clock constrained` as definitely thermal unless a relevant thermal trip is also active. A combined state may say `Performance limited by temperature` only when both signals agree.

### Charging state

- `On battery`;
- `AC connected — charging`;
- `AC connected — not charging`;
- `AC connected — full`;
- `Unknown`.

`power_now` must not be presented as charger capacity. The Surface qualification data varied substantially while battery energy remained flat, so this field is driver-specific and should be labelled only as an instantaneous reported battery-side value when shown.

## Diagnostics UI

Suggested summary:

```text
Thermal and power

CPU clock:          400 MHz average
CPU range:          400–3500 MHz
CPU load:           High
Platform sensor:    GEN4 52.5°C
Relevant trip:      48.1°C passive/active
AC connected:       Yes
Battery:            65% — Not charging
System state:       Performance limited by temperature
```

Expandable details may show:

- every CPU frequency;
- every thermal zone and trip;
- cooling-device states;
- Intel `pstate` values;
- power-supply properties;
- minimum and maximum observed values for the current Diagnostics session.

## Sampling lifecycle

- Fetch only while Settings → Diagnostics is the active visible panel.
- Default interval: 3 seconds.
- Stop immediately when leaving Diagnostics or when the document is hidden.
- On return, fetch once immediately before restarting the interval.
- Keep session minima/maxima in browser memory; do not create a permanent background logger.
- Prevent overlapping requests.

## Security and portability

- The server reads from fixed allowlisted roots only.
- No request parameter may select a filesystem path.
- Symlinks resolving outside the expected system roots should not be followed blindly.
- Permission failures and missing files become unavailable fields, not server errors.
- The endpoint remains local-only under the dashboard's existing loopback model.
- Battery serial numbers, hardware identifiers, and unrelated device metadata are excluded.

## Tests

### Python

Use a configurable fake sysfs/proc root to test:

- CPU frequency aggregation;
- missing cpufreq support;
- valid and invalid thermal values;
- trip parsing and margin-based sensor selection;
- battery/AC discovery with different power-supply names;
- charging-state mapping;
- constrained-clock heuristic with high and low load;
- no arbitrary path access;
- stable JSON contract with partial data.

### Node

- Diagnostics starts polling only when visible and selected;
- leaving the panel cancels the timer;
- visibility restoration performs one immediate refresh;
- session minima/maxima update correctly;
- partial/unavailable data renders safely;
- `AC connected — not charging` is distinct from disconnected AC;
- no charger-wattage claim is derived from `power_now`.

### Playwright

- render normal, warm, throttled, and unavailable fixture states;
- navigate away for longer than the polling interval and verify no requests occur;
- return and verify one immediate request;
- confirm the rest of Settings remains usable while the diagnostics endpoint fails.

## Acceptance criteria

- The Surface thermal state can be recognised from the dashboard without SSH.
- Low idle clocks are not falsely reported as thermal throttling.
- Charging suspension is clearly visible while AC remains online.
- Platforms without Linux thermal or cpufreq data continue to run normally.
- Adding Diagnostics does not create another permanent background workload.
