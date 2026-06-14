# open-mmi

Open vehicle MMI integration framework for Linux.

`open-mmi` is an early GPLv3 vehicle integration project that connects passive vehicle CAN-bus data to configurable Linux actions, persistent vehicle state, and UI/dashboard consumers.

> Where hex meets human form.

---

## Current status

`open-mmi` is currently an **alpha/backend project**.

The current maintainer-tested reference vehicle is:

```text
Seat Leon 1P / VAG PQ35
```

The current focus is:

```text
SocketCAN receive
profile-driven CAN decoding
persistent vehicle status snapshots
local Linux actions
CLI/dashboard consumers
safe user configuration
vehicle-profile contribution workflow
```

This is **not yet** a polished infotainment replacement, final tablet UI, or multi-vehicle supported product.

The goal is to build a reusable open foundation so vehicle-specific CAN knowledge can live in shareable profiles instead of being rediscovered privately.

---

## Current tagged checkpoint

The existing `v1.0.0-backend` tag represents an early backend checkpoint, not a final Open MMI product release.

It proves the first backend foundation:

* CAN input via SocketCAN
* profile-driven vehicle decoding
* configurable event dispatch
* modular Linux actions
* timeout-based vehicle presence
* persistent vehicle status snapshots
* safe user config under `~/.config/open-mmi`
* install/update/uninstall tooling
* CLI dashboard prototype

Future GitHub Releases will use clearer alpha versioning, release notes, known limitations, screenshots or example output, and a clear source checkpoint.

---

## What open-mmi is for

`open-mmi` is designed for:

* Linux car PC projects
* tablet-based vehicle integrations
* steering wheel media controls
* lightweight vehicle dashboards
* reverse-engineered vehicle integrations
* local vehicle state/status display
* future dashboard and UI consumers

The project currently focuses on local, passive CAN receive and Linux-side actions. It does not currently provide active CAN transmit/control behaviour.

---

## What open-mmi supports today

Current capabilities include:

* SocketCAN input
* vehicle profiles
* user bindings
* modular actions
* profile-driven status/state mappings
* persistent status snapshot output
* CLI dashboard / future UI consumers
* hot-reload configuration
* off-car safe mode
* systemd + udev integration
* safe user config directory under `~/.config/open-mmi`

---

## Screenshots and visual proof

The UI is currently alpha. Screenshots should be treated as proof of the backend/status pipeline, not as a final user interface.

Future screenshots can be added here.

### CLI dashboard alpha

```text
TODO: Add screenshot of the CLI dashboard consuming live status snapshot.
```

Example future Markdown:

```markdown
![open-mmi CLI dashboard alpha](docs/images/status-cli-alpha.png)
```

### Daemon/status proof

```text
TODO: Add screenshot or terminal capture showing daemon status/logs.
```

Example future Markdown:

```markdown
![open-mmi daemon status](docs/images/daemon-status.png)
```

### Future graphical/tablet UI

```text
TODO: Add screenshot of graphical/tablet UI once it exists.
```

Example future Markdown:

```markdown
![open-mmi tablet UI alpha](docs/images/tablet-ui-alpha.png)
```

---

## Branches

`main` is intended to stay conservative and usable.

Development work should happen on feature or beta branches before being merged into `main`.

Recommended workflow:

```bash
# Main branch
git switch main

# New development branch
git switch -c beta/my-feature
```

For real vehicle testing, keep working changes on a beta branch until they have been tested on the car.

Backend checkpoints may be tagged, for example:

```bash
git checkout v1.0.0-backend
```

A git tag is not the same thing as a GitHub Release. Future public GitHub Releases will include release notes, known limitations, screenshots or example output, and a clear source checkpoint.

---

# Quick Start

## 1. Get the code

```bash
git clone https://github.com/Sheepdog-97/open-mmi.git
cd open-mmi
```

## 2. Install

```bash
sudo ./scripts/manage.sh install
```

This will:

