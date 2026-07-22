# Troubleshooting

Start with the UI where possible. Use terminal commands when the launcher,
dashboard, authorization, or local services prevent the UI from reporting a
useful state.

## The desktop shortcut does not appear

Run the managed update/install path from the source checkout:

```bash
sudo ./scripts/manage.sh update
```

Check:

```bash
ls -l ~/.local/share/applications/open-mmi.desktop
ls -l ~/.local/share/applications/open-mmi-chooser.desktop
ls -l "$(xdg-user-dir DESKTOP)/Open MMI.desktop"
```

Refresh the application menu or log out and back in after a new desktop entry is
installed.

## The shortcut opens the wrong interface

Open **Open MMI Interface Chooser**, or run:

```bash
open-mmi-launcher --choose --ask-remember
```

Set the normal default from **Settings → System** or:

```bash
open-mmi-config launcher default web
```

## The dashboard does not open

Check the local service and health state:

```bash
open-mmi-config dashboard status
open-mmi-config dashboard restart
curl http://127.0.0.1:8765/api/health
```

Then inspect logs:

```bash
sudo ./scripts/manage.sh logs
```

The launcher normally starts the service on demand, so a disabled service at
login is not by itself a fault.

## Vehicle Setup or browser updates say the coordinator is unavailable

A fresh install may add the account to `open-mmi-config` or
`open-mmi-update`. The current desktop session cannot inherit those groups.

Check:

```bash
groups "$USER"
open-mmi-config vehicle-setup coordinator
open-mmi-config updates coordinator
```

Log out and back in once, or reboot, after group membership changes.

## Apply is disabled

Open **Review current setup** or **Review changes** first. Apply requires:

- a current valid preview;
- an available privileged coordinator;
- no active update/configuration/lifecycle lock;
- exact current and target revisions;
- explicit confirmation.

Refresh Vehicle Setup if the preview became stale. Inspect coordinator state:

```bash
open-mmi-config vehicle-setup coordinator
```

A previous unverified restoration intentionally blocks another Apply until
recovery succeeds.

## Apply succeeded but no vehicle data appears

Configuration activation and live CAN health are separate.

Check:

```bash
ip link show can0
candump can0
```

Confirm:

- the adapter is detected;
- the interface is up;
- bitrate matches the selected bus;
- CAN high, CAN low, and required ground are connected correctly;
- the selected connection point exposes the expected frames;
- the vehicle bus is awake;
- the selected profile and bus match the hardware.

A sleeping vehicle, disconnected adapter, or no recent frames does not mean that
the profile failed to load.

## The CAN service will not start

```bash
sudo ./scripts/manage.sh status
sudo ./scripts/manage.sh logs
```

Common causes include:

- invalid profile or bindings JSON;
- invalid semantic configuration;
- missing installed files or dependencies;
- unsafe ownership, permissions, or symlinks;
- an invalid explicit environment override;
- a conflicting additional systemd drop-in;
- a failed generated runtime or provisioning file.

Vehicle Setup keeps last-known-good in-memory rules on ordinary parse/reload
failure. Coordinator-managed Apply additionally restores the previous generated
configuration when a post-mutation failure occurs.

## A custom save did not change the running vehicle behavior

This is expected. Saving a custom profile or bindings file does not activate it.
The running managed daemon pins the exact revisions it loaded until a reviewed
Apply restarts it.

Close the editor, choose **Review current setup**, verify the saved revision, and
confirm **Apply setup**.

## A custom item cannot be renamed or deleted

Active custom profiles and bindings are protected from rename and deletion.
Select and Apply another maintained or custom item first. Duplicate remains
available because it leaves the active source untouched.

A stale revision also blocks lifecycle operations. Refresh Vehicle Setup before
retrying.

## An update check fails or says the remote differs

Network failure is not treated as “up to date.” Check:

```bash
open-mmi-config updates status
open-mmi-config updates check
open-mmi-config updates readiness
open-mmi-config updates coordinator
```

The installed branch/upstream must match the source descriptor recorded by the
managed installer. To deliberately deploy another development branch:

```bash
git switch <branch>
git pull --ff-only
sudo ./scripts/manage.sh update
```

At the current development checkpoint, the browser install workflow is intended
for nightly. No public beta or stable release is presently available.

## A prepared or installed update failed

Inspect the bounded coordinator state first:

```bash
open-mmi-config updates coordinator
```

The installer performs post-update service and dashboard health checks and uses
automatic restoration after a failed deployment. Manual browser-selected
rollback is intentionally unavailable.

Use system journals only as an administrator diagnostic; the browser does not
expose raw privileged command output.

## User overrides are not used

Files under `~/.config/open-mmi` are not selected merely because they exist.
Normal custom selection occurs through Vehicle Setup and the canonical
descriptor.

Direct environment overrides are advanced and explicit:

```text
OPEN_MMI_VEHICLE_CONFIG
OPEN_MMI_BINDINGS_FILE
```

Inspect active paths with:

```bash
sudo ./scripts/manage.sh config paths
```

See [Profile and bindings ownership](profile-ownership.md).

## Permission denied for display or virtual input actions

Check account groups:

```bash
groups "$USER"
```

Some local actions may require groups such as:

```text
video input
```

After an administrator changes those memberships, log out and back in. These
permissions are a local security tradeoff and should be granted only on a trusted
vehicle computer.

## More detailed recovery guidance

- [Manual administration](manual-administration.md)
- [Desktop shell](desktop-shell.md)
- [Runtime hardening](runtime-hardening.md)
- [Vehicle setup](vehicle-setup.md)
