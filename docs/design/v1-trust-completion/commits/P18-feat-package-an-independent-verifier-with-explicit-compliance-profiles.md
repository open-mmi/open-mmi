# P18 — feat: package an independent verifier with explicit compliance profiles

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: D — Independent evidence
- Implementation prerequisites: P17
- Boundary closure gates: G3
- Required review: Maintainer/security review of independence and SI compliance claims
- Suggested signed commit subject: feat: package an independent verifier with explicit compliance profiles
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Official provenance, policy compliance, owner authorization, installed integrity and externally anchored continuity are independently reported and verifiable without importing the target installation.

## Minimum current-source read set

- independent_checker/open_mmi_trust_check.py
- independent_checker/open_mmi_can_trust_test.py
- independent_checker/README.md
- tests/test_independent_trust_checker.py
- tests/test_independent_can_trust.py
- tools/verify_wheel.py
- docs/trust-architecture.md

## Proposed new paths — these do not yet exist merely because listed

- independent_checker/spec/
- independent_checker/test_vectors/
- tools/build_independent_checker_bundle.py
- tests/test_independent_checker_bundle.py

## Required implementation

- Extend the standalone verifier for the finalized P10–P17 schemas, protected-core classification and externally witnessed continuity requirements.
- Ship versioned specification and conformance vectors with a reproducible standalone bundle and a documented independent executable-digest acquisition path.
- Separate official-release provenance from a reviewed SI profile. Modified distribution bytes do not become compliant merely because the SI signed them; identify what trusted external profile/implementation evidence establishes compliance.
- Permit supported non-protected/profile modifications only under explicit reviewed contracts. Unknown modified enforcement implementations remain UNVERIFIED until independently qualified.
- Support read-only mounted-target inspection with trusted host tools and without consuming target Inspector output.
- Prepare, but do not create or publish, a separate verifier repository/release if the maintainer chooses that distribution route. Local independence and independently acquired distribution are separate claims.

## Required behavioral and negative tests

- Run checker in an environment with no Open MMI package installed and a deliberately malicious target package that must never execute.
- Validate shared conformance vectors independently; include unknown schema, missing files, official-but-boundary-expanded release, reviewed SI profile and unreviewed SI enforcement changes.
- Test externally pinned checker digest mismatch and trusted mounted-target operation.
- Verify bundle completeness, deterministic contents and no dependency on the source checkout or target-controlled executables.

Test command groups: **T0 T_INDEPENDENT T_TRUST T_FULL T_PACKAGE**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P18-A01** — All successor formats and limits are independently implemented.
- [ ] **P18-A02** — Results cannot conflate signer identity with compliance or owner authorization.
- [ ] **P18-A03** — A portable bundle works from a separate trusted environment and has a clear independent anchoring procedure.
- [ ] **P18-A04** — G3 evidence covers official, supported SI and unverified/failed cases.

## Explicit exclusions

- No self-issued universal SI PASS badge.
- No importing target code or asking target code for verification answers.
- No remote repository creation, publication or signer-root changes without explicit maintainer action.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
