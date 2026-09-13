# P12 — feat: gate protected-core deltas before candidate execution

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P11
- Boundary closure gates: G2
- Required review: Maintainer/security review of classification completeness and authorization binding
- Suggested signed commit subject: feat: gate protected-core deltas before candidate execution
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

An unchanged capability manifest does not bypass explicit owner review of protected-core or enforcement changes.

## Minimum current-source read set

- open_mmi_trust/transition_gate.py
- open_mmi_trust/transition_gate_cli.py
- ui/update_coordinator.py
- ui/update_installer.py
- open_mmi_trust/release_integrity.py
- tests/test_trust_transition_gate.py
- tests/test_update_coordinator.py
- tests/test_update_installer.py

## Proposed new paths — these do not yet exist merely because listed

- tests/test_protected_core_transition.py

## Required implementation

- Read candidate artifacts only as exact Git objects/verified release data using old trusted code. Compare protected inventory and control definitions against the accepted protected anchor.
- Classify any protected addition/removal/byte change conservatively under P10. Candidate code, comments, self-reported compatibility and signature status cannot suppress the delta.
- Extend the fixed prepared-transition review with protected change details and a root+TTY acknowledgement bound to transaction, candidate commit, old protected anchor, policy/inventory/lineage and candidate protected digest.
- Combine capability and protected-code deltas into one coherent decision while preserving each authority dimension. Do not reuse a token across candidates or after state changes.
- Recheck at coordinator preflight and immediately before installer execution. Ensure the checker/classifier itself is included in the protected set.
- Keep operational activation staged until P16; unsupported/uninitialized active states block rather than silently returning to the old gate.

## Required behavioral and negative tests

- A candidate that preserves manifest JSON but alters the trust comparator, deployment script, unit sandbox or protected broker requires acknowledgement.
- Unprotected feature-only bytes with unchanged policy can proceed under the reviewed contract.
- Test stale/replayed authorization, replaced candidate object, changed accepted anchor, mixed narrowing plus protected expansion, removed protected definition and generation regression.
- Instrument candidate hooks/imports/commands and prove zero executions before all authorization decisions.

Test command groups: **T0 T_TRUST T_UPDATE T_FULL**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P12-A01** — Protected deltas are visible and cannot self-authorize.
- [ ] **P12-A02** — Exact-bound authorization and rechecks reject race/replay cases.
- [ ] **P12-A03** — C6 transition semantics remain intact and separately testable.
- [ ] **P12-A04** — No privileged candidate execution is reachable through an unreviewed protected change in the successor path.

## Explicit exclusions

- No automatic semantic-equivalence judgment by an LLM.
- No broad browser approval or reusable authorization token.
- No allowing an unknown protected file type merely because signed.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
