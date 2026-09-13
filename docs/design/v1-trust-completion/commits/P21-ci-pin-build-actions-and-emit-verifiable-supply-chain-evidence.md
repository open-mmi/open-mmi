# P21 — ci: pin build actions and emit verifiable supply-chain evidence

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: E — Supply-chain and release
- Implementation prerequisites: P20
- Boundary closure gates: G4
- Required review: Maintainer review of workflow authority and artifact evidence
- Suggested signed commit subject: ci: pin build actions and emit verifiable supply-chain evidence
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

CI inputs and generated evidence identify what built the artifact. A green run or mutable Action tag does not substitute for pinned inputs and artifact identity.

## Minimum current-source read set

- .github/workflows/ci.yml
- pyproject.toml
- package-lock.json
- tests/test_release_engineering.py
- tests/test_release_readiness.py
- tools/verify_wheel.py

## Proposed new paths — these do not yet exist merely because listed

- tools/build_release_evidence.py
- tests/test_release_evidence.py

## Required implementation

- Resolve official Action release references to reviewed full commit SHAs at implementation time and record their upstream versions; do not invent or reuse stale SHAs from this plan.
- Minimize workflow token permissions and protect signing/publishing from untrusted pull-request execution while retaining ordinary PR test coverage.
- Emit an SBOM/dependency inventory, source identity, lock digests, toolchain versions, workflow identity and produced artifact digests in deterministic machine-readable form.
- Verify first-party wheel/static/checker content and cross-check the SBOM against locked and installed packages.
- Keep build execution, verification and publication separated. This commit prepares evidence and does not publish a release.
- Document which reproducibility claims are actually tested; mutable runner images or external system packages remain explicit assumptions.

## Required behavioral and negative tests

- Tampered lock, SBOM omission, unexpected package, wrong source identity or artifact substitution fails verification.
- Fork/untrusted PR jobs cannot obtain signing or publication authority.
- Two supported clean builds produce matching normalized inventories; byte reproducibility is claimed only where tested.
- CI evidence uses the exact tested subject SHA and retains diagnostics on failed verification.

Test command groups: **T0 T_FULL T_PACKAGE T_SUPPLY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P21-A01** — Action refs are verified pins and workflow privileges are reviewed.
- [ ] **P21-A02** — Machine-readable build/dependency evidence is complete and tied to artifact digests.
- [ ] **P21-A03** — Artifact verification runs before any potential publication job.
- [ ] **P21-A04** — Release limitations accurately identify non-hermetic host inputs.

## Explicit exclusions

- No user secret disclosure or logging of credentials.
- No automatic release publishing.
- No broad CI rewrite unrelated to trust/release inputs.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
