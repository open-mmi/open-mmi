# Contributing to Open MMI

Thanks for your interest in contributing to Open MMI.

`open-mmi` is an early GPLv3 vehicle integration project that connects passive vehicle CAN-bus data to configurable Linux actions, persistent vehicle state, and UI/dashboard consumers.

> Where hex meets human form.

---

## Current project status

`open-mmi` is currently an alpha/backend project.

The current maintainer-tested reference vehicle is:

```text
Seat Leon 1P / VAG PQ35
```

This is not yet a polished infotainment replacement, final tablet UI, or multi-vehicle supported product.

Useful background docs:

```text
docs/project-philosophy.md
docs/versioning.md
docs/release-checklist.md
docs/status-snapshot.md
SECURITY.md
```

---

## Project direction

Open MMI is designed to be profile-driven.

Vehicle-specific CAN knowledge should live in:

```text
vehicles/{profile}/config.json
```

Core Python should stay generic wherever possible.

Good contributions usually improve one of these areas:

* vehicle profiles
* CAN decode notes
* status mappings
* action modules
* dashboard/UI consumers
* install/update tooling
* documentation
* tests
* screenshots or example output
* replay/demo data once tooling supports it

The goal is to make vehicle integration knowledge reusable, not to hardcode one car into the daemon.

---

## Branch workflow

`main` is intended to stay conservative and usable.

Use feature or beta branches for development:

```bash
git switch main
git pull origin main
git switch -c beta/my-feature
```

For real vehicle testing, keep work on a beta branch until it has been tested safely.

Avoid mixing unrelated work in one branch. For example:

```text
Good:
  beta/seat-1p-lighting
  beta/status-dashboard
  beta/can-runtime-config

Avoid:
  beta/fix-everything
```

Runtime behaviour changes, udev changes, install changes, and CAN interface setup changes should usually be developed in their own beta branches.

### Managed updater behaviour on development branches

The managed updater is intentionally bound to the branch that produced the
installed runtime. Switching branches without deploying the new branch makes
Settings report a branch mismatch and disables browser update actions.

After a development branch contains the build to test, authorize and deploy it
once from the terminal. For example:

```bash
git switch beta/status-dashboard
git pull --ff-only origin beta/status-dashboard
sudo ./scripts/manage.sh update
```

Later forward commits on that recorded nightly branch can use **Check**,
**Prepare**, and **Install** in Settings. To return the managed installation to
`main`:

```bash
git switch main
git pull --ff-only origin main
sudo ./scripts/manage.sh update
```

The terminal update records the newly deployed branch and upstream. The
browser does not offer a branch selector and must not be used to authorize an
arbitrary repository or ref.

---

## Issue templates

Please use the GitHub issue templates where possible.

Current templates include:

```text
Vehicle profile request
CAN capture submission
Bug report
Feature request
```

Structured issues are much easier to review than free-form reports.

For vehicle support, useful information includes:

* vehicle make/model/year
* platform/chassis if known
* CAN adapter used
* capture point used
* bitrate
* candump logs or short excerpts
* what physical state was triggered
* VCDS/OBDeleven/diagnostic notes if available
* whether the mapping was tested on a real vehicle

Please avoid posting sensitive vehicle data such as full VINs, private locations, personal details, credentials, or complete logs containing sensitive information.

---

## Before opening a pull request

Please check:

```bash
python3 -m py_compile canbusd/core.py canbusd/can_runtime.py canbusd/status_rules.py canbusd/status_bus.py
python3 -m unittest discover -s tests
python3 -m json.tool vehicles/seat_1p/config.json >/dev/null
python3 -m json.tool bindings/default.json >/dev/null
bash -n scripts/manage.sh
```

If your change affects install/update behaviour, test the management script where possible:

```bash
sudo ./scripts/manage.sh status
sudo ./scripts/manage.sh logs
```

If your change affects documentation only, say that clearly in the pull request.

---

## Pull request expectations

A good pull request explains:

* what changed
* why it changed
* how it was tested
* whether it was tested in a vehicle
* whether it touches CAN receive, CAN transmit, actions, install/update, udev, service permissions, or UI
* whether documentation needs updating
* whether the change is experimental, alpha, or intended as a longer-term interface

If the change affects the status snapshot, update or check:

```text
docs/status-snapshot.md
```

If the change affects release/version wording, update or check:

```text
docs/versioning.md
docs/release-checklist.md
```

If the change affects permissions, local actions, CAN safety, or trusted config, update or check:

```text
SECURITY.md
```

---

## Vehicle profiles

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

