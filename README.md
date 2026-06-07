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

# Quick Start (5 minutes)

## 1. Get the Code

```bash
git clone https://github.com/Sheepdog-97/open-mmi.git
cd open-mmi
```

## 2. Install

```bash
sudo ./scripts/manage.sh install
```

This will:
- Install system dependencies (Python, CAN utilities, udev)
- Create isolated Python virtual environment
- Install Python packages (python-can, evdev)
- Copy application files to `/opt/open-mmi`
- Install systemd service for auto-start
- Configure user permissions
- Start the daemon

**Requires sudo.** Takes ~2-3 minutes.

## 3. Verify Installation

```bash
sudo ./scripts/manage.sh status
```

Expected output:
```
Status:         ✓ Installed
Install Dir:    /opt/open-mmi
Version:        <current-version>
Service:        ✓ Running
```

## 4. View Logs

```bash
sudo ./scripts/manage.sh logs
```

You should see:
```
[canbusd] Starting canbusd (vehicle=seat_1p, bindings=default)
[canbusd] Loaded X CAN rules
[canbusd] Loaded X bindings
[canbusd] Opening can0...
```

Press Ctrl+C to exit logs.

---

# How It Works

## The Three-Layer Architecture

```
CAN Message from Vehicle
        ↓
[Vehicle Profile] - Interprets raw CAN data into semantic events
        ↓
        Event (e.g., "volume_up")
        ↓
[Bindings] - Maps events to Linux actions
        ↓
        Action (e.g., "audio.volume_up")
        ↓
[Actions] - Python functions that affect the system
        ↓
        System Response (volume increases)
```

## Real Example

When your car sends CAN message `0x5C1 byte0=0x06`:

1. **Vehicle Profile** (`vehicles/seat_1p/config.json`) recognizes this as "volume_up"
2. **Binding** (`bindings/default.json`) maps "volume_up" → `audio.volume_up("+10%")`
3. **Action** (`actions/audio.py`) calls the `volume_up()` function
4. System's audio volume increases by 10%

---

# Full User Journey

## Scenario: You got a new car and need to configure open-mmi

### Step 1: Understand Your Vehicle (30 minutes)

First, understand what CAN messages your car sends:

```bash
# Install CAN monitoring tools (optional, helps with debugging)
sudo apt install can-utils

# Monitor raw CAN messages
candump can0
```

Watch for patterns. For example, when you press volume buttons, note:
- The CAN ID (e.g., 0x5C1)
- The byte index that changes
- What values it sends (0x01, 0x02, 0x06, etc.)

### Step 2: Create Your Vehicle Profile (15 minutes)

Create a new vehicle profile for your car:

```bash
mkdir -p vehicles/my_car
cp vehicles/seat_1p/config.json vehicles/my_car/config.json
nano vehicles/my_car/config.json
```

Edit the configuration with your CAN mappings:

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
      "id": "0x5C1",
      "byte": 0,
      "value": 7,
      "event": "volume_down"
    }
  ],
  "presence": []
}
```

### Step 3: Create Your Bindings (10 minutes)

Create a bindings file that maps events to actions:

```bash
cp bindings/default.json bindings/my_bindings.json
nano bindings/my_bindings.json
```

Configure what happens for each event:

```json
{
  "volume_up": {
    "module": "audio",
    "func": "volume_up",
    "args": ["+5%"]
  },
  "volume_down": {
    "module": "audio",
    "func": "volume_down",
    "args": ["-5%"]
  }
}
```

### Step 4: Test in Development Mode (10 minutes)

Before installing, test your configuration locally:

```bash
# Ensure dependencies are installed
pip install python-can evdev

# Validate your configuration
python3 canbusd/canbusd.py --check

