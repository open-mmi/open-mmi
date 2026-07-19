# V1 update management design set

| Field | Value |
| --- | --- |
| Source branch | `v1-update-management` (merged) |
| Target | `main` |
| Status | Implemented on `main`; continued real-device qualification in progress |
| Predecessor | `v1-runtime-hardening` |
| Initial delivery | Read-only update visibility |

## Purpose

This design set records how the former `v1-update-management` branch turned the
administrator-run `manage.sh update` path into a deliberately staged
update-management system. The implementation is now merged into `main`. It
covers informational status, fail-closed readiness, restricted preparation,
confirmed nightly installation, health validation, and automatic restoration.
Qualification continues on real devices after the merge.

## Design documents

- [`update-source-and-channels.md`](update-source-and-channels.md)
- [`update-status-api.md`](update-status-api.md)
- [`update-ui.md`](update-ui.md)
- [`update-execution.md`](update-execution.md)
- [`health-checks-and-rollback.md`](health-checks-and-rollback.md)
- [`security-and-permissions.md`](security-and-permissions.md)
- [`qualification.md`](qualification.md)

## Decision principles

1. **Read before writing.** Update visibility ships before update execution.
2. **Use managed policy, not browser input.** The browser cannot choose a repository, remote, branch, path, tag, or command.
3. **Do not guess.** Network failure is not “up to date”; a different remote commit is not automatically assumed to be a safe forward update.
4. **Keep update state outside Chromium.** Browser refreshes and service restarts must not define whether an update succeeded.
5. **Separate preparation, execution, validation, and rollback.** A copied file is not a successful update.
6. **Preserve user configuration.** Update and rollback paths must not replace user-managed configuration with defaults.
7. **Fail closed around privilege.** No browser-controlled shell or `sudo` arguments.
8. **Build on runtime hardening.** Changed-build reload and same-build service recovery remain the frontend handoff mechanism.

## Implementation order

1. Managed installed-source descriptor and read-only status model. **Implemented in the first branch slice.**
2. Settings → System update panel and manual read-only check. **Implemented in the first branch slice.**
3. Stable/beta/nightly channel policy. **Implemented with root-owned fixed-name policy, legacy-label migration, and CLI-only selection.**
4. Pre-update readiness checks. **Implemented as a fail-closed gate.**
5. Persistent coordinator state and fixed-action privileged boundary. **Implemented with status, preparation, and a separate no-arguments installer service.**
6. User-triggered update execution. **Implemented for confirmed CLI and same-origin browser nightly candidates.**
7. Post-update health validation. **Implemented for service state, `/api/health`, and target build identity.**
8. Rollback mechanism. **Automatic restoration and bounded transaction-artifact retention are implemented; manual rollback remains unavailable.**
9. Diagnostics/log integration. **Deferred: the API exposes bounded safe state;
   raw system journals remain an administrator diagnostic rather than browser
   content.**
10. Full laptop, tablet, suspend/resume, failure, and recovery qualification.
    **Continuing on `main` and recorded in
    [`qualification.md`](qualification.md).**

## Historical first-slice boundaries

The first read-only slice, before the later coordinator and execution slices:

- records the source checkout, branch, upstream, installed commit, and version during managed install/update;
- exposes local-only `GET /api/system/update-status`;
- exposes same-origin `POST /api/system/update-check` with no caller-controlled parameters;
- uses bounded `git ls-remote` against the recorded remote/ref;
- never fetches, merges, resets, copies, installs, restarts, or elevates privilege;
- labels an unproven commit mismatch as **remote differs** rather than promising an update direction;
- added no browser install, rollback, channel-change, scheduling, or
  unattended-update action. Later slices added fixed confirmed browser nightly
  installation only; the other boundaries remain.

## Non-goals for this branch start

- unattended or scheduled updates;
- arbitrary Git repositories or refs;
- browser-supplied shell commands;
- automatic merge/reset of dirty worktrees;
- downgrades;
- an update button before readiness and rollback exist;
- treating the source checkout as the installed runtime;
- hiding thermal, power, disk, or service-health blockers.

## Initial qualification gates

Before the first slice is accepted:

- installed source metadata is written atomically by install and update;
- the status endpoint works when the source checkout is healthy, dirty, missing, detached, or on another branch;
- an offline or invalid remote is reported as unavailable, never current;
- repeated manual checks do not overlap;
- no HTTP parameter can select a path, remote, branch, ref, or command;
- opening Settings performs no network update check;
- the current Settings panel remains usable when update status is unavailable;
- Python, Node, Playwright, installer-contract, and wheel-content tests pass.

The current implementation and device evidence are tracked in
[`qualification.md`](qualification.md). That record, rather than this
historical first-slice checklist, owns the final merge decision.
