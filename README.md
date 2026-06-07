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
|------|---------|
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
```

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
│   └── user/
│       └── canbusd.service
│
├── udev/
│   └── 80-canbus.rules
│
├── scripts/
│   ├── manage.sh          (Main installation/management tool)
│   └── dev_run.sh         (Development runner)
│
├── pyproject.toml
├── README.md
└── LICENSE
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
  "rules": [
    {
      "id": "0x5C1",
      "byte": 0,
      "value": 6,
      "event": "volume_up"
    }
  ],
  "presence": []
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

* **audio** - Volume control, playback transport (playerctl + pactl)
* **keys** - Virtual media key injection (uinput)
* **brightness** - Display brightness control (brightnessctl)
* **screen** - Display power management (xset) and user switching (dm-tool)

Each action exposes simple functions used by bindings.

---

# Requirements

## System

* Linux (systemd recommended)
* Python 3.9+
* SocketCAN enabled kernel
* CAN interface (e.g. `can0`)

## User Permissions

Running canbusd requires membership in:

* `video` group - for brightness and display control via `/sys/class/backlight`
* `input` group - for uinput device access (virtual keyboard)

If permissions issues occur, check:

```bash
# User should be in these groups
groups $USER

# Add user to required groups (automatic during install)
sudo usermod -aG video,input $USER

# Apply changes (may require logout/login or use: newgrp video)
```

## Python Dependencies

Install via pip (automatically handled by install):

```bash
pip install python-can evdev
```

Optional for additional functionality:

```bash
# For audio control via pactl (PulseAudio/PipeWire)
sudo apt install pulseaudio-utils

# For audio transport via playerctl
sudo apt install playerctl

# For brightness control
sudo apt install brightnessctl

# For display control
sudo apt install xserver-xorg-core x11-utils

# For user switching
sudo apt install lightdm-tools  # or equivalent for your display manager
```

---

# Configuration

## Environment Variables

Control daemon behavior via environment variables:

```bash
# Vehicle profile to load (default: seat_1p)
export OPEN_MMI_VEHICLE=seat_1p

# Bindings file to load (default: default)
export OPEN_MMI_BINDINGS=default

# Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)
export OPEN_MMI_LOG_LEVEL=INFO
```

For systemd service, edit configuration:

```bash
sudo ./scripts/manage.sh config edit
```

Then add to `[Service]` section:

```ini
Environment="OPEN_MMI_LOG_LEVEL=DEBUG"
Environment="OPEN_MMI_VEHICLE=seat_1p"
```

---

# Running

## Validate Configuration

```bash
python3 canbusd/canbusd.py --check
```

## Development Mode

```bash
# Ensure dependencies are installed
pip install python-can evdev

# Run daemon (or use dev script)
./scripts/dev_run.sh

# Or manually with debug logging
OPEN_MMI_LOG_LEVEL=DEBUG python3 canbusd/canbusd.py
```

---

# Installation & Management

All installation, update, and management operations use the unified `manage.sh` script.

## Prerequisites

```bash
sudo apt update
sudo apt install git python3 python3-pip python3-venv can-utils udev dbus-x11
```

## Quick Start

```bash
# Install
sudo ./scripts/manage.sh install

# Check status
sudo ./scripts/manage.sh status

# View logs
sudo ./scripts/manage.sh logs

# Update
sudo ./scripts/manage.sh update

# Uninstall
sudo ./scripts/manage.sh uninstall
```

## Installation Manager (`manage.sh`)

Complete unified tool for installation, updates, and management.

### Commands

```bash
sudo ./scripts/manage.sh install      # Fresh installation
sudo ./scripts/manage.sh update       # Update with automatic rollback
sudo ./scripts/manage.sh uninstall    # Remove installation
sudo ./scripts/manage.sh status       # Show installation status
sudo ./scripts/manage.sh logs         # View daemon logs in real-time
sudo ./scripts/manage.sh config edit  # Edit service configuration
```

### Install

```bash
sudo ./scripts/manage.sh install
```

**Does:**

* Create `/opt/open-mmi` installation directory
* Create isolated Python virtual environment
* Install Python dependencies
* Copy application files
* Install systemd user service
* Install udev rules for CAN interface
* Configure user permissions (video, input groups)
* Start daemon automatically

### Update

```bash
sudo ./scripts/manage.sh update
```

**Features:**

* Automatic backup before update
* Safe merge of changes
* Dependency upgrade
* Systemd and udev rules update
* Automatic rollback on failure
* Daemon restart with verification

### Uninstall

```bash
sudo ./scripts/manage.sh uninstall
```

**Features:**

* Optional backup before removal
* Clean daemon shutdown
* Complete file removal
* udev rules cleanup

### Status

```bash
sudo ./scripts/manage.sh status
```

Shows:

* Installation status
* Installed version
* Daemon running status
* User permissions
* Available backups

### Logs

```bash
sudo ./scripts/manage.sh logs
```

View daemon logs in real-time (Ctrl+C to exit).

### Config

```bash
sudo ./scripts/manage.sh config edit
```

Edit systemd service configuration safely with reload/restart.

---

# Verify Installation

After installation, verify everything works:

```bash
# Check installation status
sudo ./scripts/manage.sh status

