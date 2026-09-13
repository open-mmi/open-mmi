# P07 — docs: record C7 completion evidence and operating limits

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: P06
- Boundary closure gates: G1
- Required review: Maintainer diff review
- Suggested signed commit subject: docs: record C7 completion evidence and operating limits
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

C7 is called complete only for a recorded code subject with authoritative status, usable setup guidance, preserved root+TTY mutation and qualified CAN dependencies.

## Minimum current-source read set

- docs/trust-architecture.md
- docs/getting-started.md
- docs/manual-administration.md
- docs/release-checklist.md
- CHANGELOG.md
- ui/web_dashboard/README.md

## Proposed new paths — these do not yet exist merely because listed

- docs/design/v1-trust-completion/evidence/c7-closeout.json

## Required implementation

- Collect G0/G1 results with exact subject code commit, installed identity, policy/inventory digests, machine role and evidence references.
- Reconcile obsolete statements about missing checker, listen-only, direct dashboard inspection, build execution and completed versus pending phases.
- Preserve C6's established milestone while listing later strengthening separately.
- Record baseline-existing-state for beta-to-feature migration and history_before_baseline=unverified; do not retrofit trust continuity to legacy beta.
- Update progress and the closure matrix; do not mark remote identity, protected-core continuity or release readiness complete here.
- This can be a documentation/evidence commit. Record the previously tested code commit as the subject and the later recording commit separately.

## Required behavioral and negative tests

- Validate the handoff ledger and linked evidence digests; every P01–P06 criterion must map to a result or a clearly unresolved blocker.
- Check cited commands against current CLI --help and actual file paths.
- Verify docs do not imply a browser mutation surface, a physical listen-only requirement or hardware proof from CI.
- Reuse qualified runtime evidence when only excluded documentation files change; record why the tested runtime inventory is unchanged.

Test command groups: **T0 T_DOC**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P07-A01** — G1 passed on the relevant code subject; unresolved failures block the C7 completion label.
- [ ] **P07-A02** — Owner setup, service lifecycle, prepared expansion guidance and CAN evidence are linked.
- [ ] **P07-A03** — C6, C7, future strengthening and release gates have unambiguous separate statuses.
- [ ] **P07-A04** — A new agent can resume at P08 using the ledger without the prior chat.

## Explicit exclusions

- No invented test output or retroactive vehicle qualification.
- No runtime code change solely to produce a milestone commit.
- No promotion to nightly/beta/main within this card.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
