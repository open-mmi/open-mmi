# Runtime performance and background-work policy

| Field | Value |
| --- | --- |
| Branch | `v1-runtime-hardening` |
| Status | Implemented on branch — browser pass complete; CAN profiling deferred |
| Owners | Dashboard frontend, dashboard server, CAN daemon |

## Context

Hot-condition Surface Pro qualification exposed a thermal feedback loop: sustained dashboard and CAN work contributed heat, platform firmware reduced the CPU to approximately 400 MHz, and the same work then occupied a much larger share of the reduced capacity.

The cold-condition vehicle test passed, so this design does not assume that the desktop-shell branch introduced a universal performance regression. It establishes rules and measurement so avoidable work can be removed without degrading responsive vehicle information.

The current frontend includes a 200 ms vehicle-status polling path plus several Media timers, animation frames, geometry measurements, and mutation observers. These are candidates for measurement and lifecycle ownership, not automatic proof that every interval is wrong.

## Implemented first pass

The first runtime-efficiency slice keeps the existing 200 ms visible status cadence and removes work that does not change the user experience:

- `/api/status` requests cannot overlap; a slow response is allowed to finish before another request is accepted;
- status polling pauses while the browser document is hidden and resumes with one immediate refresh;
- vehicle health remains current, while unchanged vehicle values skip the full non-health render path;
- text, attributes, tell-tale SVG markup, tachometer CSS properties, coolant state, and voltage markup are written only when their values change;
- driver-facing cleanup is event-driven rather than rescanning the dashboard on every status response;
- Jellyfin Media no longer runs an unconditional one-second page/layout loop;
- Media layout work runs only while Media is active and visible, on navigation, resize/orientation, provider-content change, or initial construction;
- broad Media mutation observers were removed in favour of explicit layout events;
- Media-key installation uses bounded startup retries plus page/content events instead of a permanent 1.5-second probe;
- tell-tale test maintenance is event-driven rather than using permanent 750 ms and one-second timers.

Settings → Diagnostics exposes session counters for status fetches and overlap suppression, vehicle renders and unchanged-state skips, and Media layout requests/runs. These counters are read only while Diagnostics is already polling.

This pass deliberately does not change the visible status interval, animation quality, media progress event handling, or CAN daemon behaviour.

## Principles

1. Remove work that produces no visible or behavioural change.
2. Keep safety-relevant and driver-relevant status responsive.
3. Give every recurring task one owner and an explicit stop path.
4. Inactive pages do not perform page-specific rendering or layout work.
5. Hidden documents suspend nonessential polling and retries.
6. Do not rebuild static forms to refresh live status.
7. Do not introduce a low-power toggle until measured trade-offs remain.
8. Optimise browser and CAN workloads separately so improvements are attributable.

## Global efficiency changes

The following do not require a user setting when implemented correctly:

- skip DOM writes when the rendered value and state class are unchanged;
- publish or notify subscribers only when their relevant state changed;
- prevent overlapping fetches;
- cancel obsolete requests where safe;
- stop page-owned timers when leaving the page;
- disconnect page-owned observers when their target is inactive or removed;
- replace recurring geometry checks with resize, orientation, navigation, or actual-content-change events;
- preserve static settings DOM while updating only live values;
- pause nonessential work while the document is hidden;
- coalesce multiple layout requests into one animation frame;
- avoid duplicate status or provider controllers.

These changes should make every platform cooler without altering user-visible refresh behaviour.

## Work ownership

### Shared vehicle status

- One status client owns `/api/status` polling.
- At most one request may be in flight.
- Subscribers receive a monotonically increasing snapshot identity.
- Subscribers may declare the fields they depend on or perform a cheap equality check.
- A subscriber does not rerender when its relevant values did not change.

The existing 200 ms interval may remain during the first optimisation pass if request, publish, and render suppression materially lower workload. Any later change to the driver-visible refresh interval requires comparison testing.

### Navigation and inactive pages

- Page-specific controllers start on `openmmi:pagechange` when their page becomes active.
- They stop on page exit.
- A hidden page may retain DOM and state but cannot continue periodic layout work.
- Settings panels update only their active live section.

### Media providers

- Only the active enabled media provider performs routine status/browse refreshes.
- Jellyfin layout fitting is event-driven, not an unconditional one-second task.
- Media-key binding probes stop after successful installation and do not run forever.
- Configuration forms remain outside provider refresh targets.
- Mutation observers must have a named owner, a narrow target, and a disconnect path.

