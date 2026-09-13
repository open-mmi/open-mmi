# P15 — test: make trusted deployment recovery atomic and fail closed

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P14
- Boundary closure gates: G2
- Required review: Maintainer/security review of state ordering, durability and recovery
- Suggested signed commit subject: test: make trusted deployment recovery atomic and fail closed
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Power loss or a failed update cannot silently roll back owner authority, forge lineage, activate unaccepted code or reopen an unprotected update route.

## Minimum current-source read set

- open_mmi_trust/transition_gate.py
- open_mmi_trust/lineage.py
- open_mmi_trust/release_integrity.py
- ui/update_installer.py
- ui/update_coordinator.py
- tests/test_update_installer.py
- tests/test_trust_lineage.py
- tests/test_manage_script.py

## Proposed new paths — these do not yet exist merely because listed

- tests/test_trusted_deployment_recovery.py
- docs/design/v1-trust-completion/deployment-crash-matrix.md

## Required implementation

- Define a durable transaction state machine for artifact staging, authorization consumption, protected-anchor evolution, accepted state/lineage updates, activation, health checks and final inventory recording.
- Preserve the C6 distinction: acknowledged expansion authority is recorded before expanded code can execute; failed narrowing must not leave restored broader code outside an accidentally narrowed ceiling.
- Choose recovery code independent of the candidate and preserve enough verified old engine/artifacts to recover after process restart.
- Journal only bounded trusted data. Use fsync/atomicity where durability is part of the claim and detect inconsistent partial states.
- Make repeated recovery idempotent. Interrupted or incomplete recovery remains visibly blocked until verified; do not silently bootstrap replacement anchors.
- Document restoration effects on protected-core state, previous accepted expansion and future update eligibility.

## Required behavioral and negative tests

- Inject failures before and after every durable state write, rename, service action, token consumption and health check.
- Restart a fresh old-code recovery process from persisted fixtures rather than resuming an in-memory test only.
- Test ENOSPC, read-only filesystem, truncated state, lost artifact, wrong owner/mode, concurrent operations, stale token and repeated recovery.
- Validate restored bytes/units against the prior accepted inventory and preserve chain/authorization ordering.
- Run real disposable-VM reboot interruption cases at G2; unit mocks alone do not satisfy crash durability.

Test command groups: **T0 T_TRUST T_UPDATE T_LIFECYCLE T_FULL T_RECOVERY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P15-A01** — Every crash-matrix row has an explicit allowed post-state and tested recovery behavior.
- [ ] **P15-A02** — No failed update is labeled successful, no old authority is silently rewritten and no unverified runtime is automatically re-anchored.
- [ ] **P15-A03** — Recovery is old-code-owned and repeatable.
- [ ] **P15-A04** — Successor activation remains blocked until the required recovery evidence is present.

## Explicit exclusions

- No automatic rollback to an arbitrary caller-selected commit.
- No clearing trust state or lineage to repair a transaction.
- No promising crash safety based only on sequential happy-path tests.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
