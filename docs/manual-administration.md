# Manual administration

This is the terminal reference for installation, development deployment,
recovery, service control, update policy, logs, and low-level configuration.
Normal maintained-vehicle use should begin with the desktop application,
[Getting started](getting-started.md), and
[Vehicle setup](vehicle-setup.md).

## Install, update from a checkout, and uninstall

```bash
sudo ./scripts/manage.sh install
sudo ./scripts/manage.sh update
sudo ./scripts/manage.sh status
sudo ./scripts/manage.sh logs
sudo ./scripts/manage.sh uninstall
```

The checkout-driven `update` command is important when:

- deploying a different development branch;
- repairing an installation when the browser workflow is unavailable;
- authorizing a new recorded source/upstream;
- updating from a source tree before a release channel is available.

It is not the preferred routine update interaction for a vehicle owner once the
installed UI update workflow is working.

Uninstall can also be run from the installed copy if the source checkout has
been removed:

```bash
sudo /opt/open-mmi/scripts/manage.sh uninstall
```

## Browser update workflow and CLI equivalents

The normal installed development workflow is under:

```text
Settings → System → Software updates
```

Equivalent inspection and fixed-action commands are:

```bash
open-mmi-config updates status
open-mmi-config updates check
open-mmi-config updates readiness
open-mmi-config updates coordinator
open-mmi-config updates prepare
open-mmi-config updates install
```

The browser and these commands use the installer-recorded source and root-owned
policy. They do not accept a repository, ref, path, command, or rollback target.

At this development checkpoint, confirmed installation is intended for the
recorded nightly source. The policy schema also accepts `beta` and `stable`, but
no public beta or stable release is currently published.

Administrators select policy with:

```bash
sudo open-mmi-config updates channel nightly
sudo open-mmi-config updates channel beta
sudo open-mmi-config updates channel stable
```

There is no browser channel editor, unattended schedule, downgrade workflow, or
caller-selected rollback. Failed installations use automatic restoration.

When switching development branches, deploy the chosen branch once through the
checkout so the installed source descriptor is updated:

```bash
git switch <branch>
git pull --ff-only
sudo ./scripts/manage.sh update
```

## Launcher and desktop behavior

```bash
open-mmi-launcher
open-mmi-launcher web
open-mmi-launcher tui
open-mmi-launcher --choose --ask-remember
open-mmi-config launcher status
open-mmi-config launcher default web
open-mmi-config launcher default tui
open-mmi-config launcher autostart enable
open-mmi-config launcher autostart disable
```

The UI equivalents for default interface and opening after graphical login are
under **Settings → System**.

The dashboard service normally starts on demand. Permanent service control is an
advanced operation:

```bash
open-mmi-config dashboard status
open-mmi-config dashboard start
open-mmi-config dashboard stop
open-mmi-config dashboard restart
open-mmi-config dashboard enable
open-mmi-config dashboard disable
```

See [Desktop shell](desktop-shell.md) for managed browser ownership, chooser
fallback, health checks, and desktop file behavior.

## Vehicle configuration inspection

```bash
open-mmi-config vehicle-setup status
open-mmi-config vehicle-setup catalogue
open-mmi-config vehicle-setup coordinator
open-mmi-config vehicle-setup preview seat-leon-1p-pq35 default \
  --bus comfort \
  --interface can0
```

The CLI preview is non-mutating. The UI owns normal review and confirmed Apply.

For maintained-profile recovery when the UI cannot be used:

```bash
sudo ./scripts/manage.sh config apply-profile seat-leon-1p-pq35 default
sudo ./scripts/manage.sh config paths
```

Advanced service-environment editing remains available:

```bash
sudo ./scripts/manage.sh config edit-service
```

Direct `OPEN_MMI_VEHICLE_CONFIG` and `OPEN_MMI_BINDINGS_FILE` overrides are
supported for development and unusual recovery cases. They are not the normal
custom-profile workflow and must not be described as automatically discovered.
See [Profile and bindings ownership](profile-ownership.md).

## Terminal status UI

The terminal UI remains useful over SSH, during graphical recovery, and for
compact diagnostics:

```bash
open-mmi-status
open-mmi-status --once
open-mmi-status --raw
```

![Open MMI terminal status dashboard](images/status-dashboard-active.png)

Additional terminal states are retained as diagnostic evidence:

![Closed vehicle state in the terminal status dashboard](images/status-dashboard-closed.png)

![Lighting state in the terminal status dashboard](images/status-dashboard-lighting.png)

These images are intentionally secondary to the Web dashboard screenshots in
the project README.

## Installation and service diagnostics

The management script reports installed paths and service state:

![Open MMI install status](images/install-status.png)

Its command overview remains useful for recovery:

![Open MMI management help](images/manage-help.png)

The historical terminal-driven update flow remains available:

![Open MMI update flow](images/update-flow.png)

Inspect daemon activity with:

```bash
sudo ./scripts/manage.sh logs
```

![Open MMI daemon logs](images/daemon-logs.png)

Use `Ctrl+C` to stop a live log stream.

## Jellyfin configuration

The normal path is **Settings → Media → Jellyfin setup**. CLI equivalents are:

```bash
open-mmi-config jellyfin status
open-mmi-config jellyfin setup
open-mmi-config jellyfin test
open-mmi-config jellyfin clear
open-mmi-config dashboard restart
```

Persistent credentials are stored in:

```text
~/.config/open-mmi/dashboard.env
```

The parent directory is private and the file is mode `0600`. Do not copy this
file into the repository.

## Important locations

```text
/opt/open-mmi/                              installed application
/etc/open-mmi/vehicle-configuration.json    canonical vehicle selection
/etc/open-mmi/update-policy.json             update channel policy
~/.config/open-mmi/                          private user configuration
~/.config/open-mmi/vehicles/                 custom vehicle profiles
~/.config/open-mmi/bindings/                 custom bindings
~/.config/open-mmi/dashboard.env             dashboard provider credentials
~/.config/open-mmi/launcher.json              launcher preference
~/.config/autostart/open-mmi.desktop          open-after-login entry
~/.config/systemd/user/                       user service units/drop-ins
/etc/udev/rules.d/80-canbus.rules             generated CAN provisioning
```

Treat custom profile and bindings content as sacred user data. Install, update,
and Apply must not silently overwrite, migrate, or delete it.

## Development and contributor commands

```bash
open-mmi-config vehicle-setup events --search "human meaning"
open-mmi-config vehicle-setup statuses --search "human meaning"
open-mmi-config vehicle-setup actions --search "local behavior"
open-mmi-config vehicle-setup scaffold --help
open-mmi-config vehicle-setup capture --help
open-mmi-config vehicle-setup conform --root .
open-mmi-config vehicle-setup replay --root . seat-leon-1p-pq35
open-mmi-config vehicle-setup qualification report --root .
```

These commands belong to research, review, and maintenance rather than normal
in-car operation.
