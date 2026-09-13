# P01 — fix: read dashboard trust evidence through the privileged coordinator

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: No new-code prerequisite; inspect the actual baseline first.
- Boundary closure gates: G1
- Required review: Maintainer diff review
- Suggested signed commit subject: fix: read dashboard trust evidence through the privileged coordinator
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

The installed unprivileged dashboard obtains authoritative trust evidence only from the fixed privileged read-only status service. Neither the browser nor a fallback local Inspector can manufacture owner authority.

## Minimum current-source read set

- ui/web_dashboard/trust_status.py
- ui/trust_status_coordinator.py
- ui/web_dashboard/server.py
- systemd/system/open-mmi-trust-status.service
- tests/test_web_dashboard_trust_status.py
- tests/test_trust_status_coordinator.py
- tests/js/trust_status.test.js
- tests/browser/dashboard.spec.js

## Proposed new paths — these do not yet exist merely because listed

None specified. Add a file only when the bounded implementation needs it, and record it.

## Required implementation

- Replace the production default in trust_status_payload with the existing coordinator client; retain dependency injection only for tests with an explicit contract.
- Validate the coordinator envelope, API version, allowed status, report shape and error response before exposing it; avoid accepting payload.status=PASS alongside report.status=FAIL.
- Keep GET /api/trust/status and the current dashboard response contract stable unless a versioned additive change is justified.
- Map unavailable socket, permission denial, timeout, malformed/truncated/oversized reply and coordinator failure to UNVERIFIED with sanitized guidance. Do not fall back to direct inspection of private files.
- Keep the service protocol fixed to status. Do not add sudo subprocesses to the web process, root file permissions for the dashboard, or mutation routes.
- Confirm socket ownership/group configuration permits the actual desktop account after a deliberate group refresh. Use existing open-mmi-update group conventions.
- Update the old test that explicitly assumes direct Inspector imports; replace source-string assumptions with behavioral routing tests.

## Required behavioral and negative tests

- Patch the coordinator client and local Inspector independently: an ordinary GET must call the former and must not invoke the latter.
- A socket service running with permission to a fixture private store returns evidence to a client without granting file access. Real root/non-root separation belongs in an isolated Linux integration fixture or G1, not a mocked claim.
- Reject mismatched report/envelope statuses, unknown versions, duplicate JSON keys, invalid framing and unauthorized mutation actions.
- Stop/restart the coordinator during a visible Trust page; status becomes unavailable and recovers without a page crash or stale PASS.
- Assert POST /api/trust/status and trust-acceptance POST paths remain unavailable.

Test command groups: **T0 T_UI T_SOCKET T_TRUST T_FULL T_BROWSER**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P01-A01** — The production adapter calls client_status and has no direct-inspection fallback.
- [ ] **P01-A02** — All client failure cases preserve UNVERIFIED and disclose no private raw exception or state.
- [ ] **P01-A03** — GET API, browser rendering and socket round-trip regressions pass on an appropriate Linux environment.
- [ ] **P01-A04** — The installed unprivileged dashboard/service round trip is recorded at G1 before C7.1 is called complete.

## Explicit exclusions

- No trust-state mutation or telemetry consent change.
- No CAN topology changes.
- No broad frontend reorganization.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
