# P25 — docs: close release trust boundaries with a portable qualification dossier

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: F — Final qualification
- Implementation prerequisites: P24
- Boundary closure gates: G5
- Required review: Maintainer final acceptance and release decision
- Suggested signed commit subject: docs: close release trust boundaries with a portable qualification dossier
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Completion means every supported trust claim has current, scoped evidence and a reproducible recovery/verification path, with no pending required boundary hidden by a release badge.

## Minimum current-source read set

- docs/release-checklist.md
- docs/branch-workflow.md
- docs/trust-architecture.md
- SECURITY.md
- CHANGELOG.md
- independent_checker/README.md

## Proposed new paths — these do not yet exist merely because listed

- docs/design/v1-trust-completion/evidence/final-boundary-closure.json
- docs/design/v1-trust-completion/evidence/release-qualification.md

## Required implementation

- Reconcile every original goal with its implementation, acceptance criteria, test evidence and required external/hardware gate. Include independent owner authorization, SI compliance scope, challenge transport support and dependency/host assumptions.
- Complete G5 using authorized nightly-to-beta promotion, the maintainer-selected beta soak and exact beta-to-main release checks from the repository policy. Do not invent a soak duration.
- Record the actual code/artifact subject separately from this evidence-only recording commit; avoid circular requirements to test a commit containing its own SHA.
- Verify legacy migration is labeled new baseline, successor continuity begins at explicit enrollment, and unsupported hardware attestation/OS compromises are not claimed covered.
- Prepare the final signed release/checker/metadata instructions and evidence bundle for maintainer review. Publication remains a separate explicit action.
- Leave the next-chat handoff with no ambiguous in-progress task, exact release candidate identity, any deferred optional work and the location of independently retained owner/checker anchors.

## Required behavioral and negative tests

- Validate all manifest IDs, dependency/gate closures, evidence hashes and original-goal coverage; no required item may be not-run, blocked or supported only by stale evidence.
- Run independent verification against the exact release candidate from a separate trusted environment and demonstrate recovery from retained checkpoints.
- Complete cold reboot, suspend/resume, adapter reconnect, live decoding, UI freshness, update expansion/narrowing and recovery qualification on the actual target(s).
- Refresh only invalidated automated evidence; record why documentation-only changes do not alter the tested runtime.

Test command groups: **T0 T_DOC T_INDEPENDENT T_FULL T_BROWSER T_PACKAGE**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P25-A01** — Every required commit criterion and G0–G5 gate has explicit accepted evidence or the overall goal remains incomplete.
- [ ] **P25-A02** — The qualified candidate completed the agreed beta soak and final promotion checks.
- [ ] **P25-A03** — A new agent/owner can independently reconstruct what was trusted, authorized, installed and tested from the dossier.
- [ ] **P25-A04** — Optional TPM/measured boot, fully reproducible OS images and unsupported field transports are clearly separated from completed baseline claims.

## Explicit exclusions

- No retroactive baseline or fabricated owner/hardware evidence.
- No automatic publication, signing, channel switch or uninstall.
- No declaring a universally tamper-proof system beyond the documented trust assumptions.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
