# Open MMI V1 Roadmap

Open MMI V1 is the first complete public shape of the project: a local, read-only vehicle dashboard/MMI built from decoded vehicle state.

V1 is not a finished car operating system. It is the point where the project has a complete, usable loop:

```text
vehicle state → dashboard → media → settings → events/overlays → docs → compatibility testing path
```

## Current baseline

- Local web dashboard is now the main project face.
- Drive page shows live speed, RPM, coolant, voltage, range, outside temperature and lighting state.
- Media page supports optional Jellyfin-backed local playback and browser media keys.
- Climate page shows decoded HVAC-related state.
- Vehicle/status page shows doors, handbrake, reverse, indicators, hazards and related status.
- Footer tell-tales are stable and use local icon assets.
- Demo mode can run without a vehicle.
- SEAT León 1P is the confirmed reference vehicle.
- Dashboard is read-only from the vehicle side.

## Required before V1

### 1. Home/Menu navigation

Target layout:

```text
Media ← Home/Menu → Drive
```

Home/Menu should become the neutral landing page and provide quick access to:

- Drive
- Media
- Climate
- Settings
- Diagnostics/Vehicle

The first implementation should keep Drive and Media internals mostly untouched. The goal is to improve navigation around the existing pages, not rewrite the working pages.

### 2. Settings

Initial settings should cover:

- units, such as mph/kmh and °C/°F
- display preferences
- tell-tale test mode
- raw/debug visibility
- Jellyfin status
- reverse assist placeholder

Settings that are private or security-sensitive must stay server-side or environment-based. Tokens and service credentials must not be stored in frontend code.

### 3. Diagnostics cleanup

Move raw/unfiltered values out of driver-facing pages where possible.

Examples:

- outside unfiltered temperature
- snapshot age
- decoded lighting mode
- missing fields
- raw status link

Vehicle may become a Diagnostics/Status page, or parts of it may feed the Home page and event overlays.

### 4. Vehicle event overlays

Add a reusable overlay system for important vehicle events.

Initial overlays:

- door-open popup with an easy dismiss action
- reverse selected placeholder

The overlay system should not replace the footer tell-tales. Dismissed overlays should return only when the underlying state changes or resets.

### 5. Reverse assist foundation

V1 does not need a working camera/PDC implementation, but it should pave the way for one.

Initial setting/placeholder options:

- Off
- PDC only, placeholder
- Camera only, placeholder
- Camera + PDC, placeholder

The dashboard must remain read-only with respect to vehicle control.

### 6. Compatibility testing path

Document a temporary, read-only test process for other PQ35-family vehicles.

Wanted test vehicles:

- VW Golf Mk5
- Audi A3 8P
- Škoda Octavia 1Z
- Škoda Yeti

Compatibility claims should stay conservative until tested. The current confirmed vehicle remains SEAT León 1P.

### 7. V1 release docs

Before tagging V1:

- README screenshots are current and privacy-respecting.
- Demo mode works from a clean clone.
- No secrets, backup files or local debug junk are committed.
- Compatibility limits are clearly stated.
- Known limitations are documented.
- Jellyfin/media setup is optional and token-safe.
- Tell-tale asset attributions are present.

## Suggested version path

```text
v0.95
  Current dashboard beta merged to main, with screenshots/docs good enough for public testers.

v0.99
  Roadmap feature-complete: Home/Menu, Settings, overlays, diagnostics cleanup and compatibility docs.

v1.0
  First complete Open MMI release.
```

## V1 non-goals

These are explicitly after V1 unless they fall out naturally:

- full rear camera/PDC implementation
- maps/Pure Maps integration
- multi-vehicle confirmed PQ35 support
- event-driven SSE/WebSocket status transport
- installer image
- full tablet power/amp install guide
- CAN transmit/control from the dashboard

## V1 roadmap checkpoint: Settings shell

The dashboard now has a Settings page shell for units, display preferences, diagnostics visibility, integrations, and reverse-assist placeholders. These controls are intentionally mostly non-functional at this stage; the first step is to establish where preferences live before wiring persistent behaviour.

### Settings shell scroll behaviour

The Settings page shell is scrollable inside the dashboard content area. This keeps the footer/tell-tales fixed while allowing units, display, diagnostics, integrations, and reverse-assist cards to remain accessible on tablet-sized screens.

### Settings option tree

The Settings page now uses a compact option-tree layout instead of a full page of cards. Categories stay visible on the left, and only the selected group is shown on the right. This keeps the dashboard shell fixed and avoids page-level scrolling on tablet screens.

### Diagnostics panel

Settings → Diagnostics now shows live decoded state such as status age, lighting mode, outside display/raw temperature, coolant, voltage, RPM, reverse, handbrake, and a link to `/api/status`. This is the first step toward moving raw/unfiltered values away from driver-facing pages.

### Door overlay

A global, dismissible door-open overlay now appears above any dashboard page when decoded door state reports an open door. Dismissal is tied to the current door-state signature: closing all doors resets it, and a changed door set can show the popup again. This creates the shared overlay foundation for future reverse/PDC/camera prompts.
