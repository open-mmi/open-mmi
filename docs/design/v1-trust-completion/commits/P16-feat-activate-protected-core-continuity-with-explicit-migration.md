# P16 — feat: activate protected-core continuity with explicit migration

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: C — Strengthen future continuity
- Implementation prerequisites: P15
- Boundary closure gates: G2
- Required review: Maintainer/security approval of migration and activation; implementation preparation is independent of tablet permission
- Suggested signed commit subject: feat: activate protected-core continuity with explicit migration
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Existing C6 users can deliberately establish stronger future protection without a false historical claim or an automatic fallback that defeats the new boundary.

## Minimum current-source read set

- open_mmi_trust/transition_gate_cli.py
- open_mmi_trust/inspector.py
- ui/update_installer.py
- ui/update_coordinator.py
- ui/web_dashboard/static/system-settings.js
- ui/web_dashboard/static/trust-status.js
- docs/trust-architecture.md
- docs/manual-administration.md
- tests/test_update_installer.py
- tests/test_update_coordinator.py

## Proposed new paths — these do not yet exist merely because listed

- tests/test_protected_core_migration.py
- docs/design/v1-trust-completion/protected-core-migration.md

## Required implementation

- Implement the reviewed P10 bridge/enrollment/activation sequence. Explicitly identify the first commit/anchor from which successor protection applies.
- Require valid existing C6 integrity, provenance, owner state and lineage for enrollment on an established installation; legacy beta migration remains a separate new-baseline operation.
- After activation, route all managed prepared-update entry points through protected-delta checks and the trusted deployment/recovery engine.
- If active successor state or executable support is missing/corrupt/unsupported, block. Do not fall back to the former candidate-script path.
- Keep manual root administration available only as an explicit out-of-band operation whose continuity consequences are visible; do not confuse it with a gated update.
- Expose activation state and history limits read-only in Inspector/UI; maintain precise root+TTY owner instructions.

## Required behavioral and negative tests

- Existing valid C6, missing C6 anchor, legacy beta, already-active, partial enrollment and unsupported version each have distinct tested outcomes.
- Old-schema clients reject unsupported successor state safely.
- Exercise every managed install entry point; none bypasses protected-core checks after activation.
- A manual altered install cannot automatically inherit previous protected continuity.
- Cross-check new state fixtures with P17/P18 before tablet successor activation and final G2 closure.

Test command groups: **T0 T_TRUST T_UPDATE T_UI T_FULL T_BROWSER T_RECOVERY**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P16-A01** — The first protected checkpoint and activation event are explicit and immutable evidence.
- [ ] **P16-A02** — All managed update paths enforce the successor contract when active.
- [ ] **P16-A03** — Legacy/C6/successor histories and guarantees remain distinguishable.
- [ ] **P16-A04** — G2 plus independent compatibility evidence are required before describing the stronger boundary as complete.

## Explicit exclusions

- No automatic tablet channel switch.
- No retroactive protected-history fabrication.
- No removal or redefinition of completed C6 functionality.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
