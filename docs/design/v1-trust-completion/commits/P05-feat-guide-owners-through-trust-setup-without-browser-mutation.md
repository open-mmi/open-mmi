# P05 — feat: guide owners through trust setup without browser mutation

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: P04
- Boundary closure gates: G1
- Required review: Maintainer diff review
- Suggested signed commit subject: feat: guide owners through trust setup without browser mutation
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

The 800×480 owner experience explains status, the next valid local action and its limits, while browser trust operations remain read-only.

## Minimum current-source read set

- ui/web_dashboard/static/trust-status.js
- ui/web_dashboard/static/system-settings.js
- ui/web_dashboard/static/index.html
- ui/web_dashboard/static/styles-system-settings.css
- tests/js/trust_status.test.js
- tests/js/system_settings.test.js
- tests/browser/dashboard.spec.js
- ui/web_dashboard/README.md
- docs/getting-started.md

## Proposed new paths — these do not yet exist merely because listed

None specified. Add a file only when the bounded implementation needs it, and record it.

## Required implementation

- Render clear setup stages from P04: what is established, what is missing, why an update is blocked and what the owner can review next.
- Use the established Settings layout, visibility-aware refresh and connection recovery conventions. Keep long digests in bounded technical details with accessible exact values.
- Show existing terminal commands only when appropriate to the model. Never prefill a confirmation phrase as if reviewed or run a command from the browser.
- Keep C7.4 prepared-expansion guidance intact; show changed capability/purpose/assurance and exact-candidate context without duplicating contradictory notices.
- Treat revoked/absent telemetry authorization as a normal default-deny privacy state, not setup failure.
- Update first-time/legacy owner docs with the evidence prerequisites and explicit beta-to-feature new-baseline semantics.

## Required behavioral and negative tests

- JS tests cover all P04 states and malformed model input.
- Playwright at 800×480 verifies overflow, touch navigation, unavailable/recovered service, refresh after a CLI-side change fixture and a stale prepared update.
- Ensure no browser interaction sends a trust-mutation POST or accepts a candidate-selected command/path.
- Test keyboard/screen-reader labels and full-digest access without persistent private data in localStorage.
- Existing update, media, vehicle setup and dashboard connection tests remain green.

Test command groups: **T0 T_UI T_TRUST T_FULL T_BROWSER**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P05-A01** — An owner can identify the next valid action without reading raw check IDs.
- [ ] **P05-A02** — Unavailable or stale evidence cannot leave a green completed stage displayed.
- [ ] **P05-A03** — C7.4 behavior and read-only trust boundaries remain intact.
- [ ] **P05-A04** — G1 records the real tablet UI and a completed new-baseline progression.

## Explicit exclusions

- No UI redesign outside Trust and directly related update guidance.
- No browser terminal, sudo helper or trust-acceptance button.
- No telemetry opt-in default change.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
