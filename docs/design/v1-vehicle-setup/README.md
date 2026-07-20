# V1 vehicle setup management

Status: implementation in progress — core apply, custom copy, editing and lifecycle management complete

This design defines a local, explicit setup path for selecting an Open MMI vehicle
profile, bindings and SocketCAN input without editing systemd or udev files by hand.

It does not implement CAN transmission, automatic vehicle detection or simultaneous
multi-bus reception. The first delivery keeps the currently supported one-active-bus
runtime and makes that limitation visible in the UI.

## User outcome

A user should be able to:

1. open **Settings → Vehicle setup**;
2. choose a maintained or custom vehicle profile;
3. choose maintained or custom bindings independently;
4. inspect the logical CAN bus, expected bitrate and selected SocketCAN interface;
5. review validation and compatibility warnings;
6. apply the setup explicitly;
7. see whether the configuration loaded and whether the interface is present;
8. create a named custom copy from a maintained template;
9. edit and validate that custom copy without changing the active runtime;
10. duplicate, rename or delete inactive custom entries explicitly; and
11. return to a maintained profile without leaving a custom path override active.

The normal path must not require a terminal. Existing management commands remain an
administrator and recovery interface over the same backend contract.

## Scope

The V1 setup-management scope includes:

- discovery of installed maintained profiles and bindings;
- discovery of user-owned custom profiles and bindings;
- explicit maintained/custom source labels;
- independent profile and bindings selection;
- one active named CAN bus;
- selection of an already-provisioned SocketCAN interface;
- profile-driven udev provisioning where declared;
- a canonical root-owned selection descriptor;
- preview, validation, apply, verification and automatic restoration;
- creation of custom copies from installed maintained templates;
- draft editing with atomic saves and revision checks;
- revision-bound duplicate, rename and inactive-only deletion for custom entries;
- machine-readable active configuration and CAN health status; and
- an 800×480 Settings workflow with inline feedback.

## Non-goals

The first delivery does not include:

- several simultaneous SocketCAN listeners;
- automatic vehicle or bitrate detection;
- arbitrary filesystem browsing;
- browser-supplied paths, commands, service names or udev rules;
- editing files under `/opt/open-mmi`;
- automatic migration, refresh or deletion of custom files;
- CAN transmit, coding, adaptation or actuator control;
- a visual editor for every status-rule variant; or
- automatic merging of maintained template changes into custom copies.

## Existing contracts retained

The design retains these current contracts:

- maintained vehicle profiles are installed under
  `/opt/open-mmi/vehicles/<profile>/config.json`;
- maintained bindings are installed under `/opt/open-mmi/bindings/<bindings>.json`;
- custom vehicle profiles live under
  `~/.config/open-mmi/vehicles/<profile>/config.json`;
- custom bindings live under `~/.config/open-mmi/bindings/<bindings>.json`;
- custom files are sacred and opt-in;
- `canbusd` remains a passive SocketCAN consumer;
- interface provisioning remains an explicit management operation; and
- configuration reload keeps the last known-good in-memory rules on parse failure.

## Decisions

### Maintained means installed

The production catalogue and runtime resolve maintained files from `/opt/open-mmi`, not
from a mutable Git checkout. Development checkout use must be an explicit development
mode. This keeps the active profile aligned with the installed Open MMI build.

### Custom files are never implicitly selected

Creating `~/.config/open-mmi/vehicles/example/config.json` does not activate it. The
canonical selection must name source `custom` and identifier `example` before the
runtime uses that file.

### Selection is canonical; generated files are derived

A root-owned descriptor records the intended configuration. The systemd drop-in and
udev rules are generated outputs which may be checked, recreated or restored.

### Save and activate are separate

A custom draft may be saved without changing the configuration loaded by the
running daemon. Coordinator-managed exact profile and bindings paths are pinned for
the lifetime of the daemon process; activation is a separate reviewed operation that
restarts the daemon. Invalid drafts cannot be activated.

### Absence is not activation failure

A sleeping vehicle or disconnected CAN adapter must not make configuration application
fail. Verification checks that the expected configuration loaded. Adapter presence and
recent frames are reported separately as runtime health.

### One coordinator owns privileged application

The dashboard never runs `sudo` or `scripts/manage.sh`. A narrow configuration
coordinator accepts only fixed schema-validated operations and performs the root-owned
parts of an apply transaction.

### Multi-CAN is a separate runtime milestone

The saved format records bus-to-interface assignments even though V1 activates one bus.
This avoids a state-format replacement later, but it is not a claim that simultaneous
multi-bus reception already works.

## Component map

```text
Settings UI
  -> loopback same-origin dashboard API
      -> read-only catalogue and draft helpers
      -> restricted configuration coordinator
          -> canonical selection descriptor
          -> generated user systemd drop-in
          -> generated root udev rules
          -> canbusd restart and verification
  <- active configuration and per-bus health
```

## Design documents

- [`configuration-contract.md`](configuration-contract.md) defines ownership,
  catalogue identities, canonical state and API payloads.
- [`security-and-apply.md`](security-and-apply.md) defines the privilege boundary,
  transaction, verification and restoration behaviour.
- [`setup-ui.md`](setup-ui.md) defines the tablet workflow and status language.
- [`validation-and-editing.md`](validation-and-editing.md) defines custom-copy,
  validation and editor boundaries.
- [`multi-can-runtime.md`](multi-can-runtime.md) records the later simultaneous-bus
  architecture without expanding V1 scope.
- [`qualification.md`](qualification.md) defines delivery slices and acceptance gates.

## Required implementation order

1. Reconcile existing ownership and lookup documentation.
2. Extract shared profile/bindings resolution and validation from shell-facing code.
3. Add read-only catalogue and active-runtime status.
4. Add the canonical descriptor and privileged apply transaction.
5. Qualify maintained selection through CLI and `vcan` before exposing writes in UI.
6. Add the Vehicle setup selector and review screen.
7. Add custom copy/import, revision-safe JSON editing, validation and activation.
8. Add rename, duplicate and protected deletion, then last-known-good user revisions.
9. Add bindings editing through an explicit action registry.
10. Add broader structured profile editing only after rule schemas are complete.
11. Treat simultaneous multi-CAN as its own reviewed beta milestone.
