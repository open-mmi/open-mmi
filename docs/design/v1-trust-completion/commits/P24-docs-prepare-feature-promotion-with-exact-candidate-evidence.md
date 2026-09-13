# P24 — docs: prepare feature promotion with exact candidate evidence

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: F — Final qualification
- Implementation prerequisites: P23
- Boundary closure gates: G4
- Required review: Maintainer decides promotion, commit, push and merge actions
- Suggested signed commit subject: docs: prepare feature promotion with exact candidate evidence
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Only the exact qualified feature/runtime candidate is proposed for nightly integration; merge or branch movement does not inherit evidence for changed runtime bytes automatically.

## Minimum current-source read set

- docs/branch-workflow.md
- docs/release-checklist.md
- docs/design/v1-update-management/qualification.md
- docs/runtime-hardening-qualification.md
- CHANGELOG.md
- docs/trust-architecture.md

## Proposed new paths — these do not yet exist merely because listed

- docs/design/v1-trust-completion/evidence/promotion-candidate.json

## Required implementation

- Prepare the reviewed patch/diff summary, migration/recovery notes, test evidence and unresolved-risk list for a feature-to-nightly PR. Do not commit, push, open or merge it without explicit maintainer authorization at that point.
- Record feature subject SHA, required G0–G4 evidence, pending promotion actions and how merge changes affect runtime inventory.
- After authorized integration, record the resulting nightly SHA and rerun CI plus impacted tablet/vehicle qualification there. Do not assume a successful feature test proves a materially changed merge.
- Follow feature -> nightly -> beta -> main. Do not merge beta backwards just to remove an ahead count; preserve production hotfix policy.
- Prepare explicit commands only after inspecting the actual repository/PR state; no hard-coded future commit hashes or blanket git add -A.
- Ensure updater channel metadata still identifies the intended source and that beta/stable tag discovery is not confused with Git branch promotion.

## Required behavioral and negative tests

- Check exact promoted code identity, clean tree, signed commits where required and CI run subject.
- Compare runtime inventories between qualified feature and integrated nightly; classify which evidence remains valid and which must be refreshed.
- Repeat required nightly hardware/update/migration checks on the integrated subject.
- Verify documentation and release checklist agree on direction, tag/channel semantics and pending beta soak.

Test command groups: **T0 T_DOC T_FULL T_BROWSER T_PACKAGE**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P24-A01** — A concrete reviewable promotion package exists with exact source identities.
- [ ] **P24-A02** — Authorized nightly integration and its CI/hardware evidence are recorded, or explicitly pending.
- [ ] **P24-A03** — No release or beta promotion is claimed merely because the feature PR is ready.
- [ ] **P24-A04** — P25 receives an unambiguous tested nightly/beta candidate and remaining gate list.

## Explicit exclusions

- No autonomous remote Git operations.
- No feature-to-main shortcut.
- No signing or publishing under the agent's invented identity.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
