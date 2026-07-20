# Delivery and qualification

## Delivery slices

### Slice 0: contract cleanup

- make profile ownership language consistent;
- define maintained production resolution as installed `/opt/open-mmi` content;
- document explicit development checkout mode;
- correct the `config paths` lookup description;
- state that creating a custom file does not activate it; and
- amend the dashboard read-only constraint to permit explicit local setup while
  retaining the no-CAN-transmit boundary.

Gate: documentation and existing behaviour have one unambiguous contract.

### Slice 1: validation and catalogue

- shared identifiers and fixed-root resolution;
- profile and bindings validators;
- profile/bindings compatibility report;
- maintained/custom catalogue;
- interface discovery;
- read-only active runtime status; and
- CLI status command using the same backend.

Gate: no mutation endpoints; malformed and symlinked fixtures fail closed.

### Slice 2: canonical state and coordinator

Current foundation status: the root-owned coordinator service, persistent state schema, recovery path, dedicated authorization group, configuration/update/lifecycle lock primitives, and independent non-mutating preview action are implemented. Dashboard and CLI preview now cross the fixed coordinator socket. Managed installation is not considered successful until the service is active, its socket exists, and a status round trip succeeds; prepared rollback preserves the previous coordinator unit and fixed-path environment. Apply, systemd/udev mutation, runtime verification and restoration remain gated.

- root-owned descriptor;
- deterministic plan rendering;
- dedicated configuration transaction lock/state;
- preview and apply coordinator actions;
- systemd/udev generation;
- restart, verification and automatic restoration; and
- update/configuration lifecycle exclusion.

Gate: maintained selection qualifies through CLI on `vcan` and restoration tests.

### Slice 3: maintained-selection UI

- Vehicle setup Settings category;
- profile and bindings selectors;
- one-bus/interface selector;
- compatibility and provisioning preview;
- apply confirmation;
- local progress and final status; and
- technical detail disclosure.

Gate: browser tests pass at 800×480 and portrait; real device retains setup across reboot
and adapter hotplug.

### Slice 4: custom copies

- create from installed template;
- provenance sidecars;
- safe load/save with revision tokens;
- maintained/custom activation switching;
- explicit return-to-maintained flow; and
- last-known-good user revision.

Gate: sacred custom files survive update, apply, switching and failed activation.

### Slice 5: editors

- action registry;
- bindings matrix;
- JSON validation editor;
- structured bus metadata; and
- later rule-specific forms.

Gate: UI cannot create an action outside the registry and invalid drafts never reach the
active runtime.

### Slice 6: simultaneous multi-CAN

This is a separate beta milestone after single-input setup has soaked successfully.

## Unit tests

Required coverage includes:

- identifier allowlist and traversal rejection;
- maintained and custom fixed-root resolution;
- symlinked files and components;
- deterministic catalogue ordering;
- malformed catalogue entries;
- profile bus metadata and rule bus references;
- bindings action registry and argument schemas;
- event compatibility results;
- canonical descriptor parsing and revisioning;
- deterministic systemd and udev generation;
- request key allowlists and body limits;
- stale preview revision rejection;
- atomic draft writes and conflicts;
- transaction state persistence;
- apply failure at every stage; and
- verified restoration.

## Integration tests

Use temporary roots and user-manager doubles for ordinary CI. Add Linux integration tests
where systemd/udev are available.

Required workflows:

1. maintained profile plus maintained bindings;
2. maintained profile plus custom bindings;
3. custom profile plus maintained bindings;
4. switch custom back to maintained;
5. absent selected interface;
6. invalid selected custom file;
7. service restart failure;
8. runtime loads an unexpected revision;
9. configuration apply blocked during update transaction; and
10. update blocked during configuration transaction.

`vcan0` qualification exercises successful activation without vehicle hardware.

## Browser tests

Playwright coverage includes:

- catalogue grouping and labels;
- draft selection without mutation;
- maintained/custom compatibility warnings;
- multi-declared-bus single-runtime warning;
- interface present, down and absent states;
- review differences;
- explicit confirmation;
- progress polling;
- success with no frames;
- coordinator unavailable;
- restored failure;
- custom identifier conflict;
- unsaved editor navigation warning;
- focus preservation across status refresh;
- no off-screen-only feedback; and
- 800×480 containment with touch-sized controls.

## Concrete apply-operation tests

Before exposing apply, unit and integration tests must prove:

- maintained/custom catalogue reads reject symlink traversal, unsafe ownership and writable files;
- profile and bindings revisions are rechecked immediately before generation;
- canonical, systemd and udev output is deterministic for one reviewed target;
- existing generated files are snapshotted twice around stable loaded-runtime evidence;
- rollback manifests and payload checksums reject tampering;
- absent files are restored as absent and existing ownership/modes are preserved;
- destination symlinks and non-regular files are rejected;
- only fixed manager reload, udev reload/trigger and canbusd restart commands execute;
- stale status evidence from before restart is not accepted;
- an injected post-mutation failure restores both files and previous runtime evidence; and
- interrupted mutation recovery reopens the durable snapshot and reports restored versus unverified restoration.

These tests do not enable the public socket action or browser button.

## Device qualification

On the reference tablet and Seat 1P profile verify:

- fresh installation default;
- selecting and reapplying the maintained profile;
- daemon restart;
- graphical logout/login;
- reboot;
- CAN adapter unplug/replug;
- vehicle asleep/no frames;
- adapter present but interface down;
- wrong interface followed by corrected apply;
- update after custom files exist;
- custom activation followed by return to maintained;
- dashboard reload during apply; and
- journal output contains actionable but non-secret errors.

## First-release acceptance

The first setup-management release is complete when a user can select and safely apply a
maintained profile, bindings and one CAN adapter entirely from Settings; the selection
survives reboot and hotplug; failures restore the prior configuration; and custom files
are never created or activated implicitly.

The editor and simultaneous multi-CAN runtime may ship later without invalidating that
first release.
