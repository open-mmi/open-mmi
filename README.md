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
- hot-reload config
- vehicle profiles
- user bindings
- modular actions
- off-car safe mode

---

# Architecture

open-mmi separates:

| Layer | Purpose |
|---|---|
| Vehicle Config | What CAN messages mean |
| Bindings | What should happen |
| Actions | How Linux performs it |

Flow:

```text
CAN message
    ↓
Vehicle event
    ↓
User binding
    ↓
Linux action
```

Example:

```text
0x5C1 byte0=0x06
    ↓
volume_up event
    ↓
audio.volume_up("+5%")
```

---

# Project Structure

```text
open-mmi/
├── canbusd/
├── vehicles/
├── bindings/
├── actions/
├── systemd/
└── udev/
```

---

# Vehicle Profiles

Vehicle profiles define CAN mappings.

Example:

```json
{
  "id": "0x5C1",
  "byte": 0,
  "value": 6,
  "event": "volume_up"
}
```

Profiles live in:

```text
vehicles/<vehicle_name>/config.json
```

---

# Bindings

Bindings map events to actions.

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

Bindings live in:

```text
bindings/default.json
```

Users can customize bindings without modifying vehicle configs.

---

# Actions

Actions are reusable Linux functionality modules.

Examples:
- media keys
- audio control
- brightness control
- screen wake/sleep

Located in:

```text
actions/
```

---

# Requirements

- Linux
- Python 3
- SocketCAN

Python packages:

```bash
pip install -r requirements.txt
```

---

# Running

## Validate configuration

```bash
python3 canbusd/canbusd.py --check
```

## Run daemon

```bash
python3 canbusd/canbusd.py
```

---

# systemd

Example service file:

```text
systemd/canbusd.service
```

---

# udev

Example CAN interface setup rules:

```text
udev/80-canbus.rules
```

---

# Contributing

Contributions are welcome:
- new vehicle mappings
- new actions
- hardware integrations
- documentation
- tooling

Vehicle profiles should avoid hardcoded user-specific behavior.

---

# Safety

This project interacts with vehicle CAN networks.

Use carefully and at your own risk.

Avoid transmitting onto safety-critical CAN networks unless you understand the implications.
