# P23 — test: exercise the full trust lifecycle with adversarial release fixtures

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: F — Final qualification
- Implementation prerequisites: P22
- Boundary closure gates: G4
- Required review: Maintainer/security review of failure coverage and remaining limitations
- Suggested signed commit subject: test: exercise the full trust lifecycle with adversarial release fixtures
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

The complete supported lifecycle preserves owner authority and evidence under hostile candidates, interruption and recovery, rather than merely passing isolated component tests.

## Minimum current-source read set

- tests/test_update_installer.py
- tests/test_update_coordinator.py
- tests/test_trust_transition_gate.py
- tests/test_trust_lineage.py
- tests/test_release_integrity.py
- tests/test_release_provenance.py
- tests/test_independent_trust_checker.py
- tests/browser/dashboard.spec.js
- docs/release-checklist.md

## Proposed new paths — these do not yet exist merely because listed

- tests/integration/test_trust_lifecycle.py
- docs/design/v1-trust-completion/adversarial-lifecycle-matrix.md

## Required implementation

- Build a disposable Linux/VM qualification harness with independently generated signing identities and exact release fixtures. Never mutate production trust stores.
- Exercise legacy new-baseline migration, valid C6 transition, protected enrollment, equal/narrower update, capability expansion, protected-core-only expansion, failed install, reboot recovery and offline external verification.
- Include signed-but-hostile candidates with unchanged manifests, malicious scripts/hooks, widened unit permissions, modified dependency bytes, forged local history and stale owner tokens.
- Correlate dashboard/API/CLI/independent-checker results using exact commit, inventory, lineage and protected anchor identities.
- Add regression tests for actual defects found, each with a focused patch revision or numbered follow-up; preserve original card IDs and explain splits in the ledger.
- Keep operational migration success, continuity success, synthetic CAN results and vehicle-qualified behavior separately recorded.

## Required behavioral and negative tests

- Every adversarial matrix row has an expected allow/block/recover state and evidence source.
- Instrument pre-gate execution and unauthorized egress/writes; absence of observed traffic alone is not enforcement proof.
- Restart clean processes/VMs at defined crash points and verify retained owner authority and restored bytes.
- Run the complete existing Python/JS/browser/package/registry/CI matrix on the subject tree, plus new integration tests.
- No skipped/environment-blocked test satisfies a required boundary; reuse existing valid evidence only with a recorded no-impact rationale.

Test command groups: **T0 T_TRUST T_UPDATE T_UI T_FULL T_BROWSER T_PACKAGE T_SYNTH T_ISOLATION T_RECOVERY T_SUPPLY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P23-A01** — All required matrix rows pass or remain explicit release blockers.
- [ ] **P23-A02** — No unresolved critical trust, CAN or identity defect remains.
- [ ] **P23-A03** — Cross-layer identities agree and evidence is independently inspectable.
- [ ] **P23-A04** — G4 can use this evidence without rerunning unchanged qualifying tests.

## Explicit exclusions

- No integration-test helper that grants production bypass flags.
- No flattening expected UNVERIFIED scenarios into PASS.
- No forcing exactly 25 commits when a discovered defect needs a focused follow-up.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
