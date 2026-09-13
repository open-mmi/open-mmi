# P08 — security: close the supported remote vehicle identity boundary

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: B — Enforcement closure
- Implementation prerequisites: P07
- Boundary closure gates: G2
- Required review: Maintainer/security review required for the data-flow model and any media input restriction
- Suggested signed commit subject: security: close the supported remote vehicle identity boundary
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Supported Open MMI identity data has no authorized remote-resolution path. Closure rests on data access and mediated egress, not on a regex or owner trust acknowledgement alone.

## Minimum current-source read set

- open_mmi_trust/vehicle_identity.py
- open_mmi_telemetry/guard.py
- ui/media_egress.py
- ui/media_egress_config.py
- ui/egress_client.py
- ui/update_coordinator.py
- open_mmi_trust/inspector.py
- systemd/system/open-mmi-media-egress.service
- systemd/system/open-mmi-update-coordinator.service
- tests/test_vehicle_identity_remote_resolution.py
- tests/test_network_egress.py

## Proposed new paths — these do not yet exist merely because listed

- docs/design/v1-trust-completion/identity-boundary.md

## Required implementation

- Map every actual identity source, allowed local reader, IPC payload, durable store and external-network actor before coding. Include local VIN authorization, CAN-derived identity, profile metadata and media/query inputs.
- Record the threat model explicitly: trusted enforcement components versus ordinary app components, owner-entered media text, encoded values and deliberately modified privileged code.
- Retain useful existing recognized-identity guards, but demonstrate whether identity can reach an allowed broker through encoding, alternate fields or shared IPC. Do not claim a general information-flow guarantee from token detection.
- Narrow broker inputs and filesystem/IPC access where the supported identity data path requires it. Preserve legitimate media functionality through explicit typed operations and trusted configuration.
- If a compromised component can both read identity and send arbitrary media queries, present that concrete path and the proposed separation for maintainer review; do not broaden the promise or silently remove search.
- Update Inspector/checker contracts and privacy wording to the demonstrable boundary. Leave unresolved paths blocked in the ledger until architectural closure is proven.

## Required behavioral and negative tests

- Reject raw, URL-encoded, double-encoded and alternate-field recognized identity before remote call sites; assertions inspect zero outbound attempts and redacted errors.
- Test actual broker process identities cannot read the protected identity stores or receive identity-bearing operational IPC.
- Verify ordinary media requests, credentials and supported searches still function.
- Add a regression for each discovered data-flow path, including pre-network hooks rather than only regex unit tests.
- Test maliciously altered privileged software as outside v1 guard assurance and explicitly cover its protected-code treatment in P10–P16.

Test command groups: **T0 T_IDENTITY T_TRUST T_FULL T_ISOLATION**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P08-A01** — The reviewed data-flow map contains no unresolved supported identity-to-remote-resolution path.
- [ ] **P08-A02** — Positive functionality and pre-egress denial tests pass in an appropriate Linux isolation environment.
- [ ] **P08-A03** — Assurance labels and documentation match demonstrated enforcement and declared threat scope.
- [ ] **P08-A04** — G2 includes this boundary; acknowledgement is never used as substitute enforcement.

## Explicit exclusions

- No general PII classifier or new remote VIN service.
- No harvesting real VINs for test fixtures.
- No declaring full closure while a documented encoding/IPC escape remains.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
