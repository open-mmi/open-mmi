# Required qualification check IDs

Generated from manifest.json. Read GATES.md for procedures and EVIDENCE_PROTOCOL.md for evidence rules.

These are required checks, not completed results. Update progress.json only after actual observation and review.

## G0 — Existing CAN-isolation operational baseline

Pinned subject: 6b0de79968a5cfb72773989db4c72989204e3cb6

- [ ] **G0-01** — Record checkout and installed runtime identity separately; deliberate beta-to-feature migration and recovery route are documented.
  Required machine: tablet; evidence level: installed-integration.
- [ ] **G0-02** — Physical CAN is private; receive peer, exact gateway and both egress barriers are observed with stable namespace identity.
  Required machine: tablet; evidence level: installed-integration.
- [ ] **G0-03** — ACK-capable live vehicle reception, relevant decoded data and a fresh dashboard are observed without Open MMI-originated data frames.
  Required machine: tablet; evidence level: vehicle-qualified.
- [ ] **G0-04** — Authorized clean install/reinstall, cold reboot, adapter reconnect and suspend/resume preserve the observed topology and useful reception.
  Required machine: tablet; evidence level: installed-integration, vehicle-qualified.
- [ ] **G0-05** — Baseline limitations explicitly retain the old independent CAN checker gap; no claim of trusted continuity from legacy beta.
  Required machine: dev, tablet; evidence level: source-reviewed.

## G1 — Installed C7 and independently checked CAN

- [ ] **G1-01** — Unprivileged installed dashboard obtains privileged coordinator evidence without private-state access; socket failure and recovery do not leave stale PASS.
  Required machine: tablet; evidence level: installed-integration.
- [ ] **G1-02** — Root+TTY setup prerequisites, expansion guidance, first baseline and legacy/corrupt-state handling are correct; browser mutation remains unavailable.
  Required machine: tablet, isolated_vm; evidence level: installed-integration.
- [ ] **G1-03** — Independent live checker observes namespace, peer, exact gateway and both barriers on the installed target after lifecycle transitions.
  Required machine: tablet; evidence level: installed-integration.
- [ ] **G1-04** — Independent isolated negative transmission tests establish the one-way path and both effective egress barriers.
  Required machine: dev, isolated_vm; evidence level: synthetic-CAN.
- [ ] **G1-05** — ACK-capable vehicle reception and the 800x480 dashboard stay useful and fresh after reboot/reconnect/suspend.
  Required machine: tablet; evidence level: vehicle-qualified.
- [ ] **G1-06** — Installed update/reinstall/recovery preserves protected data, units and the established C6 gates.
  Required machine: tablet, isolated_vm; evidence level: installed-integration.
- [ ] **G1-07** — Applicable final Python, JS/browser, packaging and systemd evidence is retained for the implemented feature subject.
  Required machine: dev, ci; evidence level: unit-tested, protocol-tested, systemd-verified.

## G2 — Effective confinement and stronger protected continuity

- [ ] **G2-01** — Supported identity resolution paths cannot disclose identity remotely; policy and enforcement evidence are separately identified.
  Required machine: dev, isolated_vm; evidence level: installed-integration.
- [ ] **G2-02** — Effective network and persistence confinement passes negative and necessary positive probes under actual process identities and deployed units.
  Required machine: isolated_vm; evidence level: installed-integration.
- [ ] **G2-03** — Protected-core expansion is stopped by old trusted code before candidate execution; deployed bytes match the approved declarative plan.
  Required machine: isolated_vm; evidence level: installed-integration.
- [ ] **G2-04** — Every required crash/recovery transition is tested with fresh process state; selected durability cases survive actual VM restart.
  Required machine: isolated_vm; evidence level: installed-integration.
- [ ] **G2-05** — Explicit successor enrollment preserves C6 anchors and blocks missing/corrupt successor state on every managed route without fallback.
  Required machine: isolated_vm; evidence level: installed-integration.
- [ ] **G2-06** — Separately trusted verifier understands successor evidence and does not imply an external consent witness where none exists.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G2-07** — Deliberately activated target preserves CAN, UI and trusted-update operation with a reviewed recovery route.
  Required machine: tablet; evidence level: installed-integration, vehicle-qualified.

## G3 — External continuity, compliance and challenge

- [ ] **G3-01** — Verifier runs without importing/executing target packages; its distribution and owner anchors are retained independently.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G3-02** — Retained checkpoints and independent owner-witness receipts expose rollback, rewriting and unproven expansion; missing intervals remain UNVERIFIED.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G3-03** — Wiped/restored target can be assessed using retained external artifacts; missing anchors cannot be silently bootstrapped.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G3-04** — Official provenance, accepted boundary, integrity and reviewed SI compliance remain separate dimensions with adversarial vectors.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G3-05** — Fresh approved challenge binds target/release/evidence and rejects replay, missing response and unsupported transport.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G3-06** — Any production challenge transport has controlled target hardware evidence; an explicitly reviewed synthetic-only disposition narrows the claim.
  Required machine: tablet, independent_host; evidence level: installed-integration, externally-verified.

## G4 — Feature, integrated nightly and release candidate

- [ ] **G4-01** — Exact release-candidate CI passes the required Python, JS/browser, registry, package and adversarial lifecycle matrix.
  Required machine: ci; evidence level: unit-tested, protocol-tested.
- [ ] **G4-02** — Locked build inputs, offline install, SBOM, signed metadata and exact artifact/dependency graph agree on every supported platform.
  Required machine: dev, ci; evidence level: installed-integration.
- [ ] **G4-03** — Standalone checker validates retained signatures and installed inventory using independently accepted anchors.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G4-04** — Exact integrated nightly has a recorded feature comparison, fresh nightly CI and scoped evidence reuse rationale.
  Required machine: ci; evidence level: unit-tested.
- [ ] **G4-05** — Nightly target requalification covers vehicle CAN, fresh UI, power/reconnect and effective runtime barriers.
  Required machine: tablet; evidence level: vehicle-qualified.
- [ ] **G4-06** — Nightly migration/update/equal-narrower/expansion/recovery paths retain trust and installed artifact identity.
  Required machine: tablet; evidence level: installed-integration.
- [ ] **G4-07** — No required unresolved identity, CAN, continuity or metadata blocker remains; beta promotion has a concrete reviewed dossier.
  Required machine: dev; evidence level: source-reviewed.

## G5 — Beta soak and release readiness

- [ ] **G5-01** — Maintainer-defined beta soak duration, exact subjects and observed results are recorded; affected changes invalidate impacted evidence.
  Required machine: tablet; evidence level: vehicle-qualified.
- [ ] **G5-02** — Exact release/main candidate CI and artifact identity match the qualified beta promotion.
  Required machine: ci; evidence level: unit-tested, installed-integration.
- [ ] **G5-03** — Final target qualification and migration/recovery instructions agree with the final installed runtime.
  Required machine: tablet; evidence level: installed-integration, vehicle-qualified.
- [ ] **G5-04** — External checker/checkpoint/owner anchors and release evidence are independently retained and verified.
  Required machine: independent_host; evidence level: externally-verified.
- [ ] **G5-05** — All goal claims map to reviewed evidence and explicit exclusions; maintainer records final readiness without unauthorized publishing.
  Required machine: dev; evidence level: source-reviewed.
