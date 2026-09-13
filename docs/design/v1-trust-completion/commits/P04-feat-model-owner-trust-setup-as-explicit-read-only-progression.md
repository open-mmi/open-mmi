# P04 — feat: model owner trust setup as explicit read-only progression

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: P03
- Boundary closure gates: G1
- Required review: Maintainer diff review
- Suggested signed commit subject: feat: model owner trust setup as explicit read-only progression
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Next-step guidance derives from authoritative current evidence and existing CLI prerequisites. It never treats missing evidence, corruption or legacy migration as permission to bootstrap over established authority.

## Minimum current-source read set

- ui/web_dashboard/trust_status.py
- ui/trust_status_coordinator.py
- open_mmi_trust/accepted_state_cli.py
- open_mmi_trust/lineage_cli.py
- open_mmi_trust/release_integrity_cli.py
- open_mmi_trust/release_provenance_cli.py
- open_mmi_trust/transition_gate_cli.py
- tests/test_web_dashboard_trust_status.py

## Proposed new paths — these do not yet exist merely because listed

- ui/web_dashboard/trust_setup.py
- tests/test_trust_setup.py

## Required implementation

- Implement a pure state-to-guidance model covering accepted baseline, lineage, installed integrity, pinned provenance, prepared transition and evidence availability.
- Preserve independent dimensions: signature provenance, accepted permissions, history and runtime enforcement must not collapse into a misleading one-bit trust badge.
- Follow actual prerequisite order: inspect/review current release; accept-current creates the first accepted-state plus lineage baseline; separately bootstrap lineage only for an existing accepted state without lineage; integrity requires valid accepted state/lineage; provenance requires valid current integrity and independently verified signer material.
- Provide bounded allowlisted action identifiers and explanatory text, not arbitrary command strings supplied by reports or candidate code. Existing CLI commands stay the only mutation authority.
- Differentiate not-established from unreadable, malformed, inconsistent, broadened-after-install and history-before-baseline-unverified.
- Return recovery guidance for corruption or stale prepared state; never suggest accept-current as a way to authorize an already-installed expansion.

## Required behavioral and negative tests

- Use a table-driven fixture for every meaningful combination, including legacy baseline, accepted-without-lineage, bad lineage, missing integrity, signer missing/mismatched and candidate expansion.
- No action has unsatisfied prerequisites; no corrupted state maps to normal bootstrap or generic accept guidance.
- Equivalent/narrower update eligibility is independent of optional telemetry authorization.
- A refreshed report changes the suggested step deterministically without mutating any trust files.

Test command groups: **T0 T_UI T_TRUST T_FULL**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P04-A01** — State fixture matrix and exact allowed action vocabulary are checked into the repo.
- [ ] **P04-A02** — Guidance order agrees with current owner CLIs and preserves all error distinctions.
- [ ] **P04-A03** — No code path writes trust state or invokes privileged commands.
- [ ] **P04-A04** — The model exposes enough provenance for the UI to explain each blocker.

## Explicit exclusions

- No new bootstrap CLI, convenience bypass or --yes option.
- No requirement to authorize telemetry to complete trust setup.
- No assumed signer fingerprint, candidate path or user-specific username.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
