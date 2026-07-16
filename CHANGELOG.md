# Changelog

## Unreleased — V1 foundation hardening

### Added
- Dashboard System settings for the remembered launcher UI and dashboard start-at-login state.
- Secure Jellyfin setup through the dashboard and the new `open-mmi-config` CLI.
- Private `~/.config/open-mmi/dashboard.env` service configuration with connection testing and fixed-action dashboard restart.
- GitHub Actions for Python, packaging, browser, JavaScript, CSS, and live dashboard checks.
- Virtual-CAN, daemon lifecycle, action boundary, status publication, and browser interaction coverage.
- Installable Python package with console entry points and complete runtime assets.
- Playwright coverage for navigation, overlays, persistence, media selection, responsive layouts, and browser errors.

### Changed
- The dashboard service now loads its user-owned environment file and the installer exposes `open-mmi-config` with the other packaged commands.
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