* install system dependencies
* create `/opt/open-mmi`
* create an isolated Python virtual environment
* install Python packages
* copy application files to `/opt/open-mmi`
* copy management scripts to `/opt/open-mmi/scripts`
* copy UI/dashboard files to `/opt/open-mmi/ui`
* install the systemd user service
* configure user permissions
* start the daemon

## 3. Verify installation

```bash
sudo ./scripts/manage.sh status
```

Expected output:

```text
Status:         ✓ Installed
Install Dir:    /opt/open-mmi
Version:        <current-version>
Service:        ✓ Running
```

## 4. View logs

```bash
sudo ./scripts/manage.sh logs
```

Press `Ctrl+C` to exit logs.

## 5. Run the status dashboard

From the installed copy:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

Useful alternatives:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py --once
./venv/bin/python ui/dashboard/status_cli.py --raw
```

---

# Safety note

This project interfaces with vehicle CAN buses.

`open-mmi` currently focuses on passive CAN receive and local Linux actions. Do not add vehicle CAN transmit/control behaviour without a separate safety design, explicit allowlists, warnings, maintainer review, and extensive testing.

Decoded status is informational and should not be treated as a replacement for OEM safety warnings, diagnostics, or driver judgement.

---

# How it works

## Runtime flow

```text
CAN frame from vehicle
        ↓
canbusd/core.py
        ↓
active vehicle profile
        ↓
rules / presence / status mappings
        ↓
dispatcher + event bus + status bus
        ↓
