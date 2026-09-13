# P03 — fix: distinguish static trust contracts from live enforcement evidence

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: P02
- Boundary closure gates: G1
- Required review: Maintainer diff review
- Suggested signed commit subject: fix: distinguish static trust contracts from live enforcement evidence
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

An Inspector PASS for signed configuration does not assert that a namespace or enforcement rule was observed live. Overall and per-check labels preserve the provenance and limits of their evidence.

## Minimum current-source read set

- open_mmi_trust/inspector.py
- open_mmi_trust/data/trust-inspection.v1.schema.json
- ui/trust_status_coordinator.py
- ui/web_dashboard/static/trust-status.js
- independent_checker/open_mmi_trust_check.py
- tests/test_trust_inspector.py
- tests/test_independent_trust_checker.py
- tests/js/trust_status.test.js
- docs/trust-architecture.md

## Proposed new paths — these do not yet exist merely because listed

None specified. Add a file only when the bounded implementation needs it, and record it.

## Required implementation

- Inventory existing consumers of check IDs and report schema; choose a backward-compatible additive evidence shape or an explicit report-version change with consumer updates.
- Separate declared policy, signed/static contract, independently observed runtime enforcement and hardware qualification. Retain PASS/FAIL/UNVERIFIED semantics within each defined dimension.
- Remove unconditional live claims such as physical_interface_host_visible=False where no live observation occurred.
- The AF_UNIX-only coordinator must not gain NET_ADMIN or broad namespace access merely to produce a green status. Prefer accurately reporting static evidence and referring to independent measurements.
- If an independent report is displayed, bind it to subject commit, inventory/policy digests, observation time and boot/namespace identity; stale or unbound results are not current proof.
- Update Inspector wording, independent-checker wording, UI labels and docs together; reconcile stale listen-only claims.

## Required behavioral and negative tests

- Valid source/unit files with no live observation cannot yield a live-enforcement PASS.
- A changed boot/namespace/source commit invalidates any previously attached runtime observation.
- FAIL dominates contradictory evidence; unavailable evidence remains UNVERIFIED and cannot be hidden by static PASS.
- Older supported report clients remain functional or explicitly report unsupported versions, never reinterpret fields.
- No new network, trust-write or namespace-management authority appears in the status service.

Test command groups: **T0 T_UI T_TRUST T_CAN T_FULL T_BROWSER**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P03-A01** — Every relevant check states what was inspected and what was not.
- [ ] **P03-A02** — The new CAN Inspector note accurately matches P02 checker capabilities.
- [ ] **P03-A03** — Schema/consumer tests and stale-evidence cases pass.
- [ ] **P03-A04** — G1 dashboard screenshots and independent reports show consistent but separately scoped statuses.

## Explicit exclusions

- No automatic invocation of privileged repair from inspection.
- No changing declared assurance solely to hide absent evidence.
- No claiming OS inspection equals hardware attestation.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
