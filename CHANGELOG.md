# Changelog

## Unreleased — V1 update management

### Added
- Managed `/opt/open-mmi/.update-source.json` metadata recording the managed source checkout, nightly channel, branch, upstream, installed commit, and installed version.
- Local-only update status, readiness, coordinator status, manual check, candidate preparation, and confirmed installation endpoints.
- Settings → System visibility and fixed controls for checking, preparing, and installing a managed nightly candidate with live transaction state.
- Branch-specific update source, API, UI, execution, rollback, health, and permission design records.
- Root-owned `/etc/open-mmi/update-policy.json` with fixed `stable`, `beta`, and `nightly` channel selection plus automatic migration from the legacy `development` label.
- Administrative `open-mmi-config updates status`, `updates check`, and `updates channel` commands.
- Read-only pre-update readiness inspection through `GET /api/system/update-readiness` and `open-mmi-config updates readiness`.
- Fail-closed disk, command, coordinator, transaction-lock, configuration-preservation, power, thermal, and service restart-loop checks.
- Root-owned update coordinator service with atomic persistent state, crash recovery, exclusive transaction locking, and fixed status/prepare/install Unix-socket actions.
- Restricted candidate preparation with fixed confirmation, root-owned staging, forward-ancestry proof, release-tag identity validation, and persistent preparation state.
- Confirmed CLI and same-origin browser nightly candidate installation through a no-arguments one-shot root service, with identity/ancestry revalidation, deployment backup, fixed health checks, and automatic restoration on failure.
- Automatic transaction-artifact cleanup with one active/prepared staging tree and two retained rollback archives.
- Stable/beta semantic release-tag filtering, official-repository enforcement, downgrade refusal, and rewritten-tag detection.

### Security
- Update checks accept no browser-selected repository, path, remote, branch, ref, timeout, or command.
- Git credential prompts are disabled, checks use bounded argument-list subprocesses, and raw remote errors are not exposed to the browser.
- A remote commit mismatch is reported conservatively when update direction cannot be proven without changing the checkout.
- Channel policy rejects symlinks, writable files, unknown fields, unsupported channels, non-root production ownership, untrusted release remotes, and browser-selected source data.
- Git inspection invoked through `sudo open-mmi-config` drops back to the original user before reading the user-owned checkout.
- Browser execution accepts only exact confirmation objects over literal-loopback, same-origin JSON routes and delegates to the fixed coordinator protocol; it cannot select update inputs or pass DNS-rebinding hostnames.
- Coordinator handoff completes even when the dashboard connection closes during its expected self-restart.
- Artifact pruning accepts only contained, non-symlinked coordinator transaction directories and leaves unrelated entries untouched.

### Not yet included
- No browser channel editor, scheduling, unattended updates, stable/beta installation, or caller-selected/manual rollback target.

## Unreleased — V1 runtime hardening

### Added
- Build-aware frontend identity, versioned local assets, `/api/version`, and one-shot automatic reload after installed updates.
- Shared dashboard connection recovery with bounded health backoff and in-place same-build restart recovery.
- Jellyfin provider reconnection without reloading Chromium.
- Touch-safe **Open MMI Interface Chooser** and guarded graphical TUI recovery.
- Read-only thermal, CPU-frequency, power, charging, cooling-device, and runtime activity diagnostics.
- Branch-specific design records plus permanent runtime-hardening and vehicle-tablet installation guidance.

### Changed
- User-facing version and update state now appear in Settings → System; lower-level build comparison remains in Diagnostics.
- Vehicle rendering skips unchanged state while retaining the visible 200 ms status cadence.
- Media layout, tell-tale maintenance, media-key setup, Diagnostics polling, and retry work now follow page/document visibility and explicit ownership.
- Server-backed controls pause during dashboard transport loss without destroying navigation or unsaved forms.

### Fixed
- Managed Chromium no longer requires routine cache/profile clearing after later updates.
- Diagnostics fields remain mounted instead of flashing from repeated panel reconstruction.
- Settings → System no longer remains stuck on “loading desktop shell status”.
- Linux Mint terminal-wrapper handling now launches the actual TUI instead of an idle shell in `/opt/open-mmi`.
- Touchscreen users can return from a remembered TUI default without terminal commands.

### Known limitations
- The first update from a frontend that predates the version controller may require one manual reload.
- Hot, passively cooled tablets may still throttle and suspend charging; firmware protections are not bypassed.
- CAN-daemon profiling, cooling hardware, and update download/rollback management remain later work.

## Unreleased — V1 foundation hardening

### Added
- Dashboard System settings for the remembered launcher UI and graphical-login application autostart.
- Secure Jellyfin setup through the dashboard and the new `open-mmi-config` CLI.
- Private `~/.config/open-mmi/dashboard.env` service configuration with connection testing and fixed-action dashboard restart.
- GitHub Actions for Python, packaging, browser, JavaScript, CSS, and live dashboard checks.
- Virtual-CAN, daemon lifecycle, action boundary, status publication, and browser interaction coverage.
- Installable Python package with console entry points and complete runtime assets.
- Playwright coverage for navigation, overlays, persistence, media selection, responsive layouts, and browser errors.

### Changed
- The dashboard service now loads its user-owned environment file; fresh installs start it on demand, graphical-login application launch is user-configurable, and advanced service enablement remains in `open-mmi-config`.
- Split dashboard media backends into Radio, USB, Jellyfin, and Bluetooth providers.
- Split frontend API, preferences, status, navigation, overlays, vehicle rendering, media controllers, and CSS into focused modules.
- Moved stateful CAN rule data into explicitly owned runtime state.
- Moved subprocess-backed actions onto a bounded single-worker queue so CAN reception remains responsive.
- Routed steering-wheel media transport through BlueZ/MPRIS-aware actions with a synthetic-key fallback.
- Expanded Diagnostics to use canonical profile paths and list every currently decoded state value.
- Made `climate.recirculation_active` the canonical status field.

### Security
- Restricted configuration APIs to loopback, same-origin requests and never return stored Jellyfin passwords or tokens.
- Write dashboard credentials atomically with mode `0600`, reject symlink targets, and keep secrets out of browser storage and command arguments.
- Pinned validated radio DNS addresses through connection and redirects.
- Opened USB media through descriptor-relative, no-follow traversal.
- Bounded Jellyfin JSON/image reads and hardened authentication-cache lifecycle.
- Isolated subscriber and persistence failures from CAN reception.

### Compatibility
- The legacy `climate.front_demist_air_request` status field remains temporarily as an alias of `climate.recirculation_active`.
