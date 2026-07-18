# Update execution

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Proposed; deliberately not implemented in first slice |
| Owners | Future update coordinator, installer, systemd integration |

## Required architecture

```text
Web UI
  -> local dashboard API
  -> restricted update coordinator
  -> fixed installer/update operations
```

The dashboard process must not execute browser-supplied shell commands and must not run `sudo` with browser-controlled arguments.

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
