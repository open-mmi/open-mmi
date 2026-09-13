# P02 — fix: independently verify the private CAN receive topology

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: P01
- Boundary closure gates: G1
- Required review: Maintainer/security review of independent measurement and namespace selection
- Suggested signed commit subject: fix: independently verify the private CAN receive topology
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Independent CAN evidence measures the actual ACK-capable namespace/gateway/DROP topology and never imports the target implementation or grants Open MMI a transmit action.

## Minimum current-source read set

- independent_checker/open_mmi_can_trust_test.py
- independent_checker/open_mmi_trust_check.py
- independent_checker/README.md
- ui/can_namespace.py
- systemd/system/open-mmi-can-namespace.service
- systemd/system/open-mmi-can-private-provision.service
- systemd/system/open-mmi-can-private-quiesce.service
- tests/test_independent_can_trust.py
- tests/test_can_namespace.py

## Proposed new paths — these do not yet exist merely because listed

None specified. Add a file only when the bounded implementation needs it, and record it.

## Required implementation

- Replace the production LISTEN-ONLY requirement with versioned, independently implemented checks for the new topology. Preserve useful vcan challenge functionality as a separately named evidence dimension.
- Resolve the fixed namespace service and a stable namespace identity; inspect host and private namespace without creating or repairing interfaces. Recheck identity after collection to detect restarts.
- Verify physical canN is absent from the host namespace, present as a physical CAN controller privately, and connected to the intended vxcan peer and host openmmi-rx.
- Verify both live clsact/egress matchall DROP rules, the exact one-way gateway, controller mode and link state. Parse complete structures; do not accept route-name prefixes, extra routes or unrecognized filter actions.
- Missing privilege, tools, interface, namespace or required driver evidence yields UNVERIFIED. Contradictory, weakened or reverse-path evidence yields FAIL. Link down may be safely blocked but is not healthy live reception.
- Keep production inspection read-only. Any test transmission must be checker-owned on an explicitly isolated bench/vcan setup, never the owner's live vehicle.
- Document required host tools and exact commands after confirming their paths; do not reuse target Python helpers or silently enter arbitrary namespaces.

## Required behavioral and negative tests

- Fixtures cover correct topology, physical CAN visible on host, wrong namespace identity, wrong peer, missing/extra/reverse gateway, similar destination prefix and changed namespace during inspection.
- Reject permissive, missing, reordered/extra-action, wrong-chain and unsupported tc evidence; exercise real iproute2 output fixtures from the target before declaring parser coverage complete.
- Controller LISTEN-ONLY off with intact barriers is eligible; old listen-only-only evidence can never certify the new topology.
- A real disposable synthetic test verifies receipt and blocked reverse transmission independently; a unit fixture is not this test.
- Missing permissions/tools produce explicit UNVERIFIED without repair or mutation.

Test command groups: **T0 T_CAN T_TRUST T_FULL T_SYNTH**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P02-A01** — The live checker can describe and validate the intended new topology without requiring LISTEN-ONLY.
- [ ] **P02-A02** — No mutation or Open MMI CAN-transmit path is introduced.
- [ ] **P02-A03** — Negative fixtures and independently collected synthetic evidence pass.
- [ ] **P02-A04** — G1 records live target checks and reception after lifecycle transitions before the CAN boundary is closed.

## Explicit exclusions

- No new production CAN challenge ID or transmitting protocol.
- No restoration of listen-only as the enforcement architecture.
- No weakening of namespace or tc policy to make the checker pass.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
