# Update execution

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Restricted candidate preparation implemented; installation remains disabled |
| Owners | Future update coordinator, installer, systemd integration |

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

The only enabled protocol request is exactly
`{"api_version": 1, "action": "status"}`. Extra fields and all prepare,
install, rollback, path, command, repository, ref, and service inputs are
rejected. The response explicitly reports `execution_enabled: false`.

An active state found at daemon startup is conservatively recovered to
`failed` rather than resumed or called successful. The transaction lock uses a
non-blocking exclusive filesystem lock and rejects overlap. Execution code does
not yet acquire it because execution remains outside this slice.

Readiness reports the boundary itself as available, but retains the separate
`execution-authorization` blocker while `execution_enabled` is false. Installing
this service therefore cannot accidentally expose an update action.

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
into `/opt/open-mmi`. `execution_enabled` and `installation_enabled` remain
false; install and rollback requests are still rejected.

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
15. Mark success and retain bounded rollback information.

## Persistence

Coordinator state must survive:

- Chromium refresh or closure;
- dashboard-server restart;
- suspend/resume;
- the frontend changed-build reload.

States should include idle, preparing, downloading, validating, installing, restarting, checking health, complete, failed, and rolling back.

## Locking

A second update request must fail safely while any transaction is active. Locks must be recoverable after a crashed process without allowing two coordinators to modify the installation concurrently.

## Existing `manage.sh update`

The current command remains an administrator path while the coordinator is designed. It is not exposed directly to the browser. Refactoring should preserve install/update/reinstall/uninstall coverage and should avoid maintaining two unrelated deployment implementations.