# View logs (should show startup messages)
sudo ./scripts/manage.sh logs

# Validate configuration
/opt/open-mmi/venv/bin/python /opt/open-mmi/canbusd/canbusd.py --check
```

---

# systemd Service

Located at:

```text
~/.config/systemd/user/canbusd.service
```

Manages:

* Starting daemon at login
* Restarting on failure
* Logging to systemd journal

View logs:

```bash
# Live logs
journalctl --user -u canbusd -f

# Last 50 lines
journalctl --user -u canbusd -n 50

# Only errors
journalctl --user -u canbusd -p err
```

Control daemon:

```bash
# Start
systemctl --user start canbusd

# Stop
systemctl --user stop canbusd

# Restart
systemctl --user restart canbusd

# Status
systemctl --user status canbusd

# Logs
journalctl --user -u canbusd -f
```

---

# udev Rules

Located at:

```text
/etc/udev/rules.d/80-canbus.rules
```

Handles:

* Bringing up CAN interface (`can0`) at startup
* Setting CAN bitrate to 100000
* Setting permissions on uinput device
* Setting permissions on backlight controls

---

# Troubleshooting

## Daemon Won't Start

```bash
# Check logs
journalctl --user -u canbusd -f

# Validate config
/opt/open-mmi/venv/bin/python /opt/open-mmi/canbusd/canbusd.py --check

# Check permissions
ls -la /sys/class/backlight/
groups $USER
```

## CAN Interface Not Found

```bash
# Check if CAN interface exists
ip link show can0

# Manually bring up interface
sudo ip link set can0 down
sudo ip link set can0 type can bitrate 100000
sudo ip link set can0 up

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Restart daemon
systemctl --user restart canbusd
```

## Permission Denied Errors

```bash
# Add user to required groups
sudo usermod -aG video,input $USER

# Apply immediately (or logout/login)
su - $USER

# Verify
groups $USER
```

## Actions Not Executing

```bash
# Enable debug logging
sudo ./scripts/manage.sh config edit
# Add: Environment="OPEN_MMI_LOG_LEVEL=DEBUG"

# Then restart
systemctl --user restart canbusd

# Check detailed logs
journalctl --user -u canbusd -f
```

## Update Failed

```bash
# Check available backups
ls /opt/open-mmi-backups/

# Restore from backup manually if needed
sudo rm -rf /opt/open-mmi
sudo cp -r /opt/open-mmi-backups/backup-XXXXX /opt/open-mmi
```

---

# Development

Run locally without system installation:

```bash
# Install dependencies
pip install python-can evdev

# Validate configuration
python3 canbusd/canbusd.py --check

# Run daemon
python3 canbusd/canbusd.py

# Or use development script
./scripts/dev_run.sh
```

Development tools are in `dev/` (ignored by git, not used in production).

---

# Contributing

Contributions are welcome:

* New vehicle profiles
* Improved CAN mappings
* New action modules
* Hardware integrations
* Documentation improvements
* Tooling and debugging utilities

Vehicle profiles should remain hardware-focused and not contain user-specific logic.

---

# Safety

This project interfaces directly with vehicle CAN networks.

**Incorrect configuration may affect vehicle behaviour or system usability.**

Use carefully and ensure you understand your vehicle's CAN environment before enabling or modifying mappings.

Never modify vehicle-critical CAN IDs (steering, braking, engine control).

Test new configurations in development mode first.

---

# License

GPL-3.0-only. See LICENSE file for details.
