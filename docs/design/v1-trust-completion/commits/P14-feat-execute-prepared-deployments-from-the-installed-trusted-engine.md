# P14 — feat: execute prepared deployments from the installed trusted engine

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P13
- Boundary closure gates: G2
- Required review: Maintainer/security review required; high-consequence deployment code
- Suggested signed commit subject: feat: execute prepared deployments from the installed trusted engine
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Prepared deployment is performed by already-trusted implementation under a fixed authority set. Accepted candidate runtime starts only after its required policy/protected-core authorization.

## Minimum current-source read set

- ui/update_installer.py
- open_mmi_trust/release_integrity.py
- scripts/manage.sh
- systemd/system/open-mmi-update-installer.service
- tests/test_update_installer.py
- tests/test_manage_script.py

## Proposed new paths — these do not yet exist merely because listed

- open_mmi_trust/deployment_engine.py
- tests/test_trusted_deployment_engine.py

## Required implementation

- Implement P13 plan operations using descriptor-relative safe file handling, same-filesystem staging and atomic replacement where appropriate.
- Keep the executing old engine and its dependencies stable through the transaction; do not reload modules or invoke newly written candidate helpers during deployment/recovery.
- Replace the successor-path call to staged scripts/manage.sh _deploy-prepared with the installed engine. Review service/daemon reload actions as execution boundaries.
- Install only the verified prepared artifact offline. Validate mode/owner/path/byte identities both before exposure and after deployment.
- Retain shared lifecycle locks and existing configuration preservation. Coordinate service handoffs without creating windows where physical CAN is up without barriers.
- Keep legacy/manual deployment explicitly separate with continuity implications; do not leave it as an automatic fallback for successor failure.

## Required behavioral and negative tests

- Candidate manage.sh/build hooks contain observable tripwires and are never executed by prepared deployment.
- Faults at each file/service/package boundary leave recoverable state, never silently marked success.
- Tests cover protected core replacement while old execution continues, changed plans/artifacts, concurrent lifecycle operations and configuration preservation.
- Installed source, site-packages, privileged units and protected inventory all match accepted artifacts before success.

Test command groups: **T0 T_TRUST T_UPDATE T_LIFECYCLE T_FULL T_PACKAGE T_SYSTEMD**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P14-A01** — Successor prepared updates have no candidate-controlled privileged deployment callback.
- [ ] **P14-A02** — Runtime activation occurs only after both policy and protected-core authorization.
- [ ] **P14-A03** — Fixed operations preserve normal install behavior and offline constraints.
- [ ] **P14-A04** — P15 recovery qualification is a required dependency of activation, not an optional later cleanup.

## Explicit exclusions

- No arbitrary root command dispatcher.
- No network package installation during prepared deployment.
- No weakening CAN barriers during service handoff.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
