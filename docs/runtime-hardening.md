# Runtime hardening

This document describes the stable runtime behaviour introduced by the
`v1-runtime-hardening` milestone. The branch-specific design record remains in
[`docs/design/v1-runtime-hardening`](design/v1-runtime-hardening/README.md).

## Frontend updates and browser cache

The dashboard gives each deployed frontend build a unique identity. The server
exposes that identity through an uncached `/api/version` endpoint and injects it
into local JavaScript and CSS URLs.

When an installed update changes the build:

1. the already-running dashboard detects the new server build;
2. active form editing can defer the reload;
3. Chromium performs one controlled reload;
4. the new frontend assets load without deleting the managed browser profile.

A server restart with the same build reconnects in place and does not reload the
page. Settings → System shows the user-facing dashboard/server versions and
update state. Diagnostics retains the detailed loaded-versus-server comparison.

The first update from a frontend that predates this controller cannot initiate
its own reload and may require one normal or forced refresh. Later updates use
the automatic path.

## Dashboard-server recovery

The browser owns one shared dashboard connection state. A transport failure:

- keeps the current page, readings, navigation and unsaved forms mounted;
- stops the high-frequency vehicle-status poller;
- displays a non-blocking reconnecting banner;
- temporarily disables controls that require the server;
- retries `/api/health` with bounded backoff;
- pauses retries while the document is hidden.

When the server returns, version reconciliation runs before normal polling
resumes. Ordinary HTTP errors are not treated as a lost server connection.

## Jellyfin recovery

Jellyfin recovery is independent from dashboard-server recovery. During a
provider outage the Media page keeps the last successful library visible and
moves into a reconnecting state. Retry delays are bounded, pause outside the
active Media page, and stop for missing configuration or rejected credentials.
The active library refreshes automatically when Jellyfin returns. Restarting
Jellyfin does not require reloading Chromium.

## Interface recovery

The normal **Open MMI** launcher uses the remembered Web Dashboard or Terminal
UI preference. The independent **Open MMI Interface Chooser** application-menu
entry always opens the chooser and ignores that default.

Graphical TUI sessions are guarded. Closing or failing the TUI returns to the
chooser, allowing a touchscreen-only user to reopen the Web Dashboard without a
terminal command. Choosing an interface once is temporary unless the user
explicitly confirms that it should be remembered.

Linux Mint terminal wrappers are resolved to their native terminal executable
where available so the TUI command is launched rather than leaving an idle
shell in `/opt/open-mmi`.

## Thermal, power and activity diagnostics

Settings → Diagnostics exposes read-only runtime information when Linux provides
it:

- current, minimum and maximum CPU frequencies;
- load context;
- thermal zones and reported trip points;
- cooling-device state;
- AC and battery state;
- Intel `pstate` detail;
- session-observed clock and temperature ranges;
- dashboard connection and recovery counters;
- status-fetch, render-suppression and Media-layout counters.

The endpoint reads only fixed allowlisted `/sys` and `/proc` properties. Missing
or unsupported data renders as unavailable. Polling runs only while Diagnostics
is active and the document is visible.

The throttling label is deliberately conservative: low clocks alone are normal
at idle. The dashboard requires repeated near-minimum clocks under material load
and only names temperature as the cause when a thermal trip is active too.
Reported battery-side `power_now` is not presented as charger capacity.

## Runtime efficiency

The visible vehicle-status cadence remains 200 ms. Runtime hardening reduces
work without reducing that responsiveness:

- status requests cannot overlap and pause while Chromium is hidden;
- unchanged vehicle state skips the full render path;
- unchanged text, attributes and tell-tale markup are not rewritten;
- Media layout is event-driven and stops outside the active Media page;
- permanent layout, tell-tale-maintenance and media-key probe timers were
  removed or bounded;
- Diagnostics updates stable DOM nodes instead of rebuilding the panel.

No low-power mode is enabled by default. A performance toggle should be added
only if later measurement demonstrates a real responsiveness or visual-quality
trade-off.

## Known limitations and deferred work

- Thermal firmware protections are not bypassed or altered.
- Passively cooled tablets may still throttle in hot vehicle installations.
- Charging may be suspended by the device while hot even though AC remains
  connected.
- Cooling hardware and fan control are independent of Open MMI.
- CAN-daemon profiling and optimisation remain separate from this browser pass.
- Update download, installation, rollback and release-channel management belong
  to the later `v1-update-management` milestone.

See [`vehicle-tablet-installation.md`](vehicle-tablet-installation.md) for safe
installation and cooling guidance.
