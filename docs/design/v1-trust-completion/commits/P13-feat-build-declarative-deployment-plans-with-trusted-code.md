# P13 — feat: build declarative deployment plans with trusted code

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P12
- Boundary closure gates: G2
- Required review: Maintainer/security review of the operation and destination allowlists
- Suggested signed commit subject: feat: build declarative deployment plans with trusted code
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Candidate content may describe installable data within a fixed contract; it may not choose privileged commands, hooks, arbitrary paths or package build logic.

## Minimum current-source read set

- open_mmi_trust/release_integrity.py
- ui/update_installer.py
- scripts/manage.sh
- tests/test_release_integrity.py
- tests/test_update_installer.py
- tests/test_manage_script.py

## Proposed new paths — these do not yet exist merely because listed

- open_mmi_trust/deployment_plan.py
- open_mmi_trust/data/deployment-plan.v1.schema.json
- tests/test_trusted_deployment_plan.py

## Required implementation

- Translate the existing successful deployment behavior into an old-code-generated plan from authenticated inventory and trusted installation policy.
- Allowlist operation types, destination roots, ownership/mode rules, service actions, preserved configuration and rollback artifacts. Reject unexpected objects, absolute/traversing paths, symlinks and undeclared root destinations.
- Reuse trusted wheel construction from exact Git inventory. Do not reintroduce candidate PEP 517 hooks, setup.py, shell evaluation or arbitrary environment expansion.
- Bind plans to candidate, accepted policy/protected anchor, transaction and inventory digests. Recalculate rather than trusting a candidate-supplied plan.
- Preserve desktop launchers, coordinator environment, udev, namespace modules, service units, source/site-packages parity and update metadata.
- Provide a non-mutating explain/validate path so the maintainer can review the exact plan before any deployment.

## Required behavioral and negative tests

- Malicious candidate fixtures attempt hooks, arbitrary URL/command/path, new privileged destinations, path traversal, symlink/hardlink entries and unknown file types.
- Dry-run planning does not execute candidate code or alter target paths.
- Plans for representative current installations preserve required runtime artifacts and existing local configuration.
- Serialization is deterministic; changed transaction, candidate or anchor invalidates the plan.

Test command groups: **T0 T_TRUST T_UPDATE T_LIFECYCLE T_FULL T_PACKAGE**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P13-A01** — The plan is a bounded versioned data object derived by old trusted code.
- [ ] **P13-A02** — All legacy deployment effects are either represented safely or explicitly unsupported and blocked.
- [ ] **P13-A03** — Hostile fixtures cannot introduce privileged execution through data fields.
- [ ] **P13-A04** — No active installer switches to this engine until P14–P16 and recovery tests are ready.

## Explicit exclusions

- No candidate-selected shell snippets or general package-manager invocation.
- No direct mutation of the user's tablet from tests.
- No redesign of unrelated install features.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