### Clock

The clock remains minute-aligned and event-driven. It must not become a high-frequency polling source.

### Diagnostics

Thermal and performance diagnostics poll only while their panel is active and visible. Instrumentation must not materially change the workload being measured.

### CAN daemon

CAN optimisation is measured separately from the browser. Investigation should distinguish:

- interface discovery and reconnect loops;
- frame receive rate;
- decode cost;
- status snapshot serialisation and write rate;
- subscriber/event publication;
- logging;
- idle behaviour while `can0` is absent.

The daemon's sleep-and-reconnect behaviour when `can0` drops is expected. PID changes caused by a deliberate service restart or reconnection lifecycle are not themselves a performance defect.

## Instrumentation

Add development/Diagnostics counters that can be read without browser developer tools:

```text
Status fetches
Status fetch failures
Status publishes
Unchanged snapshots skipped
Page renders
DOM fields changed
Media provider requests
Active timers
Long tasks over 50 ms
Last render duration
```

Counters may be session-only. Production UI should hide detailed developer counters behind Diagnostics raw/debug visibility.

Browser instrumentation should use lightweight counters and, where supported, `PerformanceObserver` for long tasks. It must not add continuous high-frequency sampling.

## Measurement method

Record conditions with every performance result:

- hardware and kernel;
- ambient/cabin condition;
- tablet cold, warm, or thermally limited;
- CPU current and configured frequency range;
- charging state;
- dashboard page;
- CAN absent, idle, or active;
- active media provider;
- Chromium renderer and GPU CPU;
- `canbusd` CPU;
- sample duration.

Do not compare raw CPU percentages from a 400 MHz throttled state directly with percentages at 3 GHz without recording the clock state.

## Baseline scenarios

At minimum:

1. Dashboard closed, CAN absent.
2. Dashboard closed, CAN active.
3. Dashboard open on Home/Drive, CAN active.
4. Dashboard open on Media with each provider idle.
5. Dashboard open on Settings → Diagnostics.
6. Jellyfin unavailable and retrying.
7. Document hidden for at least one minute.
8. Resume from suspend.
9. Hot-condition thermal limit, for observation only.

## Optional performance mode

Do not add a toggle for pure waste removal.

An optional `Performance / Auto / Cool` design may be considered only if post-optimisation measurements show that meaningful trade-offs remain, such as:

- changing driver-visible status latency;
- reducing animation quality;
- lowering media progress-update frequency;
- reducing diagnostics detail;
- changing background service behaviour.

Any such setting requires:

- a documented default;
- measurable effect;
- no hidden safety impact;
- clear UI wording;
- tests for every mode;
- an `Auto` policy that does not depend on Surface-specific sensor names.

## Tests

### Node

- one status request at a time;
- unchanged snapshots do not notify or rerender unnecessarily;
- page-owned timers start and stop with navigation;
- hidden-page lifecycle stops nonessential schedules;
- visibility restoration resumes once;
- provider controllers do not duplicate timers;
- configuration inputs remain mounted during live updates;
- media geometry work occurs on events rather than unconditional intervals.

### Playwright

- remain on each page for more than existing interval durations and verify stable timer/request counts;
- type into Jellyfin fields across status and provider refresh boundaries;
- leave Media and verify provider/layout activity stops;
- hide and restore the page and verify no burst of duplicate requests;
- exercise normal interaction with instrumentation enabled and disabled.

### Python

- CAN daemon idle and reconnect loops use bounded sleep/backoff;
- status publication can suppress identical snapshots where contract-safe;
- instrumentation counters do not alter vehicle read-only guarantees;
- performance benchmark tooling remains reproducible.

## Acceptance criteria

- No inactive page performs recurring layout reconstruction.
- No routine live update destroys editable controls.
- Hidden-page nonessential request rates fall to zero or a documented minimal health check.
- Existing driver interactions remain responsive in cold-condition vehicle testing.
- Any CPU reduction is attributable through counters and scenario comparison.
- No performance setting is introduced merely to hide avoidable work.

## Implementation outcome and deferred work

The first pass shipped without a user-facing performance mode and without reducing the visible 200 ms status cadence. It removes duplicate requests, writes, layout work and permanent maintenance timers, and exposes counters so the result can be checked without developer tools.

CAN-daemon profiling remains deferred. It must be measured separately from browser work before behaviour is changed. A low-power mode also remains deferred until measurements demonstrate a real user-visible trade-off after redundant work has been removed.
