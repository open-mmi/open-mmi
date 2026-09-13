# Original-goal coverage and completion limits

This maps the original deep-dive sections to current foundations, planned cards and evidence gates. Historical implementation order is not a command to redo completed work.

| Original section/goal | Existing foundation or planned closure |
| --- | --- |
| 1. Authenticity, compliance, authorization, continuity | Fixed distinctions; P10, P17, P18, P25 |
| 2. Existing CAN/config/update/privacy foundations | Preserve current modules; P01–P09 refine demonstrated gaps |
| 3. Separate release declaration, accepted state and history | C6 existing; regression coverage in T_TRUST and P12–P16 |
| 4. Strict Trust Manifest | Existing manifest v1; preserve it; versioned successor contract P10 |
| 5. Precise expansion comparison | Existing comparator/gate; protected implementation delta P12 |
| 6. Enforcement strength belongs to boundary | Existing assurance comparison; P03, P09, P10–P12 |
| 7. Explicit networking and local frontend assets | Existing brokers/vendored assets; P08/P09 effective closure |
| 8. Telemetry guard before collection | Existing guard; preserve default deny and pre-sampling tests throughout |
| 9. Operational state is not telemetry | Operating brief, P04/P05 guidance, P08/P09 tests |
| 10. Purpose-limited persistence | Existing store; P09 effective confinement |
| 11. CAN receive-only authority | Existing 6b0de79 namespace fix; G0, P02/P03, G1 |
| 12. Network funnels | Existing media/update mediation; P08/P09 |
| 13. Old trusted updater assesses candidate as data | C6 existing; P13–P16 remove successor candidate deployment callback |
| 14. Small protected Trust Core | P10–P16; bounded old-code deployment/recovery |
| 15. Trust Core changes are protected | P10–P12, explicit activation P16 |
| 16. CI trust invariants | Existing checks plus per-card negative tests; P21/P23 |
| 17. Official provenance separate from SI compliance | P18, P22, G3 |
| 18. Read-only CAN-triggered inspection | P19; approved transport required, no Open MMI CAN reply |
| 19. Fresh challenge evidence | P02 synthetic support plus P19 product/independent binding |
| 20. No response means UNVERIFIED | P02/P03/P19; no inferred compliance |
| 21. Existing update chain versus wiped install | P16 migration limits, P17 checkpoints/witnesses, G3 recovery |
| 22. External checker verifies rather than defines owner authority | Existing standalone checker, P17/P18 |
| 23. Optional TPM/measured boot | Explicit optional extension; not required for baseline completion |
| 24. Supply-chain inputs/reproducibility | P20–P22; full reproducible OS image optional |
| 25. Implementation sequence | Evolved into this 25-card manifest; preserve completed milestones |
| 26. Rejected shortcuts | Operating brief and every card's exclusions |
| 27. Monotonic owner boundary and demonstrable compliance | All cards, adversarial P23, final P25/G5 |

## What "complete the goal" means here

A supported release can enforce the accepted policy/protected-code transition contract through its managed update path, provide understandable read-only owner status/setup, demonstrate its supported runtime boundaries, and allow independently anchored verification/recovery under documented host/owner assumptions.

It does not mean arbitrary program equivalence has been proven, a root-controlled hostile OS cannot lie, a nonce alone is attestation, any SI modification is automatically compliant, or historical beta approvals can be reconstructed without evidence.

If a required supported field challenge transport, identity route, owner-witness rule or protected dependency remains unresolved, keep that specific original-goal row incomplete. Do not quietly shrink the claim to fit the code. The maintainer may deliberately revise supported scope, with the decision and effect recorded.

## Scope and review economy

P01–P07 are the immediate C7 milestone. P08–P09 close separate enforcement evidence. P10–P16 strengthen future continuity beyond the completed C6 scope. P17–P19 complete independent/witness/challenge aspects. P20–P25 qualify supply-chain and release behavior.

Bounded implementation/test/document tasks are suitable for cheaper models when given one card and the current handoff. The maintainer should review concrete security decisions in P08, P10–P18 and P22; models must not fill missing authority rules with plausible guesses.

The 25 slots are a planning estimate. Preserve boundaries and evidence, not a forced commit count. Merge already-satisfied tasks with evidence or split a newly difficult implementation while retaining IDs and acceptance mapping.
