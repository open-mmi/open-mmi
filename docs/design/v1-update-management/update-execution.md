# Update execution

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Confirmed CLI and same-origin browser nightly installation implemented |
| Owners | Update coordinator, installer, systemd integration |

## Required architecture

```text
Web UI
  -> local dashboard API
  -> restricted update coordinator
  -> fixed installer/update operations
```

The dashboard process must not execute browser-supplied shell commands and must not run `sudo` with browser-controlled arguments.

## Implemented coordinator boundary

`open-mmi-update-coordinator.service` runs as root and owns a Unix socket at
`/run/open-mmi/update-coordinator.sock`. Access is limited to root and the
dedicated `open-mmi-update` group. State is atomically persisted at
`/var/lib/open-mmi/update-state.json` with a fixed schema.

The protocol accepts only exact fixed-shape `status`, confirmed `prepare`, and
confirmed `install` requests. Extra fields and all rollback, path, command,
repository, ref, and service inputs are rejected. Installation is enabled only
while root-owned policy selects `nightly`.

An active state found at daemon startup is conservatively recovered to
`failed` rather than resumed or called successful. The transaction lock uses a
non-blocking exclusive filesystem lock and rejects overlap. The installer
acquires the same lock before changing the live installation.

Readiness reports execution authorization only when the coordinator is trusted,
responsive, and nightly installation is enabled. Stable and beta retain the
authorization blocker.

## Candidate preparation

The coordinator accepts exactly
`{"api_version": 1, "action": "prepare", "confirm": true}`. The local
dashboard bridge accepts only `{"confirm": true}` and supplies no repository,
channel, ref, tag, commit, path, command, service, or environment value.

Preparation re-reads the managed source and root-owned channel policy, checks
installation, disk, command, power, and thermal readiness, and takes the
exclusive transaction lock. It resolves the candidate from trusted policy,
clones the recorded remote into a randomly named directory beneath
`/var/lib/open-mmi/staging`, and proves that the installed commit is an
ancestor of the candidate. Release channels also re-check that the selected tag
still identifies the same commit after download.

State advances through `preparing`, `downloading`, and `validating`, ending in
`prepared` or `failed`. The prepared tree becomes root-owned and is not copied
into `/opt/open-mmi` until a separate confirmed install request is made.

## Confirmed installation

`open-mmi-config updates install` and the loopback same-origin dashboard route both send exactly
`{"api_version": 1, "action": "install", "confirm": true}`. The coordinator
starts the fixed `open-mmi-update-installer.service`; no unit name or argument
comes from the caller. The one-shot service accepts no arguments, re-reads
root-owned state and policy, requires nightly, validates staging containment and
ownership, and re-proves candidate identity and forward ancestry.

The deployment helper backs up the installed tree and affected service units,
deploys the staged application, reinstalls package wrappers and managed assets,
restarts only Open MMI user services, and requires active services plus matching
`/api/health` and `/api/version`. An error trap restores the previous tree and
units and restarts the restored services. Raw command output is not persisted or
returned through the coordinator protocol.

The browser route accepts only `{"confirm": true}` and cannot select a source,
candidate, path, unit, command, or rollback archive. It polls the coordinator's
persistent public state while the dashboard restarts. The coordinator completes
its post-install handoff even if that dashboard HTTP connection has already
closed.

## Transaction stages

1. Acquire a system-wide update lock.
2. Re-read trusted source and channel policy.
3. Run readiness checks.
4. Record the installed version and rollback metadata.
5. Back up user-managed configuration metadata without copying secrets into logs.
6. Download/fetch the approved candidate.
7. Validate source, ref, manifest/signature policy, and direction.
8. Stage deployment separately from the live installation where practical.
9. Stop only affected services.
10. Deploy package, assets, units, commands, and metadata.
11. Restart services.
12. Run post-update health checks.
13. Confirm `/api/version` matches the intended build.
14. Let runtime-hardening perform the one-shot frontend reload.
15. Mark success, remove terminal staging, and retain the two newest rollback archives.

## Persistence

Coordinator state must survive:

- Chromium refresh or closure;
- dashboard-server restart;
- suspend/resume;
- the frontend changed-build reload.

Coordinator startup reconciles this state with retained artifacts: only the
active/prepared staging tree is preserved, terminal staging is deleted, and
rollback archives are pruned to the fixed retention bound while protecting the
recorded transaction.

The public state uses `idle`, `preparing`, `downloading`, `validating`,
`prepared`, `installing`, `complete`, and `failed`. The installer records the
failing deployment stage and whether automatic rollback was verified rather
than exposing caller-selectable restart, health, or rollback states.

## Locking

A second update request must fail safely while any transaction is active. Locks must be recoverable after a crashed process without allowing two coordinators to modify the installation concurrently.

## Existing `manage.sh update`

The administrator command remains available for recovery and development, but
it is never exposed directly to the browser. Prepared installation invokes the
fixed internal `_deploy-prepared` operation from the staged candidate, keeping
package deployment, managed assets, service restart, health validation, and
rollback in one implementation instead of a second browser-owned updater.
