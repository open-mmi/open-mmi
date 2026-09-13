# P17 — feat: export and verify externally retained owner continuity checkpoints

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: D — Independent evidence
- Implementation prerequisites: P16
- Boundary closure gates: G3
- Required review: Maintainer/security design review required for external owner authorization evidence
- Suggested signed commit subject: feat: export and verify externally retained owner continuity checkpoints
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

External continuity claims are anchored in evidence the target cannot rewrite. A self-consistent local hash chain or a maintainer signature alone cannot prove historical owner acknowledgement.

## Minimum current-source read set

- open_mmi_trust/lineage.py
- open_mmi_trust/release_integrity.py
- open_mmi_trust/release_provenance.py
- independent_checker/open_mmi_trust_check.py
- independent_checker/README.md
- tests/test_independent_trust_checker.py
- tests/test_trust_lineage.py

## Proposed new paths — these do not yet exist merely because listed

- open_mmi_trust/checkpoint_cli.py
- open_mmi_trust/data/owner-checkpoint.v1.schema.json
- tests/test_owner_checkpoint.py

## Required implementation

- Define a bounded export containing accepted policy, protected-core anchor, lineage checkpoint and release identity/digests, without telemetry authorization material, raw VIN or secrets.
- Choose and document how the owner retains checkpoints outside the target before relying on them for future verification. Do not silently upload them or store the only copy on the tablet.
- Independently verify an expected external checkpoint against later lineage and signed artifacts, distinguishing local consistency from externally anchored continuity.
- Resolve authorization evidence for expansions after the retained checkpoint: a root attacker can append a hash-valid invented acknowledgement. Require independently retained owner-witnessed transition receipts or an explicitly reviewed external owner-signing scheme before claiming those approvals independently proven.
- Do not introduce an automatic private key on the target and call it independent. If no external owner evidence exists for an interval, label that interval UNVERIFIED.
- Handle checkpoint export interruption, duplicate records, lineage forks, truncation, missing intermediates and successor protected-core changes deterministically.

## Required behavioral and negative tests

- A coherently rewritten target-local history fails against an externally retained mismatching checkpoint.
- A forged later expansion acknowledgement without independent owner evidence cannot pass the historical-authorization dimension.
- Equivalent/narrower descendants, legitimate witnessed expansions, forks, truncated chains and unavailable checkpoints have distinct expected outcomes.
- Raw VIN, credentials and telemetry fingerprints are absent from exported public evidence and errors.
- A wiped-target recovery fixture verifies using only independently retained artifacts and a separately obtained checker.

Test command groups: **T0 T_TRUST T_INDEPENDENT T_FULL T_RECOVERY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P17-A01** — The checkpoint and owner-witness contract is reviewed and implemented with explicit trust assumptions.
- [ ] **P17-A02** — No historical interval is called independently authorized merely because local hashes recompute.
- [ ] **P17-A03** — Externally retained checkpoint verification works independently of target runtime imports.
- [ ] **P17-A04** — G3 demonstrates recovery from the retained evidence on a separate trusted environment.

## Explicit exclusions

- No automatic cloud/account integration or external transmission.
- No mandatory TPM.
- No pretending an optional unchecked expected-lineage argument proves continuity.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
