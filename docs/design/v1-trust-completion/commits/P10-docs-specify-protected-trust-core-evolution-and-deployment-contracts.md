# P10 — docs: specify protected trust-core evolution and deployment contracts

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P09
- Boundary closure gates: No hardware gate for this specification-only card; required review still applies.
- Required review: Maintainer/security design decision required before implementation of P11
- Suggested signed commit subject: docs: specify protected trust-core evolution and deployment contracts
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Changes to the machinery that enforces trust cannot silently redefine what an unchanged release manifest means. Existing C6 remains valid within its original scope.

## Minimum current-source read set

- open_mmi_trust/manifest.py
- open_mmi_trust/data/trust-manifest.v1.schema.json
- open_mmi_trust/accepted_state.py
- open_mmi_trust/transition_gate.py
- open_mmi_trust/release_integrity.py
- ui/update_installer.py
- scripts/manage.sh
- docs/trust-architecture.md
- CONTRIBUTING.md

## Proposed new paths — these do not yet exist merely because listed

- docs/design/v1-trust-completion/protected-core-contract.md
- open_mmi_trust/data/protected-core.v1.schema.json
- tests/fixtures/trust/protected-core/

## Required implementation

- Write a reviewed threat model defining protected code/data, owner authority, ordinary application code, root administrator escape and external verification assumptions.
- Enumerate protected scope: parsers/comparators, state/lineage writers, provenance/integrity verifier, deployment/recovery engine, enforcement brokers, privileged units, interpreter/import/dependency authority and rules that define the protected scope itself.
- Choose conservative explicit acknowledgement for any protected-set addition, removal or byte/control change until a separately reviewed mechanical compatibility rule exists. Do not ask a model to prove arbitrary program equivalence.
- Design versioned canonical data contracts for protected inventory, candidate delta, authorization binding and declarative deployment operations. Specify unknown-version/field handling, size limits and stable semantic IDs.
- Plan compatibility with strict manifest v1: a candidate cannot simply add unknown fields/capabilities and expect the old parser to authorize them. Separate bridge installation from explicit owner enrollment of the successor protection.
- Record a fixed initial bootstrap trust limitation, protected-state storage path decision and protection of the policy file that defines the protected set. Proposed paths are decisions, not existing installed files.
- Create independent accepted/rejected test vectors before active runtime gating.

## Required behavioral and negative tests

- Vectors include unchanged manifest with altered gate, removed sandbox, new privileged service, added native/import artifact, changed dependency, unchanged protected core and narrowed capability.
- A candidate-supplied classification or allowlist never overrides old-code classification.
- Old v1 fixtures retain their original results; unknown successor formats fail closed rather than being reinterpreted.
- Policy tests demonstrate that changing the protected-set definition itself is protected.

Test command groups: **T0 T_TRUST T_DOC**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P10-A01** — The maintainer-reviewed contract resolves protected scope, activation sequence, storage authority and supported threat claims.
- [ ] **P10-A02** — Versioned schema/vectors have stable canonical digests and explicit denial cases.
- [ ] **P10-A03** — No existing runtime behavior or owner trust state is silently migrated.
- [ ] **P10-A04** — P11–P16 can implement the contract without inventing missing authority decisions.

## Explicit exclusions

- No declaration that C6 was incomplete or must be rewritten wholesale.
- No automatic allowance for signed Trust Core changes.
- No promise to resist a malicious kernel without an independent/hardware anchor.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
