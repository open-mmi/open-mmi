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

The coordinator currently exposes `status` and non-mutating `preview`. It persists strict public transaction state, reports configuration/update/lifecycle lock ownership, and explicitly reports apply/restore as disabled. Preview rereads the fixed installed catalogue, the configured service user's custom catalogue and runtime drop-in inside the privileged boundary; it never accepts a path from the dashboard. The service still has no writable access to `/etc/open-mmi`.

Fixed protocol actions are staged as follows:

```text
status   implemented
preview  implemented, read-only
apply    gated
restore  internal recovery, gated
```

`restore` is an internal recovery action tied to coordinator-owned transaction state;
it is not a browser-selected arbitrary rollback target.

## Request defence

Both the dashboard and coordinator validate:

- exact allowed object keys;
- source class (`maintained` or `custom`);
- identifier syntax;
- fixed runtime mode (`single` in V1);
- bus names declared by the selected profile;
- valid Linux interface names;
- one interface assignment for the active bus;
- expected canonical configuration revision; and
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
