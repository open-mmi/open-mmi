# P20 — build: lock supported release dependencies and offline installation inputs

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: E — Supply-chain and release
- Implementation prerequisites: P19
- Boundary closure gates: G4
- Required review: Maintainer review of supported platforms and protected dependency scope
- Suggested signed commit subject: build: lock supported release dependencies and offline installation inputs
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

A reviewed release identifies the dependency bytes and platform inputs actually used for build/install; the prepared installer cannot silently substitute packages from the network.

## Minimum current-source read set

- pyproject.toml
- package-lock.json
- scripts/manage.sh
- open_mmi_trust/release_integrity.py
- ui/update_installer.py
- tests/test_release_engineering.py
- tests/test_release_readiness.py
- tests/test_release_integrity.py

## Proposed new paths — these do not yet exist merely because listed

- packaging/locks/
- tools/verify_release_dependencies.py
- tests/test_release_dependencies.py

## Required implementation

- Inventory Python, native, JavaScript, system-tool and interpreter dependencies and decide which are bundled, hash-locked or explicitly host-assumed. Confirm actual supported Python/CPU/OS targets; do not guess the tablet architecture.
- Generate reviewed exact-version/hash lock data for supported release environments while preserving declared compatibility metadata where appropriate.
- Account for native evdev and other binary dependencies in provenance/integrity policy; distinguish first-party inventory from third-party dependency assurance.
- Keep prepared deployment offline and fail on missing/incompatible/unverified dependencies. A changed protected dependency participates in P12 classification.
- Use trusted build infrastructure to construct artifacts; candidate source/build hooks must not run during old-side trust assessment.
- Document bootstrap installation trust separately from protected future updates, including host tool assumptions and patch-level dependency updates.

## Required behavioral and negative tests

- Rebuild/install with a disabled network from approved inputs; missing hashes, substituted wheels, incompatible ABI/architecture and unexpected versions fail.
- Validate clean-environment imports and project tests on the supported Python/platform matrix.
- No fallback to online pip, arbitrary mirrors or unpinned latest packages occurs in protected installation.
- Dependency-only changes appear in the appropriate protected delta/release metadata.

Test command groups: **T0 T_TRUST T_UPDATE T_FULL T_PACKAGE T_SUPPLY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P20-A01** — Supported release platforms have reproducible dependency selection and verified input bytes.
- [ ] **P20-A02** — Offline installation succeeds using approved inputs and fails on substitutes.
- [ ] **P20-A03** — Unbundled host assumptions are explicit rather than hidden inside a full-integrity claim.
- [ ] **P20-A04** — Full reproducible OS images remain optional; locked release inputs are mandatory for the stated scope.

## Explicit exclusions

- No global Python/system package modification on the dev machine.
- No dropping supported architectures silently.
- No claiming third-party native code is covered by the existing first-party inventory without evidence.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
