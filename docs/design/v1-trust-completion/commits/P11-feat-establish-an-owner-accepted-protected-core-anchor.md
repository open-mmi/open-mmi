# P11 — feat: establish an owner-accepted protected-core anchor

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P10
- Boundary closure gates: G2
- Required review: Maintainer/security review of enrollment and state ownership
- Suggested signed commit subject: feat: establish an owner-accepted protected-core anchor
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

The successor protected-core anchor is created only by explicit local owner enrollment of the currently verified installed implementation. Candidate data cannot supply or overwrite the accepted protected set.

## Minimum current-source read set

- open_mmi_trust/accepted_state.py
- open_mmi_trust/lineage.py
- open_mmi_trust/release_integrity.py
- open_mmi_trust/release_provenance.py
- open_mmi_trust/release_integrity_cli.py
- open_mmi_trust/release_provenance_cli.py
- tests/test_release_integrity.py
- tests/test_release_provenance.py

## Proposed new paths — these do not yet exist merely because listed

- open_mmi_trust/protected_core.py
- open_mmi_trust/protected_core_cli.py
- tests/test_protected_core.py

## Required implementation

- Implement the P10 schema and secure root-private persistence using existing no-follow, owner/mode/link-count, atomic-write and deterministic-canonicalization conventions.
- Derive protected inventory from already-verified installed release/inventory and a trusted protected-set definition. Include all relevant import/runtime copies and protection metadata.
- Provide status and fixed root+TTY enrollment without caller-selected candidate paths, arbitrary refs or --yes. Bind confirmation to current inventory, signer root, accepted state and lineage.
- Re-read all mutable inputs after confirmation; reject changes during the prompt, missing C6 anchors, mismatch, policy regression or unsafe existing state.
- Preserve current C6 stores and historical evidence. Mark predecessor protected-core history unverified; enrollment cannot claim the previous install was governed by this new protection.
- Keep successor operation explicitly inactive until the later controlled integration step, with no silent fallback once activated.

## Required behavioral and negative tests

- Non-root and non-TTY enrollment, pre-existing state overwrite, symlink/hardlink/permission attacks, partial writes and changed inputs during confirmation fail closed.
- Enrollment of an unverified or tampered current runtime is denied.
- Repeated status is read-only; repeated enrollment cannot silently rotate the anchor.
- Canonical vectors match P10 and preservation tests prove original C6 records remain unchanged.

Test command groups: **T0 T_TRUST T_FULL T_PACKAGE**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P11-A01** — Root-private protected state is independently validated and bound to verified current release anchors.
- [ ] **P11-A02** — Owner enrollment is fixed and explicit; no browser or candidate writer exists.
- [ ] **P11-A03** — Historical limitations and inactive/active states are observable.
- [ ] **P11-A04** — No managed update claims successor protection before P16 activation.

## Explicit exclusions

- No automatic key rotation.
- No retrospective proof of beta or earlier C6 installations.
- No enrolling a staged candidate as the current trusted core.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
