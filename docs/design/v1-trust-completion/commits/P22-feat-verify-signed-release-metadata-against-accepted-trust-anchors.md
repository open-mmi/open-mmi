# P22 — feat: verify signed release metadata against accepted trust anchors

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: E — Supply-chain and release
- Implementation prerequisites: P21
- Boundary closure gates: G4
- Required review: Maintainer/security review of metadata coverage, replay policy and signing
- Suggested signed commit subject: feat: verify signed release metadata against accepted trust anchors
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Release metadata binds source, artifacts, dependencies, trust declaration and checker contract to a reviewed signer, while owner capability/protected-core authorization remains a separate gate.

## Minimum current-source read set

- open_mmi_trust/release_provenance.py
- open_mmi_trust/release_integrity.py
- ui/update_coordinator.py
- ui/update_installer.py
- independent_checker/open_mmi_trust_check.py
- tests/test_release_provenance.py
- tests/test_update_installer.py
- tests/test_release_readiness.py

## Proposed new paths — these do not yet exist merely because listed

- open_mmi_trust/data/release-metadata.v1.schema.json
- tools/verify_release_metadata.py
- tests/test_release_metadata.py

## Required implementation

- Define canonical signed metadata covering source commit, artifact digests/sizes/platforms, manifest generation/digest, protected inventory, dependency/SBOM/build evidence and supported checker contract.
- Authenticate using the independently pinned signer policy. Disable network key discovery and automatic signer rotation; key lifecycle changes need their own reviewed owner path.
- Verify metadata before artifact use, then verify actual downloaded/staged bytes, exact ancestry and old-side policy/protected deltas. A metadata signature alone cannot authorize an expansion.
- Specify rollback/replay/channel/version rules using current repository policy; Git beta and updater beta/stable are not interchangeable.
- Extend standalone verification and damaged/substituted-artifact diagnostics.
- Prepare signed metadata creation commands and unsigned reviewable inputs; only the maintainer signs or publishes after explicit approval.

## Required behavioral and negative tests

- Wrong signer, expired/unsupported metadata policy, wrong commit/platform/channel, truncated metadata, duplicate keys, missing artifact and substituted SBOM/wheel/checker fail closed.
- A correctly signed broader policy still requires owner acknowledgement.
- Old metadata cannot silently roll back current owner/protected state or release ancestry.
- An offline verifier can validate a supported release bundle from independent anchors without the installed application.

Test command groups: **T0 T_TRUST T_INDEPENDENT T_UPDATE T_FULL T_PACKAGE T_SUPPLY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P22-A01** — Signatures bind the complete released object graph and actual artifact bytes are checked.
- [ ] **P22-A02** — Owner authority and provenance remain distinct in code and UI.
- [ ] **P22-A03** — Independent verification understands the same metadata without target imports.
- [ ] **P22-A04** — G4 verifies the exact release candidate bundle before promotion/publication.

## Explicit exclusions

- No trusting GitHub Verified badges as roots.
- No automatic key rotation, downgraded policy or candidate-selected metadata verifier.
- No enabling unsupported stable/beta installation paths implicitly.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
