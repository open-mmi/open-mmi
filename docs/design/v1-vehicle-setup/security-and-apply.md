# Security, privilege and apply transaction

## Boundaries

The dashboard process may:

- enumerate installed maintained files read-only;
- enumerate and edit files beneath its own Open MMI user config root;
- validate drafts;
- inspect interfaces and active runtime status read-only; and
- call a restricted local coordinator socket.

The dashboard process must not:

- run `sudo`, `pkexec`, a shell or `scripts/manage.sh`;
- write `/etc`, `/opt` or another user's home;
- submit a filesystem path to the privileged coordinator;
- submit systemd, udev or command text; or
- choose a service name or executable.

## Coordinator separation

Vehicle configuration should use a dedicated coordinator or one-shot service rather
than widening the update coordinator sandbox. The two systems have different writable
paths, actions and failure modes.

The coordinator socket is local, group-authorized and unavailable to remote clients.
Its public protocol contains fixed actions and bounded JSON objects only.

The coordinator exposes `status`, non-mutating `preview`, and one fixed confirmed
`apply` action. It persists strict public transaction state and reports
configuration/update/lifecycle lock ownership. Preview rereads the fixed installed
catalogue, the configured service user's custom catalogue and runtime drop-in inside
the privileged boundary; it never accepts a path from the dashboard. Apply has write
access only to the fixed canonical descriptor, generated udev rule, rollback/state
roots and configured canbusd runtime-drop-in directory.

Fixed protocol actions are staged as follows:

```text
status   implemented
preview  implemented, read-only
apply    implemented, exact reviewed target plus confirmation
restore  internal recovery only; no caller-selected target
```

`restore` is an internal recovery action tied to coordinator-owned transaction state;
it is not a browser-selected arbitrary rollback target.

## Request defence

Both the dashboard and coordinator validate:

- exact allowed object keys;
- duplicate JSON keys and non-finite JSON values;
- source class (`maintained` or `custom`);
- identifier syntax;
- fixed runtime mode (`single` in V1);
- bus names declared by the selected profile;
- valid Linux interface names;
- one interface assignment for the active bus;
- expected canonical configuration revision;
- reviewed target configuration revision; and
- explicit `confirm: true` for apply.

The privileged side must not trust validation performed by the dashboard.

All subprocess operations use fixed argument arrays. No operation uses `shell=True` or
interpolated shell text.

## Filesystem defence

Custom-file resolution must:

- begin at a trusted user config directory;
- use an identifier rather than a path;
- reject symlinked target files and symlinked path components;
- reject non-regular files;
- avoid following links during replacement;
- create directories with user-only write permission;
- write a temporary file in the target directory;
- flush and `fsync` before atomic replacement; and
- retain user ownership.

Maintained files are read-only and resolved from `/opt/open-mmi` in production.

## Apply transaction state

Persistent coordinator state should include:

```text
idle
validating
applying
reloading
verifying
complete
restoring
failed
```

It records only safe public detail:

- transaction identifier;
- state and stage;
- start/update/completion timestamps;
- target profile and bindings identities;
- target active bus and interface;
- whether restoration was attempted and verified; and
- a bounded user-facing error.

It does not expose temporary paths, commands or subprocess output to the browser.

## Concrete operation layer

The coordinator uses a concrete operation implementation behind the fixed public apply
protocol. It:

- securely reopens maintained and custom catalogue files without following symlinks;
- verifies expected ownership, permissions, semantic validity and reviewed revisions;
- renders canonical JSON, the canbusd systemd runtime drop-in and active-bus udev rules;
- stores a durable root-owned rollback manifest plus checksummed file payloads;
- atomically replaces each fixed destination through sibling files and directory fsync;
- invokes only fixed `systemctl --user`, `udevadm control --reload-rules`, and a fixed system-service start;
- hands host-network CAN link setup to a separate oneshot helper that consumes one root-owned normalized target and executes only fixed `ip link` argument lists;
- requires loaded-runtime evidence newer than the service restart; and
- verifies both restored files and the exact previous loaded identities, revisions, bus and interface.

The internal state machine can reopen a durable snapshot after an interrupted mutation.
The socket and fixed HTTP route may trigger apply; the Settings button still cannot.

## Vcan qualification boundary

Before the fixed public apply protocol was enabled, the reference tablet qualified the
same concrete transaction through a root-only local round-trip command. It remains
deliberately separate from `open-mmi-config`, the dashboard server and the
group-readable coordinator socket.

