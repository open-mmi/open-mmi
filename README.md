# open-mmi

Open vehicle MMI integration framework for Linux.

`open-mmi` connects vehicle CAN-bus data to configurable Linux actions, persistent vehicle state, and UI/dashboard consumers.

> Where hex meets human form.

Designed for:

- car PC projects
- tablet integrations
- Linux infotainment systems
- steering wheel media controls
- reverse-engineered vehicle integrations
- lightweight vehicle dashboards

Supports:

- SocketCAN
- vehicle profiles
- user bindings
- modular actions
- profile-driven status/state mappings
- CLI dashboard / future UI consumers
- hot-reload configuration
- off-car safe mode
- systemd + udev integration
- safe user config directory under `~/.config/open-mmi`

---

# Branches

`main` is the stable branch.

`beta/status-cli` is the current beta branch for the vehicle status model and dashboard work.

Recommended workflow:

```bash
# Stable fallback
git switch main

# Status / dashboard development and testing
git switch beta/status-cli
```

For real vehicle testing, keep working changes on a beta branch until they have been tested on the car.

---

# Quick Start

## 1. Get the Code

```bash
git clone https://github.com/Sheepdog-97/open-mmi.git
cd open-mmi
```

For beta status/dashboard testing:

```bash
git switch beta/status-cli
```

## 2. Install

```bash
sudo ./scripts/manage.sh install
```

This will:

- install system dependencies
- create `/opt/open-mmi`
- create an isolated Python virtual environment
- install Python packages
- copy application files to `/opt/open-mmi`
- copy management scripts to `/opt/open-mmi/scripts`
- copy UI/dashboard files to `/opt/open-mmi/ui`
- install the systemd user service
- configure user permissions
- start the daemon

## 3. Verify Installation

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

## 4. View Logs

```bash
sudo ./scripts/manage.sh logs
```

Press Ctrl+C to exit logs.

## 5. Run the Status Dashboard

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

# How It Works

## Runtime Flow

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

## Three Profile Concepts

Vehicle profiles now have three distinct sections.

### `rules`

Momentary events that can trigger actions.

Examples:

```text
volume_up
next_track
arrow_left
brightness_level
```

These events are looked up in `bindings/*.json` and routed to functions in `actions/`.

### `presence`

Timeout-based availability checks.

Example:

```text
CAN ID 0x65F seen recently → vehicle_present:on
CAN ID 0x65F silent too long → vehicle_present:off
```

### `status`

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

# Vehicle Profile Format

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

## `rules`

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

## `presence`

```json
{
  "presence": [
    {
      "id": "0x65F",
      "timeout_ms": 6000,
      "on_present": "vehicle_present:on",
      "on_absent": "vehicle_present:off"
    }
  ]
}
```

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

# Bindings Format

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

---

# Safe User Config Workflow

Application files are installed to:

```text
/opt/open-mmi
```

User-editable config should live in:

```text
~/.config/open-mmi
```

This keeps personal vehicle profiles and bindings safe from updates.

## Create User Config

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

## Edit Vehicle Profile

```bash
sudo ./scripts/manage.sh config edit-profile seat_1p
```

## Edit Bindings

```bash
sudo ./scripts/manage.sh config edit-bindings default
```

## Edit Service Environment

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

## Show Config Paths

```bash
sudo ./scripts/manage.sh config paths
```

## Lookup Order

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

# Management Commands

## Install

```bash
sudo ./scripts/manage.sh install
```

## Update

```bash
sudo ./scripts/manage.sh update
```

The updater:

- runs Git operations as the real user, not root
- deploys files to `/opt/open-mmi`
- installs `canbusd/`, `vehicles/`, `bindings/`, `actions/`, `ui/`, and `scripts/`
- restarts the user service

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

# Status Dashboard

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

- a web UI
- a tablet UI
- a local dashboard service
- an MQTT bridge
- a WebSocket bridge

The UI should consume human-readable vehicle state, not raw CAN frames.

---

# Available Actions

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

# Development and Testing

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

---

# Common Workflows

## Add a New Button Action

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

4. Restart or reload the daemon:

```bash
systemctl --user restart canbusd.service
```

## Add a New Status Signal

1. Identify the CAN frame.
2. Add a `status` rule to your vehicle profile.
3. Restart the daemon.
4. Watch the dashboard:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

---

# Troubleshooting

## Daemon will not start

```bash
sudo ./scripts/manage.sh logs
```

Common causes:

- invalid JSON in profile or bindings
- missing Python dependency
- missing installed files
- wrong service environment variable

## CAN messages not received

```bash
ip link show can0
candump can0
```

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

The user should normally be in:

```text
video input
```

If needed:

```bash
sudo usermod -aG video,input $USER
```

Then log out/in or reboot.

---

# Safety

This project interfaces with vehicle CAN buses.

Incorrect configuration may:

- trigger unexpected actions
- misrepresent vehicle state
- affect driver distraction
- create unsafe behaviour if connected to critical systems

Always:

- start with passive observation
- avoid vehicle-critical CAN IDs
- test mappings carefully
- keep `main` stable
- use beta branches for real-car testing
- monitor logs during testing

---

# Contributing

Contributions are welcome:

- vehicle profiles
- CAN decode notes
- status mappings
- action modules
- UI/dashboard prototypes
- documentation improvements

Profile contributions should keep vehicle-specific CAN knowledge in `vehicles/<profile>/config.json`, not in core Python.

---

# License

GPL-3.0-only. See `LICENSE`.
