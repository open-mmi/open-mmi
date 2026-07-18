# Health checks and rollback

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Pre-update inspection implemented; post-update health and rollback remain proposed |
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
silently treated as ready. Until the separately privileged coordinator exists,
`privileged-coordinator` intentionally remains a blocker and
`install_allowed` remains false.

## Post-update health

Success requires more than file copying. Checks include:

- dashboard service active;
- `/api/health` responds;
- `/api/version` equals the target build;
- required static assets exist;
- installed console commands resolve;
- desktop/menu assets exist;
- configuration is readable;
- CAN service state matches policy;
- no affected service is restarting repeatedly;
- frontend version reconciliation completes or is explicitly pending active editing.

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

Rollback may initially be CLI-only while its mechanism is qualified. A browser rollback action must not ship merely because backup files exist.

Rollback must preserve user configuration and must not silently downgrade across incompatible data/configuration formats.