actions and dashboards
```

The core idea is that vehicle-specific CAN knowledge should live in vehicle profiles, not hardcoded into the daemon.

---

# Architecture

```text
open-mmi/
├── canbusd/
│   ├── core.py             ← daemon loop: CAN input, profile loading
│   ├── dispatcher.py       ← event → event bus + action execution
│   ├── event_bus.py        ← in-process pub/sub for events
│   ├── status_bus.py       ← persistent vehicle state snapshots
│   ├── status_rules.py     ← generic profile-driven status evaluator
│   ├── state.py            ← simple in-process state helper
│   └── __init__.py
│
├── vehicles/
│   └── seat_1p/
│       └── config.json     ← vehicle CAN profile
│
├── bindings/
│   └── default.json        ← semantic event → action mapping
│
├── actions/
│   ├── audio.py
│   ├── brightness.py
│   ├── keys.py
│   ├── screen.py
│   └── __init__.py
│
├── ui/
│   └── dashboard/
│       └── status_cli.py   ← CLI dashboard / UI prototype
│
├── scripts/
│   └── manage.sh           ← install/update/uninstall/config
│
├── systemd/
│   └── user/
│       └── canbusd.service
│
├── udev/
│   └── 80-canbus.rules
│
├── pyproject.toml
├── README.md
└── LICENSE
```

---

# Three profile concepts

Vehicle profiles have three distinct sections:

```text
rules
presence
status
```

## `rules`

Momentary events that can trigger actions.

Examples:

```text
volume_up
next_track
arrow_left
brightness_level
```

These events are looked up in `bindings/*.json` and routed to functions in `actions/`.

## `presence`

Timeout-based availability checks.

Example:

```text
CAN ID 0x65F seen recently      → vehicle.present = true and vehicle_present:on
CAN ID 0x65F silent too long    → vehicle.present = false and vehicle_present:off
```

Presence rules are useful for detecting whether the vehicle bus is awake and for triggering local actions such as screen on/off.

## `status`

Persistent vehicle state for dashboards and future UI consumers.

Examples:

```text
doors.front_left = open
vehicle.reverse = true
vehicle.handbrake = true
lighting.mode = dip
lighting.dimmer_percent = 42
```

Status mappings are profile-driven. The core daemon knows generic rule types such as `bool`, `enum`, `bitfield`, `percent`, and `raw`; vehicle-specific CAN knowledge stays inside `vehicles/<profile>/config.json`.

---

# Vehicle profile format

Vehicle profiles live in:

```text
vehicles/<profile>/config.json
```

A profile may contain:

```json
{
  "rules": [],
  "presence": [],
  "status": []
}
```

---

## `rules`

Example:

```json
{
  "rules": [
    {
      "id": "0x5C1",
      "byte": 0,
      "value": 6,
      "event": "volume_up"
    },
    {
      "id": "0x470",
      "byte": 2,
      "value": "any",
      "event": "brightness_level"
    }
  ]
}
```

`value` may be a number or `"any"`.

`"any"` means the event fires when that byte changes, and the byte value is passed as an extra argument.

---

## `presence`

Example:

```json
{
  "presence": [
    {
      "id": "0x65F",
      "timeout_ms": 6000,
      "status_path": "vehicle.present",
      "on_present": "vehicle_present:on",
      "on_absent": "vehicle_present:off"
    }
  ]
}
```

`status_path` is optional. If omitted, presence is published to:

```text
vehicle.present
```

Presence status is also written under a per-frame diagnostic key such as:

```text
presence.0x65F = true
```

`on_present` and `on_absent` are optional events. If present, they are dispatched when the presence state changes.

---

## `status`

Status rules turn raw CAN data into persistent state.

### Bitfield

```json
{
  "id": "0x470",
  "byte": 1,
  "type": "bitfield",
  "path": "doors",
  "fields": {
    "front_right": "0x01",
    "front_left": "0x02",
    "rear_left": "0x04",
    "rear_right": "0x08",
    "bonnet": "0x10"
  },
  "equals": {
    "boot": "0x60"
  },
  "any": "any_open",
  "raw": "raw"
}
```

This produces status like:

```json
{
  "doors": {
    "front_left": true,
    "front_right": false,
    "any_open": true,
    "raw": 2
  }
}
```

### Percent

```json
{
  "id": "0x470",
  "byte": 2,
  "type": "percent",
  "path": "lighting.dimmer_percent",
  "raw_path": "lighting.dimmer_raw"
}
```

### Bool

```json
{
  "id": "0x621",
  "byte": 0,
  "type": "bool",
  "path": "vehicle.handbrake",
  "true": "0x20",
  "false": "0x00",
  "raw_path": "vehicle.handbrake_raw"
}
```

### Enum

```json
{
  "id": "0x531",
  "byte": 0,
  "type": "enum",
  "path": "lighting.mode",
  "values": {
    "0x00": "off",
    "0xC1": "sides",
    "0xC3": "dip"
  },
  "default": "unknown",
  "raw_path": "lighting.mode_raw"
}
```

---

# Bindings format

Bindings live in:

```text
bindings/<name>.json
```

Example:

```json
{
  "volume_up": {
    "module": "audio",
    "func": "volume_up",
    "args": ["+5%"]
  },
  "play_pause": {
    "module": "keys",
    "func": "play_pause"
  }
}
```

Bindings are selected with:

```ini
Environment="OPEN_MMI_BINDINGS=default"
```

Bindings are trusted local configuration. Do not install random bindings or vehicle profiles without reviewing them.

---

# Safe user config workflow

Application files are installed to:

```text
/opt/open-mmi
```

User-editable config should live in:

```text
~/.config/open-mmi
```

This keeps personal vehicle profiles and bindings safe from updates.

## Create user config

```bash
sudo ./scripts/manage.sh config init seat_1p default
```

This creates:

```text
~/.config/open-mmi/
├── vehicles/
│   └── seat_1p/
│       └── config.json
└── bindings/
    └── default.json
```

Existing user files are not overwritten.

## Edit vehicle profile

```bash
sudo ./scripts/manage.sh config edit-profile seat_1p
```

## Edit bindings

```bash
sudo ./scripts/manage.sh config edit-bindings default
```

## Edit service environment

```bash
sudo ./scripts/manage.sh config edit-service
```

Use this for environment variables such as:

```ini
[Service]
Environment="OPEN_MMI_VEHICLE=seat_1p"
Environment="OPEN_MMI_BINDINGS=default"
Environment="OPEN_MMI_LOG_LEVEL=DEBUG"
```

## Show config paths

```bash
sudo ./scripts/manage.sh config paths
```

## Lookup order

Vehicle config lookup order:

```text
1. OPEN_MMI_VEHICLE_CONFIG
2. ~/.config/open-mmi/vehicles/<vehicle>/config.json
3. /opt/open-mmi/vehicles/<vehicle>/config.json
```

Bindings lookup order:

```text
1. OPEN_MMI_BINDINGS_FILE
2. ~/.config/open-mmi/bindings/<bindings>.json
3. /opt/open-mmi/bindings/<bindings>.json
```

So a user can safely keep personal profiles outside the installed app tree.

---

# Management commands

## Install

```bash
sudo ./scripts/manage.sh install
```

## Update

```bash
sudo ./scripts/manage.sh update
```

The updater:

* runs Git operations as the real user, not root
* deploys files to `/opt/open-mmi`
* installs `canbusd/`, `vehicles/`, `bindings/`, `actions/`, `ui/`, and `scripts/`
* restarts the user service

## Status

```bash
sudo ./scripts/manage.sh status
```

## Logs

```bash
sudo ./scripts/manage.sh logs
```

## Config

```bash
sudo ./scripts/manage.sh config init seat_1p default
sudo ./scripts/manage.sh config edit-profile seat_1p
sudo ./scripts/manage.sh config edit-bindings default
sudo ./scripts/manage.sh config edit-service
sudo ./scripts/manage.sh config paths
```

## Uninstall

From a repo checkout:

```bash
sudo ./scripts/manage.sh uninstall
```

Or from the installed copy, even if the repo was deleted:

```bash
sudo /opt/open-mmi/scripts/manage.sh uninstall
```

---

# Status dashboard

The dashboard reads the persistent status snapshot produced by `canbusd/status_bus.py`.

Run from the installed copy:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

Options:

```bash
./venv/bin/python ui/dashboard/status_cli.py --once
./venv/bin/python ui/dashboard/status_cli.py --raw
```

This is currently a CLI dashboard, but the same status snapshot can later feed:

* a web UI
* a tablet UI
* a local dashboard service
* an MQTT bridge
* a WebSocket bridge

The UI should consume human-readable vehicle state, not raw CAN frames.

---

# Available actions

## `actions/audio.py`

```python
volume_up(step="+5%")
volume_down(step="-5%")
mute_toggle()
play_pause()
next_track()
prev_track()
stop()
```

## `actions/brightness.py`

```python
set_percent(percent)
from_can(value)
```

## `actions/keys.py`

```python
play_pause()
next_track()
prev_track()
stop()
mute_toggle()
volume_up()
volume_down()
arrow_left()
arrow_right()
```

## `actions/screen.py`

```python
on()
off()
wake_and_login(user)
```

---

# Development and testing

## Run the daemon manually

From the repo checkout:

```bash
OPEN_MMI_LOG_LEVEL=DEBUG OPEN_MMI_VEHICLE=seat_1p python3 -m canbusd.core
```

## Validate JSON

```bash
python3 -m json.tool vehicles/seat_1p/config.json >/dev/null
python3 -m json.tool bindings/default.json >/dev/null
```

## Check Python syntax

```bash
python3 -m py_compile canbusd/core.py canbusd/status_rules.py canbusd/status_bus.py
```

## Watch raw CAN

```bash
candump can0
```

The examples currently use `can0`. Other adapters, capture points, vehicles, or bitrates may require adjustment.

---

# Common workflows

## Add a new button action

1. Watch CAN traffic:

```bash
candump can0
```

2. Add a rule to your vehicle profile:

```json
{
  "id": "0x456",
  "byte": 1,
  "value": 1,
  "event": "play_pause"
}
```

3. Add a binding:

```json
{
  "play_pause": {
    "module": "keys",
    "func": "play_pause"
  }
}
```

4. Restart or update the daemon:

```bash
systemctl --user restart canbusd.service
```

## Add a new status signal

1. Identify the CAN frame.
2. Add a `status` rule to your vehicle profile.
3. Restart the daemon.
4. Watch the dashboard:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

---

# Reference vehicle

The current maintainer-tested reference vehicle is:

```text
Seat Leon 1P / VAG PQ35
```

The included `seat_1p` profile is the first real-car tested profile.

Known decoded areas include, where supported by the tested vehicle/profile:

* vehicle presence
* door/open state
* reverse
* handbrake
* brake
* lighting mode
* dimmer percentage
* indicators / hazards
* steering angle / direction / magnitude
* bulb fault status

Vehicle coding, installed modules, equipment level, and capture point may affect which frames are visible or meaningful.

---

# Current limitations

`open-mmi` is currently an alpha/backend project.

Known limitations:

* the dashboard is currently a CLI prototype
* only the included Seat 1P / VAG PQ35 profile has been real-car tested by the maintainer
* vehicle profiles may require manual CAN discovery
* CAN interface and bitrate assumptions may need adjustment for other vehicles or adapters
* some status fields are profile-specific and need refinement
* automated tests are still minimal
* replay/demo tooling is not yet complete
* Open MMI currently focuses on passive CAN receive and local Linux actions
* this is not yet a polished end-user infotainment system

Decoded status is informational and should not be treated as a replacement for OEM safety warnings or diagnostics.

---

# Troubleshooting

## Daemon will not start

```bash
sudo ./scripts/manage.sh logs
```

Common causes:

* invalid JSON in profile or bindings
* missing Python dependency
* missing installed files
* wrong service environment variable

## CAN messages not received

```bash
ip link show can0
candump can0
```

Check:

* CAN adapter is detected
* interface is up
* bitrate is correct for the bus being monitored
* CAN high / CAN low are connected correctly
* ground is connected if required by the adapter
* the selected capture point actually exposes the frames you expect

## User config not being used

Check paths:

```bash
sudo ./scripts/manage.sh config paths
```

Check daemon logs for:

```text
Loaded config from ...
Loaded bindings from ...
```

## Permission denied for virtual input

Check groups:

```bash
groups $USER
```

The user may need access to groups such as:

```text
video input
```

If needed:

```bash
sudo usermod -aG video,input $USER
```

Then log out/in or reboot.

These permissions are a local security tradeoff because they allow interaction with display/input-related system features. Only use them on systems where you trust the installed open-mmi configuration.

---

# Safety

This project interfaces with vehicle CAN buses.

Incorrect configuration may:

* trigger unexpected local Linux actions
* misrepresent vehicle state
* affect driver distraction
* create unsafe behaviour if connected to critical systems

Always:

* start with passive observation
* avoid vehicle-critical CAN IDs
* test mappings carefully
* keep `main` conservative
* use beta branches for real-car testing
* monitor logs during testing
* review vehicle profiles and bindings before using them

Open MMI currently focuses on passive CAN receive and local Linux actions.

Do not add vehicle CAN transmit/control behaviour without a separate safety design, explicit allowlists, warnings, maintainer review, and extensive testing.

---

# Contributing

Contributions are welcome.

Useful contribution areas include:

* vehicle profiles
* CAN decode notes
* status mappings
* action modules
* UI/dashboard prototypes
* documentation improvements
* install/testing notes
* screenshots and example output
* replay/demo data once tooling supports it

Profile contributions should keep vehicle-specific CAN knowledge in:

```text
vehicles/<profile>/config.json
```

not in core Python.

If you are adding support for a new vehicle, useful information includes:

* vehicle make/model/year
* platform/chassis if known
* CAN adapter used
* capture point used
* bitrate
* candump logs
* what physical state was triggered
* VCDS/OBDeleven/diagnostic notes if available
* whether the mapping was tested on a real vehicle

---

# Security

Please see `SECURITY.md` for security guidance.

Important principles:

* keep CAN receive passive by default
* treat vehicle profiles and bindings as trusted local configuration
* avoid active CAN transmit/control behaviour without a separate reviewed design
* do not install random profiles or bindings without review
* report security concerns privately where appropriate

---

# License

GPL-3.0-only.

See `LICENSE`.
