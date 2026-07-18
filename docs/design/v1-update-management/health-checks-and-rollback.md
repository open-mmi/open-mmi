# Health checks and rollback

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Pre-update inspection plus initial nightly health validation and automatic restoration implemented |
| Owners | Update coordinator, runtime services, release engineering |

## Pre-update readiness

An install action remains unavailable unless policy confirms:

- managed installation and installed version are known;
- trusted source/channel is valid;
- source checkout is in an allowed state;
- no update is already running;
- sufficient disk space exists;
- required commands and privilege boundary are available;
- configuration and rollback metadata can be preserved;
- AC/battery policy is satisfied where hardware exposes it;
- thermal state is not constrained;
- required services are not in a restart loop.

Thermal, battery, and charging values should reuse the runtime-diagnostics backend rather than implementing a second `/sys` reader.

The read-only readiness slice exposes `GET /api/system/update-readiness` and
`open-mmi-config updates readiness`. Both inspect a fixed set of local checks;
neither accepts paths, commands, service names, thresholds, or policy overrides.
Unknown power, thermal, or service state is reported as `indeterminate`, never
silently treated as ready. `install_allowed` becomes true only when the trusted
coordinator reports nightly execution authorization and every blocker clears.

## Post-update health

The initial CLI installer requires:

- dashboard service active;
- `/api/health` responds;
- `/api/version` equals the target build;
- package and console wrapper installation succeeds;
- managed service units and desktop assets install successfully.

Broader runtime diagnostics and frontend reconciliation remain later
qualification work; they do not weaken the fixed health gate above.

## Rollback metadata

Record at least:

- previous installed version and commit;
- previous deployable artifact or staging path;
- configuration backup metadata;
- update start/end timestamps;
- failed stage and safe error summary;
- service state before update;
- post-update health results.

## Initial rollback boundary

Failed deployment or health validation automatically restores the previous
installed tree and affected system/user units, reinstalls its package wrappers,
reloads service managers, and restarts the restored services. The rollback
target is derived from the active transaction and cannot be selected by a
caller. Manual and browser rollback actions remain unavailable.

Rollback must preserve user configuration and must not silently downgrade across incompatible data/configuration formats.
