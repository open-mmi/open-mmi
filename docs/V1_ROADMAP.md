# Open MMI V1 Roadmap

Open MMI V1 is the first complete public shape of the project: a local, read-only vehicle dashboard/MMI built from decoded vehicle state.

## Current baseline

- Web dashboard merged as the main project face
- Drive page
- Media page with optional Jellyfin integration
- Climate page
- Vehicle/status page
- Footer tell-tales
- Demo mode
- SEAT León 1P confirmed reference vehicle

## Required before V1

### Home/Menu navigation

Target layout:

```text
Media ← Home/Menu → Drive
Home/Menu should provide quick access to:

Drive
Media
Climate
Settings
Diagnostics/Vehicle
Settings

Initial settings should cover:

units
display preferences
tell-tale test mode
raw/debug visibility
Jellyfin status
reverse assist placeholder
Diagnostics cleanup

Move raw/unfiltered values out of driver-facing pages where possible.

Examples:

outside unfiltered temperature
snapshot age
decoded lighting mode
missing fields
raw status link
Vehicle event overlays

Add a reusable overlay system for important vehicle events.

Initial overlays:

door open popup with dismiss
reverse selected placeholder
Compatibility testing

Document a temporary read-only test process for other PQ35-family vehicles.

Wanted test vehicles:

VW Golf Mk5
Audi A3 8P
Škoda Octavia 1Z
Škoda Yeti
V1 release docs

Before tagging V1:

README screenshots current
demo mode tested from clean clone
no secrets or backup files
compatibility limits clearly stated
known limitations documented
