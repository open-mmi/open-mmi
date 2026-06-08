# Contributing to Open MMI

Thanks for your interest in contributing to Open MMI.

Open MMI is a Linux vehicle MMI integration framework that connects vehicle CAN-bus data to configurable Linux actions, persistent vehicle state, and UI/dashboard consumers.

> Where hex meets human form.

## Project Direction

Open MMI is designed to be profile-driven.

Vehicle-specific CAN knowledge should live in:

```text
vehicles/<profile>/config.json
```

Core Python should stay generic wherever possible.

Good contributions usually improve one of these areas:

- vehicle profiles
- CAN decode notes
- status mappings
- action modules
- dashboard/UI consumers
- install/update tooling
- documentation
- tests

## Branch Workflow

`main` is the stable backend branch.

Use feature or beta branches for development:

```bash
git switch main
git pull origin main
git switch -c beta/my-feature
```

For real vehicle testing, keep work on a beta branch until it has been tested safely.

## Before Opening a Pull Request

Please check:

```bash
python3 -m py_compile canbusd/core.py canbusd/status_rules.py canbusd/status_bus.py
python3 -m json.tool vehicles/seat_1p/config.json >/dev/null
python3 -m json.tool bindings/default.json >/dev/null
bash -n scripts/manage.sh
```

If your change affects install/update behaviour, test the management script where possible:

```bash
sudo ./scripts/manage.sh status
sudo ./scripts/manage.sh logs
```

## Vehicle Profiles

Vehicle profiles should contain vehicle-specific CAN IDs, byte positions, masks, values, and status mappings.

Do:

```text
vehicles/seat_1p/config.json
vehicles/my_vehicle/config.json
```

Avoid hardcoding vehicle-specific CAN IDs or values in:

```text
canbusd/core.py
canbusd/status_rules.py
actions/
ui/
```

The backend should provide generic primitives such as:

- rules
- presence
- status
- bool
- enum
- bitfield
- percent
- raw

## Safety Guidelines

Open MMI currently focuses on passive CAN receive and local Linux actions.

Do not add vehicle CAN transmit/control behaviour without a separate safety design, explicit allowlists, clear documentation, and extensive testing.

Avoid features that could:

- distract the driver
- misrepresent vehicle state
- interfere with vehicle-critical systems
- encourage unsafe testing on public roads

Test new vehicle mappings carefully and preferably while stationary before relying on them during normal driving.

## User Config Safety

Application files are installed to:

```text
/opt/open-mmi
```

User-editable config should live in:

```text
~/.config/open-mmi
```

Contributions should not overwrite user config during install or update.

## Commit Style

Use short, practical commit messages, for example:

```text
add Seat 1P door status mapping
publish vehicle presence state from presence rules
add desktop launcher for dashboard
fix updater copy order
```

## Pull Request Expectations

A good pull request explains:

- what changed
- why it changed
- how it was tested
- whether it was tested in a vehicle
- whether it touches CAN receive, CAN transmit, actions, install/update, or UI
- whether documentation needs updating

## Reporting Bugs

When reporting a bug, include:

- OS/distro
- install method
- branch or tag
- CAN adapter if relevant
- relevant logs from `sudo ./scripts/manage.sh logs`
- whether the issue happens off-car, in-car, or both

Please avoid posting sensitive vehicle data such as full VINs, private locations, or personal details.
