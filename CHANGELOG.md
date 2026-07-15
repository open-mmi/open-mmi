# Changelog

## Unreleased — V1 foundation hardening

### Added
- GitHub Actions for Python, packaging, browser, JavaScript, CSS, and live dashboard checks.
- Virtual-CAN, daemon lifecycle, action boundary, status publication, and browser interaction coverage.
- Installable Python package with console entry points and complete runtime assets.
- Playwright coverage for navigation, overlays, persistence, media selection, responsive layouts, and browser errors.

### Changed
- Split dashboard media backends into Radio, USB, Jellyfin, and Bluetooth providers.
- Split frontend API, preferences, status, navigation, overlays, vehicle rendering, media controllers, and CSS into focused modules.
- Moved stateful CAN rule data into explicitly owned runtime state.
- Made `climate.recirculation_active` the canonical status field.

### Security
- Pinned validated radio DNS addresses through connection and redirects.
- Opened USB media through descriptor-relative, no-follow traversal.
- Bounded Jellyfin JSON/image reads and hardened authentication-cache lifecycle.
- Isolated subscriber and persistence failures from CAN reception.

### Compatibility
- The legacy `climate.front_demist_air_request` status field remains temporarily as an alias of `climate.recirculation_active`.