# Output should show:
# [canbusd] config OK
```

If it fails, check:
- JSON syntax (use a JSON validator)
- File paths
- Event names match between profile and bindings

Run in debug mode to see real-time matching:

```bash
OPEN_MMI_LOG_LEVEL=DEBUG OPEN_MMI_VEHICLE=my_car python3 canbusd/canbusd.py
```

Watch for messages like:
```
[canbusd] Match: id=0x5C1 byte0=0x06 -> volume_up
[canbusd] Event dispatched: volume_up
[canbusd] Action executed: audio.volume_up(["+5%"])
```

### Step 5: Configure System Installation (5 minutes)

Once testing works, update the system installation to use your vehicle:

```bash
sudo ./scripts/manage.sh config edit
```

In the `[Service]` section, add:

```ini
Environment="OPEN_MMI_VEHICLE=my_car"
Environment="OPEN_MMI_BINDINGS=my_bindings"
```

Save and exit. The script will reload automatically.

### Step 6: Verify Production Setup (5 minutes)

Check that everything is running with your new config:

```bash
sudo ./scripts/manage.sh status
sudo ./scripts/manage.sh logs
```

You should see your vehicle and bindings loaded.

---

# Project Structure

```
open-mmi/
├── canbusd/
│   └── canbusd.py              ← Main daemon
│
├── vehicles/
│   └── seat_1p/
│       └── config.json         ← CAN message definitions
│   └── my_car/                 ← Your vehicle profile
│       └── config.json
│
├── bindings/
│   ├── default.json            ← Default event→action mappings
│   └── my_bindings.json        ← Your custom mappings
│
├── actions/
│   ├── audio.py                ← Audio control (volume, media)
│   ├── brightness.py           ← Screen brightness
│   ├── keys.py                 ← Virtual media keys
│   ├── screen.py               ← Display power & user switch
│   └── __init__.py
│
├── systemd/
│   └── user/
│       └── canbusd.service     ← Auto-start service
│
├── udev/
│   └── 80-canbus.rules         ← CAN interface setup
│
├── scripts/
│   ├── manage.sh               ← Install/update/uninstall
│   └── dev_run.sh              ← Development runner
│
├── pyproject.toml
├── README.md
└── LICENSE
```

---

# Configuration Reference

## Vehicle Profile Format (`vehicles/*/config.json`)

```json
{
  "rules": [
    {
      "id": "0x5C1",                    // CAN ID (hex string or decimal)
      "byte": 0,                        // Which byte in the message
      "value": 6,                       // Trigger on this value (or "any")
      "event": "volume_up"              // Event name
    }
  ],
  "presence": [
    {
      "id": "0x123",                    // CAN ID to monitor
      "timeout_ms": 1000,               // Consider absent after 1 second silence
      "on_present": "device_detected",  // Event when present
      "on_absent": "device_unplugged"   // Event when absent
    }
  ]
}
```

## Bindings Format (`bindings/*.json`)

```json
{
  "event_name": {
    "module": "audio",         // Action module name
    "func": "volume_up",       // Function to call
    "args": ["+5%"]            // Arguments to pass
  }
}
```

## Environment Variables

Control daemon behavior:

```bash
# Which vehicle profile to load
export OPEN_MMI_VEHICLE=seat_1p

# Which bindings file to use
export OPEN_MMI_BINDINGS=default

# Logging level: DEBUG, INFO, WARNING, ERROR
export OPEN_MMI_LOG_LEVEL=INFO
```

Set in systemd service:
```bash
sudo ./scripts/manage.sh config edit
# Add to [Service] section:
# Environment="OPEN_MMI_LOG_LEVEL=DEBUG"
```

---

# Available Actions

## audio.py - Audio Control

```python
volume_up(step="+5%")      # Increase volume
volume_down(step="-5%")    # Decrease volume
mute_toggle()              # Toggle mute
play_pause()               # Play/pause media
next_track()               # Next track
prev_track()               # Previous track
stop()                     # Stop playback
```

## brightness.py - Screen Brightness

```python
set_percent(percent)       # Set brightness (0-100)
from_can(value)           # Convert CAN byte (0x00-0x64) to brightness
```

## keys.py - Virtual Media Keys

```python
play_pause()              # Send PLAY/PAUSE key
next_track()              # Send NEXT key
prev_track()              # Send PREVIOUS key
stop()                    # Send STOP key
mute_toggle()             # Send MUTE key
volume_up()               # Send VOLUME_UP key
volume_down()             # Send VOLUME_DOWN key
arrow_left()              # Send LEFT ARROW
arrow_right()             # Send RIGHT ARROW
```

## screen.py - Display Control

```python
on()                      # Turn display on
off()                     # Turn display off
wake_and_login(user)      # Wake display and switch user
```

---

# Common Workflows

## Workflow 1: Add a New Control

**Goal:** Make steering wheel buttons control media playback

```bash
# 1. Identify CAN messages from your car
candump can0  # Watch for your buttons

# 2. Update vehicle config
nano vehicles/my_car/config.json
# Add:
# { "id": "0x456", "byte": 1, "value": 1, "event": "play_pause" }

# 3. Update bindings
nano bindings/my_bindings.json
# Add:
# "play_pause": { "module": "keys", "func": "play_pause" }

# 4. Test
python3 canbusd/canbusd.py --check

# 5. Reload in production
systemctl --user restart canbusd
sudo ./scripts/manage.sh logs  # Verify it's running
```

## Workflow 2: Debug an Action Not Working

```bash
# 1. Enable debug logging
sudo ./scripts/manage.sh config edit
# Add: Environment="OPEN_MMI_LOG_LEVEL=DEBUG"

# 2. Watch logs in real-time
sudo ./scripts/manage.sh logs

# 3. Trigger the action and look for:
# - "Match: id=0xXXX byte0=0xXX -> event_name"
# - "Event dispatched: event_name"
# - "Action executed: module.function(...)"
# - Or error messages showing what failed

# 4. Check action module
python3 -c "from actions import audio; audio.volume_up()"
# If this fails, it shows what's broken
```

## Workflow 3: Test Before Installing

```bash
# Clone repo and set up test environment
git clone https://github.com/Sheepdog-97/open-mmi.git
cd open-mmi
pip install python-can evdev

# Create your test config
mkdir -p vehicles/test_car
cp vehicles/seat_1p/config.json vehicles/test_car/config.json
nano vehicles/test_car/config.json

# Validate
python3 canbusd/canbusd.py --check

# Run with debug output
OPEN_MMI_VEHICLE=test_car OPEN_MMI_LOG_LEVEL=DEBUG python3 canbusd/canbusd.py

# Only after this works:
sudo ./scripts/manage.sh install
```

---

# Management Commands

## Installation

```bash
sudo ./scripts/manage.sh install
```

Full installation with all dependencies and auto-start.

## Check Status

```bash
sudo ./scripts/manage.sh status
```

Shows installation info, daemon status, backups.

## View Logs

```bash
sudo ./scripts/manage.sh logs
```

Real-time daemon output. Press Ctrl+C to exit.

## Update

```bash
sudo ./scripts/manage.sh update
```

Safe update with automatic backup and rollback on failure.

## Edit Configuration

```bash
sudo ./scripts/manage.sh config edit
```

Edit systemd service (environment variables, restart behavior).

## Uninstall

```bash
sudo ./scripts/manage.sh uninstall
```

Clean removal with optional backup.

---

# Troubleshooting

## "Daemon won't start"

```bash
sudo ./scripts/manage.sh logs
```

Look for error messages. Common issues:
- Config file syntax error → Check JSON
- Vehicle profile not found → Check OPEN_MMI_VEHICLE path
- Missing dependencies → Run `pip install python-can evdev`

## "CAN messages not being received"

```bash
# Check CAN interface
ip link show can0

# Should show: can0: <BROADCAST,NOTRAILERS,UP,LOWER_UP>

# If down, bring it up:
sudo ip link set can0 up

# Monitor raw messages:
candump can0
```

## "Actions not executing even though rules match"

```bash
# Enable debug logging
sudo ./scripts/manage.sh config edit
# Add: Environment="OPEN_MMI_LOG_LEVEL=DEBUG"

# Watch logs
sudo ./scripts/manage.sh logs

# Look for: "Action executed" or error messages
# If action error, check that module/function exist:
python3 -c "from actions.audio import volume_up; volume_up()"
```

## "Permission denied" errors

```bash
# Check user groups
groups $USER

# Must include: video input

# Add if missing:
sudo usermod -aG video,input $USER

# Apply (or logout/login):
newgrp video
```

---

# Requirements

## System

* Linux with systemd
* Python 3.9+
* CAN interface (e.g., `can0`)
* ~100MB disk space

## Optional System Tools

```bash
# For audio control
sudo apt install pulseaudio-utils playerctl

# For brightness
sudo apt install brightnessctl

# For display
sudo apt install xserver-xorg-core x11-utils

# For user switching
sudo apt install lightdm-tools  # or your display manager
```

---

# Architecture Deep Dive

## How the CAN Daemon Works

1. **Load Configuration** - Read vehicle profile and bindings
2. **Open CAN Interface** - Connect to `can0` and listen for messages
3. **Receive Messages** - CAN messages arrive from the vehicle
4. **Match Rules** - Check if message matches any configured rule
5. **Generate Event** - If matched, trigger the event name
6. **Lookup Binding** - Find which action handles this event
7. **Execute Action** - Call the Python function with arguments
8. **System Effect** - Action changes Linux system state

## Hot-Reload Feature

Without restarting, you can:

```bash
# Modify config
nano vehicles/my_car/config.json

# Signal daemon to reload
kill -HUP $(pgrep -f "python.*canbusd.py")

# Or systemctl
systemctl --user reload canbusd

# Daemon will reload in seconds, no downtime
```

---

# Contributing

Contributions welcome:
- New vehicle profiles
- New action modules
- Improved CAN mappings
- Documentation improvements

---

# Safety

**WARNING:** This interfaces with vehicle CAN buses.

Incorrect configuration may:
- Trigger unexpected behaviors
- Affect vehicle operation
- Create safety hazards

**Always:**
- Test configurations in development mode first
- Never modify vehicle-critical CAN IDs (steering, braking, engine)
- Start with known-good configurations
- Monitor logs when deploying to production

---

# License

GPL-3.0-only. See LICENSE file for details.
