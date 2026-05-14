````markdown
# open-mmi

Open vehicle MMI integration framework for Linux.

`open-mmi` connects vehicle CAN-bus events to configurable Linux actions.

Designed for:
- car PC projects
- tablet integrations
- Linux infotainment systems
- steering wheel media controls
- reverse-engineered vehicle integrations

Supports:
- SocketCAN
- hot-reload configuration
- vehicle profiles
- user bindings
- modular actions
- off-car safe mode
- systemd + udev integration

---

# Architecture

open-mmi is split into three layers:

| Layer | Purpose |
|------|--------|
| Vehicle Config | Interprets raw CAN messages into semantic events |
| Bindings | Maps events to actions |
| Actions | Executes system behaviour |

## Flow

```text
CAN message
    ↓
Vehicle config (CAN rule match)
    ↓
Event (e.g. volume_up)
    ↓
Binding lookup
    ↓
Action execution
    ↓
Linux system effect
````

## Example

```text
0x5C1 byte0=0x06
    ↓
volume_up
    ↓
audio.volume_up("+10%")
```

---

# Project Structure

```text
open-mmi/
├── canbusd/
│   └── canbusd.py
│
├── vehicles/
│   └── seat_1p/
│       └── config.json
│
├── bindings/
│   └── default.json
│
├── actions/
│   ├── audio.py
│   ├── brightness.py
│   ├── keys.py
│   ├── screen.py
│   └── __init__.py
│
├── systemd/
├── udev/
├── scripts/
├── pyproject.toml
└── dev/
```

---

# Vehicle Profiles

Vehicle profiles define how raw CAN data becomes events.

Location:

```text
vehicles/<vehicle_name>/config.json
```

Example:

```json
{
  "id": "0x5C1",
  "byte": 0,
  "value": 6,
  "event": "volume_up"
}
```

---

# Bindings

Bindings map events → actions.

Location:

```text
bindings/default.json
```

Example:

```json
{
  "volume_up": {
    "module": "audio",
    "func": "volume_up",
    "args": ["+10%"]
  }
}
```

Bindings can be changed without modifying vehicle configs.

---

# Actions

Actions are Python modules that implement system behaviour.

Located in:

```text
actions/
```

Examples:

* audio control
* media keys
* brightness control
* screen power management

Each action exposes simple functions used by bindings.

---

# Requirements

## System

* Linux (systemd recommended)
* Python 3.10+
* SocketCAN enabled kernel
* CAN interface (e.g. can0)

## Python dependencies

No strict `requirements.txt` is used.

Recommended dependency:

* python-can

Install example:

```bash
pip install python-can
```

(or via system package manager where available)

---

# Running

## Validate configuration

```bash
python3 canbusd/canbusd.py --check
```

## Run (development mode)

```bash
python3 canbusd/canbusd.py
```

---

# Installation (system mode)

Install to system:

```bash
sudo ./scripts/install.sh
```

This will:

* copy project to `/opt/open-mmi`
* install systemd service
* install udev rules
* enable CAN interface startup (if configured)
* start and enable daemon

---

# systemd service

Located at:

```text
systemd/canbusd.service
```

Responsible for:

* starting daemon at boot
* restarting on failure
* managing runtime process

---

# udev rules

Located at:

```text
udev/80-canbus.rules
```

Used to:

* bring up CAN interface (can0)
* configure bitrate
* ensure consistent network state

---

# Development

Run locally without install:

```bash
python3 canbusd/canbusd.py --check
python3 canbusd/canbusd.py
```

Development tools:

```text
dev/
```

Ignored by git and not used in production installs.

---

# Contributing

Contributions are welcome:

* new vehicle profiles
* improved CAN mappings
* new action modules
* hardware integrations
* documentation improvements
* tooling and debugging utilities

Vehicle profiles should remain hardware-focused and not contain user-specific logic.

---

# Safety

This project interfaces directly with vehicle CAN networks.

Incorrect configuration may affect vehicle behaviour or system usability.

Use carefully and ensure you understand your vehicle’s CAN environment before enabling or modifying mappings.

```
```