* rules
* presence
* status
* bool
* enum
* bitfield
* percent
* raw

Vehicle profiles should be reviewable by someone who understands the vehicle but may not understand the full daemon internals.

---

## CAN capture contributions

CAN captures are useful, but they need context.

When submitting a capture, include:

* vehicle make/model/year
* platform/chassis if known
* adapter used
* capture point
* bitrate
* exact actions performed
* approximate timing of each action
* any known CAN IDs or byte changes
* diagnostic tool notes if relevant

Example action notes:

```text
00:00 ignition on
00:05 sidelights on
00:10 dipped beam on
00:15 left indicator
00:20 hazards on
00:25 brake pressed
00:30 handbrake applied
```

Good capture notes make decoding much easier.

---

## Status snapshot and UI consumers

Dashboards and UI consumers should read the decoded status snapshot rather than parsing raw CAN frames directly.

See:

```text
docs/status-snapshot.md
```

UI consumers should:

* handle missing fields
* handle stale or absent snapshots
* avoid hardcoding vehicle-specific CAN IDs
* display decoded state where possible
* clearly label raw/debug values
* avoid treating decoded state as safety-critical truth

Vehicle-specific CAN knowledge belongs in vehicle profiles, not UI code.

---

## Safety guidelines

Open MMI currently focuses on passive CAN receive and local Linux actions.

Do not add vehicle CAN transmit/control behaviour without:

* a separate safety design
* explicit allowlists
* clear user-facing warnings
* maintainer review
* extensive off-car testing
* controlled real-vehicle testing
* documentation explaining the risk

Avoid features that could:

* distract the driver
* misrepresent vehicle state
* interfere with vehicle-critical systems
* encourage unsafe testing on public roads

Test new vehicle mappings carefully and preferably while stationary before relying on them during normal driving.

Decoded status is informational and should not be treated as a replacement for OEM warnings, diagnostics, safety systems, or driver judgement.

---

## Trusted configuration

Vehicle profiles and bindings are trusted local configuration.

Bindings can map decoded vehicle events to Python action modules. This is intentional, but it means bindings are not just passive data.

A malicious or careless binding may trigger unwanted local actions.

Only use profiles, bindings, action modules, scripts, and udev rules that you trust or have reviewed.

---

## User config safety

Application files are installed to:

```text
/opt/open-mmi
```

User-editable config should live in:

```text
~/.config/open-mmi
```

Contributions should not overwrite user config during install or update.

Install/update changes should preserve the safe user config workflow.

---

## Local permissions

Some installs may need permissions for local Linux actions such as virtual input, brightness control, or screen wake/sleep behaviour.

These permissions are local security tradeoffs.

A system with these permissions should be treated as a trusted local vehicle computer, not as a shared untrusted desktop.

If your contribution changes permissions, udev rules, input behaviour, backlight access, or service behaviour, update:

```text
SECURITY.md
```

---

## Commit style

Use short, practical commit messages.

Examples:

```text
add Seat 1P door status mapping
publish vehicle presence state from presence rules
add desktop launcher for dashboard
fix updater copy order
document status snapshot interface
add issue templates for community reports
```

Prefer commits that do one clear thing.

---

## Documentation style

Keep documentation honest and specific.

Use clear maturity labels:

```text
working / tested
experimental
planned
unsupported
unknown
```

Avoid making claims that are ahead of tested behaviour.

For example, prefer:

```text
CLI dashboard prototype
```

over:

```text
finished tablet UI
```

Prefer:

```text
Seat 1P / VAG PQ35 maintainer-tested reference profile
```

over:

```text
full VAG support
```

---

## Reporting bugs

When reporting a bug, include:

* OS/distro
* install method
* branch, tag, or commit
* CAN adapter if relevant
* vehicle profile if relevant
* capture point if relevant
* relevant logs from `sudo ./scripts/manage.sh logs`
* whether the issue happens off-car, in-car, or both

Please avoid posting sensitive vehicle data such as full VINs, private locations, personal details, credentials, or complete logs containing sensitive information.

---

## Releases

Do not create a GitHub Release casually.

A git tag is a source checkpoint.

A GitHub Release is a public artefact for users and contributors.

Before creating a GitHub Release, check:

```text
docs/release-checklist.md
docs/versioning.md
```

Release notes should clearly state:

* source tag
* project maturity status
* tested environment
* tested vehicle/profile, if applicable
* highlights
* known limitations
* safety/security notes
* contribution notes

---

## Licence

By contributing, you agree that your contribution will be distributed under the project licence:

```text
GPL-3.0-only
```

See:

```text
LICENSE
```
