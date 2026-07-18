# V1 runtime hardening design set

| Field | Value |
| --- | --- |
| Source branch | `v1-runtime-hardening` |
| Intended target | `main` |
| Status | In progress |
| Predecessor | `v1-desktop-shell` |
| Next planned phase | `v1-update-management` |

## Purpose

This branch hardens the installed dashboard runtime before update-management features are added. It addresses reliability issues found during desktop-shell qualification without changing vehicle-control scope or bypassing hardware safety protections.

The design set covers:

- stale frontend assets after an Open MMI update;
- dashboard and Jellyfin recovery without manual browser refreshes;
- interface selection recovery for touchscreen-only installations;
- visible thermal, CPU-frequency, battery, and charging diagnostics;
- removal of background work that has no user-visible benefit;
- installation guidance for tablets used in hot vehicle environments.

## Design documents

- [`frontend-versioning.md`](frontend-versioning.md)
- [`service-reconnection.md`](service-reconnection.md)
- [`interface-selection-recovery.md`](interface-selection-recovery.md)
- [`thermal-diagnostics.md`](thermal-diagnostics.md)
- [`runtime-performance.md`](runtime-performance.md)
- [`vehicle-tablet-cooling.md`](vehicle-tablet-cooling.md)

## Decision principles

1. **Correctness before convenience.** A successful update must not leave the browser executing an older frontend.
2. **Recover in place.** A temporary local-service failure should not require the user to close or manually refresh the dashboard.
3. **Observe before tuning.** Diagnostics must make clock, temperature, and charging behaviour visible before performance trade-offs are introduced.
4. **Remove waste globally.** Work that does not affect usability should be eliminated for every system.
5. **Make trade-offs explicit.** Reduced refresh rates or visual effects require measured justification and an explicit setting.
6. **Respect firmware protection.** Open MMI must never disable thermal limits, charging protection, or other platform safety controls.
7. **Keep cooling independent.** Physical cooling must continue to operate when the dashboard is closed, suspended, restarting, or unresponsive.

## Implementation order

1. Frontend version identity and cache-safe reload behaviour. **Implemented and qualified.**
2. Dashboard and Jellyfin reconnection state machines. **Implemented; pending laptop/Surface qualification.**
3. Touch-safe interface selection and TUI recovery. **Implemented; pending Surface qualification.**
4. Thermal and power diagnostics. **Implemented; pending Surface qualification.**
5. No-usability-impact runtime efficiency changes. **First browser pass implemented; pending laptop/Surface comparison and separate CAN profiling.**
6. Qualification on laptop and Surface Pro hardware.
7. Documentation promotion and branch merge.

This order ensures that later update-management work can rely on a proven version endpoint and controlled browser reload path.

## Non-goals

This branch does not initially include:

- unattended or scheduled software updates;
- automatic rollback;
- CAN transmission or vehicle control;
- disabling platform thermal protection;
- a mandatory low-power mode;
- software-controlled cooling hardware;
- redesigning the Media page solely for visual preference.

A low-power mode may be designed later only if measurements show that meaningful responsiveness or visual-quality trade-offs remain after waste has been removed.

## Qualification gates

The branch is ready to merge when:

- a changed frontend build is loaded without clearing the Chromium profile;
- a dashboard-server restart results in at most one controlled reload when the build changed;
- a Jellyfin restart recovers without reloading Open MMI;
- a touchscreen-only user can return from the TUI to the Web Dashboard without terminal commands;
- navigation and unsaved configuration input are not destroyed by routine service recovery;
- thermal and power data are available in Diagnostics when the platform exposes them;
- unavailable sensors degrade cleanly to `Unavailable` rather than breaking the page;
- Diagnostics polling stops when its page is not visible;
- no-usability-impact optimisations pass existing interaction and browser tests;
- cold-condition vehicle behaviour remains at least as good as the merged desktop-shell checkpoint;
- hot-condition testing does not bypass or conceal platform throttling.

## Documentation lifecycle

After merge, this index should record the merge commit or release tag and change status to `Implemented`. Stable operator-facing behaviour must then be copied into permanent documentation. Any proposal that did not ship should remain visible here as deferred or superseded.
