# open-mmi

**Open vehicle MMI integration framework for Linux.**

`open-mmi` connects vehicle CAN-bus signals to Linux actions, vehicle status, and user-facing interfaces.

> Where hex meets human form.

Designed for:

- car PC projects
- tablet integrations
- Linux infotainment systems
- steering wheel media controls
- reverse-engineered vehicle integrations
- open vehicle dashboards

Supports:

- SocketCAN
- vehicle profiles
- user bindings
- modular Linux actions
- profile-driven vehicle status mappings
- persistent status snapshots for CLI / UI consumers
- off-car safe mode
- hot-reload configuration
- systemd + udev integration
- install / update / uninstall management scripts

---

## Project status

`main` is treated as the stable branch.

Active status/dashboard work currently lives on:

```bash
beta/status-cli
```

Recommended workflow:

```bash
# Stable branch
git switch main

# Status / UI development branch
git switch beta/status-cli
```

For vehicle testing:

```bash
# On development laptop
git push

# On the car/test machine
git fetch origin
git switch beta/status-cli
sudo ./scripts/manage.sh update
```

---

# Quick Start

## 1. Get the code

```bash
git clone https://github.com/Sheepdog-97/open-mmi.git
cd open-mmi
```

To test the current dashboard/status beta:

```bash
git switch beta/status-cli
```

## 2. Install

```bash
sudo ./scripts/manage.sh install
```

This will:

- install system dependencies
- create a Python virtual environment in `/opt/open-mmi/venv`
- install Python dependencies
- copy application files to `/opt/open-mmi`
- install the `canbusd` systemd user service
- install udev rules if present
- configure user permissions
- start the daemon

The installed copy includes:

```text
/opt/open-mmi/canbusd/
/opt/open-mmi/vehicles/
/opt/open-mmi/bindings/
/opt/open-mmi/actions/
/opt/open-mmi/ui/
/opt/open-mmi/scripts/
```

This means the installed management script remains available even if the original repo checkout is removed:

```bash
sudo /opt/open-mmi/scripts/manage.sh status
sudo /opt/open-mmi/scripts/manage.sh logs
sudo /opt/open-mmi/scripts/manage.sh uninstall
```

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

## 4. View daemon logs

```bash
sudo ./scripts/manage.sh logs
```

You should see messages from `canbusd`, such as configuration loading, event dispatch, status updates, or CAN interface availability.

Press `Ctrl+C` to exit logs.

## 5. Run the status dashboard

From an installed system:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

Useful modes:

```bash
./venv/bin/python ui/dashboard/status_cli.py --once
./venv/bin/python ui/dashboard/status_cli.py --raw
```

The dashboard reads the current vehicle status snapshot produced by the daemon.

---

# How It Works

## Core pipeline

```text
Vehicle CAN frames
        ↓
vehicles/<profile>/config.json
        ↓
semantic events + vehicle status
        ↓
dispatcher / status bus
        ↓
actions + dashboard / future UI
```

There are two related but different outputs:

| Output type | Purpose | Example |
|---|---|---|
| `rules` | momentary events that can trigger actions | `volume_up`, `next_track`, `arrow_left` |
| `status` | persistent vehicle state for dashboards/UI | `doors.front_left = true`, `vehicle.reverse = false` |

## Event/action flow

```text
CAN Message from Vehicle
        ↓
[Vehicle Profile rules]
        ↓
Event, e.g. "volume_up"
        ↓
[Dispatcher]
        ↓
[Bindings]
        ↓
[Actions]
        ↓
Linux system effect
```

Example:

```text
0x5C1 byte0 = 0x06
        ↓
event = volume_up
        ↓
bindings/default.json
        ↓
actions/audio.py or actions/keys.py
        ↓
volume changes
```

## Status/UI flow

```text
CAN Message from Vehicle
        ↓
[Vehicle Profile status mappings]
        ↓
Generic status evaluator
        ↓
status_bus persistent snapshot
        ↓
CLI dashboard now / real UI later
```

Example:

```text
0x470 byte1 mask 0x02
        ↓
doors.front_left = true
        ↓
dashboard shows front-left door open
```

The UI does not need to know CAN IDs, byte indexes, masks, or vehicle-specific details. Those belong in the active vehicle profile.

---

# Project Structure

