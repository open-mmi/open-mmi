# P09 — test: measure network and persistence confinement under adversarial inputs

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: B — Enforcement closure
- Implementation prerequisites: P08
- Boundary closure gates: G2
- Required review: Maintainer/security review of effective runtime evidence
- Suggested signed commit subject: test: measure network and persistence confinement under adversarial inputs
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Declared egress and persistence purposes correspond to enforceable installed process/data boundaries; static unit text alone does not establish effective confinement.

## Minimum current-source read set

- ui/media_egress.py
- ui/vehicle_store.py
- ui/owner_config.py
- systemd/system/open-mmi-media-egress.service
- systemd/system/open-mmi-vehicle-store.service
- systemd/user/canbusd.service
- systemd/user/open-mmi-dashboard.service
- tests/test_network_egress.py
- tests/test_persistence_enforcement.py
- tests/test_trust_inspector.py
- independent_checker/open_mmi_trust_check.py

## Proposed new paths — these do not yet exist merely because listed

- tests/integration/test_trust_confinement.py
- docs/design/v1-trust-completion/confinement-evidence.md

## Required implementation

- Build disposable Linux integration fixtures using the actual installed units and process identities, separate from the user's desktop/tablet configuration.
- Attempt direct non-loopback networking from normal core processes and durable writes outside declared-purpose storage; verify failures and legitimate broker/store operations.
- Check effective drop-ins, namespace/address-family restrictions, writable paths, inherited descriptors, accessible Unix sockets and service credentials.
- Validate broker operations and storage records with exact purpose/type/range contracts; reject arbitrary URLs, paths, field names and unbounded payloads.
- Fix specific discovered enforcement holes only; do not convert an Inspector string check into a claimed runtime probe.
- Persist reusable synthetic evidence with host/kernel/systemd/tool versions and exact tested tree identity.

## Required behavioral and negative tests

- Unprivileged core cannot reach external listeners directly or write undeclared durable vehicle data.
- Normal trip/service state works; malformed/extra fields, path traversal, replayed revisions and unauthorized peer identities fail closed.
- Altered effective unit/drop-in or unsupported enforcement support yields FAIL/UNVERIFIED as appropriate.
- Exercise service restarts and descriptor/socket sharing to detect routes that source scans cannot see.
- Regression tests include the P08 identity separation.

Test command groups: **T0 T_IDENTITY T_PERSIST T_TRUST T_FULL T_ISOLATION**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P09-A01** — An effective runtime test exists for each claimed OS-enforced network/persistence control.
- [ ] **P09-A02** — Supported purpose functionality survives the confinement.
- [ ] **P09-A03** — Known unsupported host configurations are explicit and cannot yield an enforcement PASS.
- [ ] **P09-A04** — G2 records synthetic confinement; tablet applicability is rechecked at G4.

## Explicit exclusions

- No general network firewall for the user's machine.
- No new telemetry collection or persistence purpose.
- No treating localhost access as automatically trustworthy IPC.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