The command consumes an exact root-owned `0600` one-shot marker, reads one bounded JSON
preview from standard input, and accepts no caller-provided path, command, service name
or generated content. The target must resolve to an up kernel `vcanN` interface under
the virtual network-device tree. Additional user-service drop-ins that could override a
coordinator-owned runtime environment key are rejected through directory-relative,
no-follow reads before consent is consumed. The coordinator then regenerates the preview under all
three transaction locks, including the reviewed profile and bindings content revisions.

Qualification suppresses hardware CAN provisioning and does not reload or trigger the
temporary udev rules. After the vcan target is loaded and verified, the previous files
and runtime are restored and verified before the transaction locks are released. A
successful round trip removes its snapshot and records
`stage=qualification-restored`; a failed or interrupted transaction remains available
to the root-owned recovery path.

The long-running coordinator service sandbox is widened only to `/etc/open-mmi`,
`/etc/udev/rules.d`, the coordinator state/runtime directories, and the generated
per-user canbusd drop-in directory. It remains network-isolated. A separate static
oneshot helper enters the host network namespace with only `CAP_NET_ADMIN` and
`CAP_DAC_READ_SEARCH`, consumes a root-owned request from `/run/open-mmi`, independently
revalidates catalogue revisions and interface identity, and configures only the reviewed
physical `canN` interface. It never accepts paths, commands, service names, or bitrates
from the socket caller. The public protocol exposes fixed apply but continues to reject
caller-selected restore.

## Fixed public apply protocol

The apply body contains exactly `target`, `expected_configuration_revision`,
`target_configuration_revision` and `confirm`. `target` is the canonical normalized
selection returned by preview, including profile and bindings content revisions. The
coordinator converts it back to an identity-only request and rebuilds the plan under all
three locks. It rejects:

- stale active configuration revisions;
- changed profile or bindings content revisions;
- inconsistent target revision hashes;
- additional canbusd drop-ins that override coordinator-owned environment keys;
- existing selected interfaces that are not SocketCAN;
- absent selected interfaces whose names do not match `canN`;
- all `vcanN` targets outside the root-only qualification command; and
- concurrent update, lifecycle or configuration transactions.

The dashboard route remains literal-loopback and same-origin. Conflict results use the
bounded `busy` or `stale-preview` code. A failed mutation returns safe persisted state
with `apply-failed-restored` or `apply-failed-restore-unverified`; raw command output,
paths and subprocess errors do not cross the boundary. Public apply rejects `vcanN`
targets and absent interface names outside the conservative `canN` contract. Virtual
CAN remains confined to the root-only qualification command.

## Apply sequence

1. Acquire the configuration transaction lock.
2. Read the current canonical descriptor and calculate its revision.
3. Reject a stale `expected_configuration_revision`.
4. Resolve target identities beneath fixed roots.
5. Reparse and validate profile and bindings.
6. Validate profile/bindings event compatibility.
7. Validate the active bus and interface assignment.
8. Build deterministic systemd, udev and canonical descriptor content.
9. Snapshot the previous canonical descriptor and generated files.
10. Stage replacement files beside their targets.
11. Atomically install the canonical and generated files.
12. Reload the user's systemd manager.
13. Reload and trigger udev when the plan changes udev provisioning.
14. Restart `canbusd.service`.
15. Wait for machine-readable runtime configuration status.
16. Verify expected source identities, revisions, bus and interface.
17. Mark the transaction complete and retain a bounded last-known-good snapshot.

## Verification contract

Activation verification passes when:

- `canbusd.service` is active;
- the selected profile parsed successfully;
- the selected bindings parsed successfully;
- loaded identities and content revisions match the target;
- the selected active bus matches; and
- the resolved interface matches.

Verification does not require:

- a connected vehicle;
- a present interface;
- recent CAN frames; or
- particular decoded vehicle values.

Those are runtime health states and may legitimately be absent during setup.

## Restoration

If mutation, reload, restart or verification fails:

1. retain the original failure stage;
2. atomically restore the prior canonical descriptor and generated files;
3. reload systemd and udev as required;
4. restart `canbusd`;
5. verify the previous loaded configuration; and
6. report either `failed; previous setup restored` or
   `failed; restoration could not be verified`.

The previous configuration remains the only selectable automatic restoration target.

## Concurrency

- Only one configuration transaction may run at a time.
- Draft saves use per-file revision checks and do not acquire the privileged apply lock.
- Update installation and configuration apply must not run concurrently because both
  can replace installed code or restart services.
- The readiness/status API should report a clear blocker when either transaction owns
  the shared lifecycle boundary.

## CAN safety

The configuration coordinator may provision receive interfaces, but neither the UI nor
the coordinator transmits CAN frames. The operational dashboard remains read-only with
respect to the vehicle.

Every apply confirmation should state that Open MMI services will restart and that no
CAN transmission is performed.