```text
open-mmi/
├── canbusd/
│   ├── core.py             ← Main CAN daemon loop
│   ├── dispatcher.py       ← Event publishing + action dispatch
│   ├── event_bus.py        ← In-process event pub/sub
│   ├── status_bus.py       ← Persistent vehicle status snapshot store
│   ├── status_rules.py     ← Generic profile-driven status evaluator
│   ├── state.py            ← In-memory state helper
│   └── __init__.py
│
├── vehicles/
│   └── seat_1p/
│       └── config.json     ← Vehicle-specific CAN profile
│
├── bindings/
│   └── default.json        ← Event → action mappings
│
├── actions/
│   ├── audio.py            ← Audio / media controls
│   ├── brightness.py       ← Screen brightness
│   ├── keys.py             ← Virtual input / media keys
│   ├── screen.py           ← Display helpers
│   └── __init__.py
│
├── ui/
│   └── dashboard/
│       └── status_cli.py   ← CLI dashboard / UI prototype
│
├── scripts/
│   └── manage.sh           ← Install / update / uninstall / status / logs
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

# Vehicle Profiles

Vehicle profiles live in:

```text
vehicles/<profile>/config.json
```

The active profile is selected with:

```bash
OPEN_MMI_VEHICLE=seat_1p
```

A profile can contain:

```json
{
  "rules": [],
  "presence": [],
  "status": []
}
```

## `rules`

Rules convert raw CAN byte values into momentary semantic events.

Example:

```json
{
  "id": "0x5C1",
  "byte": 0,
  "value": 6,
  "event": "volume_up"
}
```

This means:

```text
When CAN ID 0x5C1 has byte 0 equal to 6, emit volume_up.
```

The special value `"any"` emits when the byte changes and passes the byte value as an extra argument:

```json
{
  "id": "0x470",
  "byte": 2,
  "value": "any",
  "event": "brightness_level"
}
```

## `presence`

Presence rules watch for whether a CAN ID is still being seen.

Example:

```json
{
  "id": "0x65F",
  "timeout_ms": 6000,
  "on_present": "vehicle_present:on",
  "on_absent": "vehicle_present:off"
}
```

This is useful for vehicle-awake / vehicle-asleep detection.

## `status`

Status mappings convert CAN bytes into persistent state for dashboards and future UIs.

Example bitfield mapping:

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

This writes state like:

```json
{
  "doors": {
    "front_right": false,
    "front_left": true,
    "rear_left": false,
    "rear_right": false,
    "bonnet": false,
    "boot": false,
    "any_open": true,
    "raw": 2
  }
}
```

Example boolean mapping:

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

Example enum mapping:

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

Example percentage mapping:

```json
{
  "id": "0x470",
  "byte": 2,
  "type": "percent",
  "path": "lighting.dimmer_percent",
  "raw_path": "lighting.dimmer_raw"
}
```

Supported status types:

| Type | Purpose |
|---|---|
| `raw` | Store the byte value directly |
| `percent` | Clamp byte value to 0-100 |
| `bool` | Match true/false values |
| `enum` | Map byte values to human-readable strings |
| `bitfield` | Map bit masks to boolean state fields |

---

# Bindings

Bindings live in:

```text
bindings/*.json
```

They map events to action modules.

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

Events without bindings are still published internally, but no action is executed.

---

# Actions

Actions live in:

```text
actions/
```

Current action modules include:

## `audio.py`

```python
volume_up(step="+5%")
volume_down(step="-5%")
mute_toggle()
play_pause()
next_track()
prev_track()
stop()
```

## `brightness.py`

```python
set_percent(percent)
from_can(value)
```

## `keys.py`

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

## `screen.py`

```python
on()
off()
wake_and_login(user)
```

---

# Status Dashboard

The current dashboard is a CLI prototype located at:

```text
ui/dashboard/status_cli.py
```

Run from the installed copy:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

One-shot output:

```bash
./venv/bin/python ui/dashboard/status_cli.py --once
```

Raw status snapshot:

```bash
./venv/bin/python ui/dashboard/status_cli.py --raw
```

The dashboard reads the persistent status snapshot written by `canbusd/status_bus.py`.

The current snapshot path defaults to:

```text
$XDG_RUNTIME_DIR/open-mmi/status.json
```

with fallback to:

```text
/tmp/open-mmi-status.json
```

A future web/tablet UI can consume the same state without decoding CAN itself.

---

# Common Workflows

## Add a new button/action

1. Identify the CAN message:

```bash
candump can0
```

2. Add a `rules` entry to the vehicle profile:

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

4. Validate JSON:

```bash
python3 -m json.tool vehicles/my_car/config.json >/dev/null
python3 -m json.tool bindings/my_bindings.json >/dev/null
```

5. Update/restart:

```bash
sudo ./scripts/manage.sh update
systemctl --user restart canbusd.service
sudo ./scripts/manage.sh logs
```

## Add a new status value

1. Identify the CAN message:

```bash
candump can0
```

2. Add a `status` entry to the vehicle profile:

```json
{
  "id": "0x123",
  "byte": 0,
  "type": "bool",
  "path": "vehicle.example",
  "true": "0x01",
  "false": "0x00",
  "raw_path": "vehicle.example_raw"
}
```

3. Validate and update:

```bash
python3 -m json.tool vehicles/my_car/config.json >/dev/null
sudo ./scripts/manage.sh update
systemctl --user restart canbusd.service
```

4. Watch the dashboard:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py
```

## Test before installing

From the repo checkout:

```bash
python3 -m py_compile canbusd/core.py canbusd/status_rules.py canbusd/status_bus.py
python3 -m json.tool vehicles/seat_1p/config.json >/dev/null
```

For real CAN testing, the daemon should run under the installed environment because permissions, systemd, udev, and runtime paths matter.

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

The updater runs Git operations as the real user, then deploys system files with sudo. This allows SSH keys and Git config to work correctly even when the update command is launched with sudo.

## Status

```bash
sudo ./scripts/manage.sh status
```

## Logs

```bash
sudo ./scripts/manage.sh logs
```

## Edit service config

```bash
sudo ./scripts/manage.sh config edit
```

Use this to set environment variables such as:

```ini
Environment="OPEN_MMI_VEHICLE=seat_1p"
Environment="OPEN_MMI_BINDINGS=default"
Environment="OPEN_MMI_LOG_LEVEL=INFO"
```

## Uninstall

```bash
sudo ./scripts/manage.sh uninstall
```

If the repo checkout has been removed, use the installed copy:

```bash
sudo /opt/open-mmi/scripts/manage.sh uninstall
```

---

# Environment Variables

```bash
OPEN_MMI_VEHICLE=seat_1p
OPEN_MMI_BINDINGS=default
OPEN_MMI_LOG_LEVEL=INFO
OPEN_MMI_STATUS_PATH=/custom/status.json
```

| Variable | Purpose |
|---|---|
| `OPEN_MMI_VEHICLE` | Select active vehicle profile |
| `OPEN_MMI_BINDINGS` | Select active bindings file |
| `OPEN_MMI_LOG_LEVEL` | Set logging level |
| `OPEN_MMI_STATUS_PATH` | Override status snapshot path |

---

# Troubleshooting

## Daemon will not start

```bash
sudo ./scripts/manage.sh logs
```

Common causes:

- invalid JSON in vehicle profile or bindings
- missing `/opt/open-mmi/canbusd`
- systemd service pointing at the wrong working directory
- missing Python dependency
- permission issue with CAN/input devices

Check installed files:

```bash
ls -l /opt/open-mmi/canbusd/core.py
ls -l /opt/open-mmi/vehicles
ls -l /opt/open-mmi/actions
```

## CAN messages are not being received

```bash
ip link show can0
candump can0
```

If `can0` is down:

```bash
sudo ip link set can0 up
```

## Actions are not executing

Watch logs:

```bash
sudo ./scripts/manage.sh logs
```

Look for:

```text
Event dispatched: <event_name>
```

Then check:

- does the event exist in `bindings/*.json`?
- does the module exist in `actions/`?
- does the function name match?
- does the action need extra permissions?

## Dashboard is blank

Check that the daemon is running:

```bash
sudo ./scripts/manage.sh status
```

Check the status snapshot:

```bash
cat "${XDG_RUNTIME_DIR:-/tmp}/open-mmi/status.json"
```

or:

```bash
find /run/user/$(id -u) /tmp -name status.json 2>/dev/null
```

Then run:

```bash
cd /opt/open-mmi
./venv/bin/python ui/dashboard/status_cli.py --raw
```

## Permission denied

Check user groups:

```bash
groups $USER
```

The user should normally be in:

```text
video input
```

If not:

```bash
sudo usermod -aG video,input $USER
```

Then log out/in or reboot.

---

# Requirements

## System

- Linux with systemd
- Python 3.9+
- CAN interface, usually `can0`
- SocketCAN support

## Python packages

Installed by `manage.sh`:

- `python-can`
- `evdev`

## Optional system tools

For audio/media:

```bash
sudo apt install pulseaudio-utils playerctl
```

For CAN debugging:

```bash
sudo apt install can-utils
```

For display/desktop integrations, requirements depend on the desktop/session.

---

# Contributing

Good contribution areas:

- new vehicle profiles
- improved CAN decodes
- new action modules
- new dashboard/UI consumers
- documentation improvements
- installer/test workflow improvements

Vehicle profile contributions should keep vehicle-specific CAN knowledge in:

```text
vehicles/<profile>/config.json
```

Core Python should stay generic where possible.

---

# Safety

**WARNING:** This interfaces with vehicle CAN buses.

Incorrect configuration may:

- trigger unexpected system behaviour
- cause distracting UI/actions while driving
- create unsafe assumptions about vehicle state

General guidance:

- prefer read-only CAN observation
- test off-road or parked first
- avoid vehicle-critical CAN IDs
- keep `main` stable and test new work on a beta branch
- monitor logs during testing
- verify changes on the real vehicle before merging

---

# License

GPL-3.0-only. See `LICENSE`.
