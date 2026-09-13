# Sources and authority

## Maintainer-supplied operating facts

The current chat supplies canonical machine paths, python3/venv conventions, branch/commit identities, validation counts, beta target status, C6/C7 milestone definitions, CAN A/B observations and command/signing discipline. These are preserved in OPERATING_BRIEF.md and CURRENT_STATE.md.

The two historical attachments are preserved unchanged in source-notes/:

- original-trust-deep-dive.md
- historical-progress-snapshot.md

Their "done" labels and implementation descriptions are historical context. Current observed code and the maintainer's latest corrections control execution.

## Pinned source

Base: https://github.com/open-mmi/open-mmi/tree/6b0de79968a5cfb72773989db4c72989204e3cb6

Key paths:

- ui/web_dashboard/trust_status.py — dashboard currently calls Inspector directly.
- ui/trust_status_coordinator.py — existing fixed read-only privileged status protocol.
- ui/can_namespace.py — current ACK-capable physical namespace and dual DROP design.
- independent_checker/open_mmi_can_trust_test.py — old listen-only production test remains.
- independent_checker/open_mmi_trust_check.py — standalone verifier and static namespace contracts.
- open_mmi_trust/inspector.py — static/enforcement evidence and current reporting.
- open_mmi_trust/accepted_state.py and transition_gate.py — C6 policy comparison/acknowledgement.
- open_mmi_trust/release_integrity.py and release_provenance.py — current inventory and signer roots.
- ui/update_installer.py and scripts/manage.sh — trusted gate then existing deployment path.
- open_mmi_trust/vehicle_identity.py — existing bounded recognized-identity guard.
- docs/branch-workflow.md and docs/release-checklist.md — promotion/soak/release policy.
- .github/workflows/ci.yml, package.json, pyproject.toml — actual test/build interfaces.

Exact feature CI: https://github.com/open-mmi/open-mmi/actions/runs/34643874676

## Proposed files and commands

Every commit card distinguishes read_paths (existing at the pinned base) from proposed_paths (new implementation suggestions). Proposed paths must be reconciled with the actual current repository before implementation.

This plan intentionally contains no invented future commit SHA, signing fingerprint, Action SHA, tablet identity, safe production CAN ID or successful hardware result.

Installed administration commands must be checked against the actual installed version. A CLI documented in feature source may not exist on the legacy beta tablet.
