# P19 — feat: bind visible trust inspection to a fresh external challenge

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: D — Independent evidence
- Implementation prerequisites: P18
- Boundary closure gates: G3, G4
- Required review: Maintainer/security and hardware-protocol review before transport implementation
- Suggested signed commit subject: feat: bind visible trust inspection to a fresh external challenge
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

A fresh challenge can request and bind read-only inspection evidence, but cannot grant capabilities, acknowledge trust, install software, enable telemetry or make Open MMI transmit onto CAN.

## Minimum current-source read set

- independent_checker/open_mmi_can_trust_test.py
- canbusd/core.py
- canbusd/event_bus.py
- canbusd/data/vehicle-events.v1.json
- ui/web_dashboard/static/trust-status.js
- ui/web_dashboard/server.py
- tests/test_independent_can_trust.py
- tests/browser/dashboard.spec.js
- docs/vehicle-integration-standard.md

## Proposed new paths — these do not yet exist merely because listed

- docs/design/v1-trust-completion/inspection-challenge.md
- tests/test_trust_inspection_challenge.py

## Required implementation

- Review the supported challenge transport and its safety contract first. Never invent a production CAN identifier or inject frames into a live vehicle to find a route.
- Reuse canonical event/status conventions where the chosen transport requires them, with explicit schema/version, bounded payload, freshness/expiry, collision handling and rate limits.
- Bind the visible nonce/result to a fresh inspection report and exact policy/release/lineage/protected-core identity. A displayed nonce alone is not proof of compliance.
- Keep external tester transmission distinct from Open MMI reception; no reply or new send call in production runtime.
- Treat no response, unsupported route, stale challenge and missing independent evidence as UNVERIFIED. Do not convert gateway/wiring failure into a proven policy violation.
- If only isolated vcan/bench transport is approved, label that support accurately and keep production field-transport completion pending.

## Required behavioral and negative tests

- Replay old nonce/result, wrong target identity, changed release during collection, truncated challenge, flooding and missing response cannot produce fresh PASS.
- Challenge receipt invokes only inspection; instrument update, trust-write, telemetry and CAN-send paths and assert no invocation.
- Independent observation sees only checker-owned test frames on the isolated fixture.
- UI displays the exact challenge and evidence identity at 800×480; old screenshots/results cannot satisfy a new nonce.

Test command groups: **T0 T_CAN T_TRUST T_UI T_FULL T_BROWSER T_SYNTH**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P19-A01** — Approved transport and supported environments are documented without invented vehicle protocol assumptions.
- [ ] **P19-A02** — Freshness and exact-evidence binding are checked independently.
- [ ] **P19-A03** — No mutation or CAN-transmit authority is introduced.
- [ ] **P19-A04** — G3/G4 distinguish synthetic challenge proof from qualified field delivery and stronger hardware attestation.

## Explicit exclusions

- No generic vehicle command channel or challenge acknowledgement over CAN.
- No claim that a nonce defeats a malicious OS by itself.
- No production vehicle injection without a separately reviewed controlled test plan.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
