# Commit index

| ID | Commit boundary | Phase | Depends on | Closure |
| --- | --- | --- | --- | --- |
| P01 | [fix: read dashboard trust evidence through the privileged coordinator](commits/P01-fix-read-dashboard-trust-evidence-through-the-privileged-coordinator.md) | A — Complete C7 | Baseline | G1 |
| P02 | [fix: independently verify the private CAN receive topology](commits/P02-fix-independently-verify-the-private-can-receive-topology.md) | A — Complete C7 | P01 | G1 |
| P03 | [fix: distinguish static trust contracts from live enforcement evidence](commits/P03-fix-distinguish-static-trust-contracts-from-live-enforcement-evidence.md) | A — Complete C7 | P02 | G1 |
| P04 | [feat: model owner trust setup as explicit read-only progression](commits/P04-feat-model-owner-trust-setup-as-explicit-read-only-progression.md) | A — Complete C7 | P03 | G1 |
| P05 | [feat: guide owners through trust setup without browser mutation](commits/P05-feat-guide-owners-through-trust-setup-without-browser-mutation.md) | A — Complete C7 | P04 | G1 |
| P06 | [test: qualify installed trust status and setup lifecycle](commits/P06-test-qualify-installed-trust-status-and-setup-lifecycle.md) | A — Complete C7 | P05 | G1 |
| P07 | [docs: record C7 completion evidence and operating limits](commits/P07-docs-record-c7-completion-evidence-and-operating-limits.md) | A — Complete C7 | P06 | G1 |
| P08 | [security: close the supported remote vehicle identity boundary](commits/P08-security-close-the-supported-remote-vehicle-identity-boundary.md) | B — Enforcement closure | P07 | G2 |
| P09 | [test: measure network and persistence confinement under adversarial inputs](commits/P09-test-measure-network-and-persistence-confinement-under-adversarial-inputs.md) | B — Enforcement closure | P08 | G2 |
| P10 | [docs: specify protected trust-core evolution and deployment contracts](commits/P10-docs-specify-protected-trust-core-evolution-and-deployment-contracts.md) | C — Strengthen future continuity | P09 | Review |
| P11 | [feat: establish an owner-accepted protected-core anchor](commits/P11-feat-establish-an-owner-accepted-protected-core-anchor.md) | C — Strengthen future continuity | P10 | G2 |
| P12 | [feat: gate protected-core deltas before candidate execution](commits/P12-feat-gate-protected-core-deltas-before-candidate-execution.md) | C — Strengthen future continuity | P11 | G2 |
| P13 | [feat: build declarative deployment plans with trusted code](commits/P13-feat-build-declarative-deployment-plans-with-trusted-code.md) | C — Strengthen future continuity | P12 | G2 |
| P14 | [feat: execute prepared deployments from the installed trusted engine](commits/P14-feat-execute-prepared-deployments-from-the-installed-trusted-engine.md) | C — Strengthen future continuity | P13 | G2 |
| P15 | [test: make trusted deployment recovery atomic and fail closed](commits/P15-test-make-trusted-deployment-recovery-atomic-and-fail-closed.md) | C — Strengthen future continuity | P14 | G2 |
| P16 | [feat: activate protected-core continuity with explicit migration](commits/P16-feat-activate-protected-core-continuity-with-explicit-migration.md) | C — Strengthen future continuity | P15 | G2 |
| P17 | [feat: export and verify externally retained owner continuity checkpoints](commits/P17-feat-export-and-verify-externally-retained-owner-continuity-checkpoints.md) | D — Independent evidence | P16 | G3 |
| P18 | [feat: package an independent verifier with explicit compliance profiles](commits/P18-feat-package-an-independent-verifier-with-explicit-compliance-profiles.md) | D — Independent evidence | P17 | G3 |
| P19 | [feat: bind visible trust inspection to a fresh external challenge](commits/P19-feat-bind-visible-trust-inspection-to-a-fresh-external-challenge.md) | D — Independent evidence | P18 | G3, G4 |
| P20 | [build: lock supported release dependencies and offline installation inputs](commits/P20-build-lock-supported-release-dependencies-and-offline-installation-inputs.md) | E — Supply-chain and release | P19 | G4 |
| P21 | [ci: pin build actions and emit verifiable supply-chain evidence](commits/P21-ci-pin-build-actions-and-emit-verifiable-supply-chain-evidence.md) | E — Supply-chain and release | P20 | G4 |
| P22 | [feat: verify signed release metadata against accepted trust anchors](commits/P22-feat-verify-signed-release-metadata-against-accepted-trust-anchors.md) | E — Supply-chain and release | P21 | G4 |
| P23 | [test: exercise the full trust lifecycle with adversarial release fixtures](commits/P23-test-exercise-the-full-trust-lifecycle-with-adversarial-release-fixtures.md) | F — Final qualification | P22 | G4 |
| P24 | [docs: prepare feature promotion with exact candidate evidence](commits/P24-docs-prepare-feature-promotion-with-exact-candidate-evidence.md) | F — Final qualification | P23 | G4 |
| P25 | [docs: close release trust boundaries with a portable qualification dossier](commits/P25-docs-close-release-trust-boundaries-with-a-portable-qualification-dossier.md) | F — Final qualification | P24 | G5 |

These are implementation dependencies; pending hardware gates block closure/promotion, not explicitly approved independent DEV preparation.
All source paths are relative to the actual repository checkout. Proposed paths are labeled in each card.
