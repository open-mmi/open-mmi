# P06 — test: qualify installed trust status and setup lifecycle

Generated from manifest.json. Update the canonical manifest and run helpers/render_manifest.py; do not silently change this generated card alone.

## Entry contract

- Phase: A — Complete C7
- Implementation prerequisites: P05
- Boundary closure gates: G1
- Required review: Maintainer review of preservation and recovery semantics
- Suggested signed commit subject: test: qualify installed trust status and setup lifecycle
- Starting branch context: owner-trust-controls-ui-v1; inspect current HEAD and prerequisite patches, never assume the original 6b0de79 is still the base.
- Read OPERATING_BRIEF.md, CURRENT_STATE.md, progress.json and HANDOFF_LATEST.md first. DEV is ~/github/open-mmi; TABLET is ~/open-mmi. Use python3/.venv/bin/python3.

## Boundary this commit establishes

Install, reinstall, service restart, update rollback and uninstall preserve the intended trust-status service, authority records, ownership and inventory coverage.

## Minimum current-source read set

- scripts/manage.sh
- systemd/system/open-mmi-trust-status.service
- open_mmi_trust/release_integrity.py
- tests/test_manage_script.py
- tests/test_command_installation.py
- tests/test_desktop_entry_installation.py
- tests/test_release_integrity.py
- tests/test_trust_status_coordinator.py
- tests/test_web_dashboard_trust_status.py

## Proposed new paths — these do not yet exist merely because listed

- tests/test_trust_setup_lifecycle.py

## Required implementation

- Extend behavior-based lifecycle fixtures around the installed wheel and service paths, including the root coordinator/unprivileged dashboard boundary.
- Verify unit install/restart/enable, preserved shared runtime directory, socket recreation and group membership behavior using real Linux integration where feasible.
- Ensure trust-status and CAN units are included in release inventory, backup and rollback. Keep unknown/missing units fail-closed.
- Treat trust-state preservation/deletion on uninstall as an explicit reviewed policy; never silently erase the owner's anchors to repair installation.
- Add a read-only health protocol checkpoint where installation currently checks only is-active, if needed to prove service readiness.
- Fix only defects exposed within this lifecycle surface and record their effect on previously qualified evidence.

## Required behavioral and negative tests

- Exercise socket occupied by symlink/non-socket/wrong owner, service crash during request, stale socket and status collection exception.
- Round-trip a valid installed fixture with root-private trust state and an unprivileged browser process.
- Reinstall and rollback restore unit bytes and preserve trust anchor files; fault during restoration is reported unverified.
- Cold start and reinstall do not require arbitrary privilege changes to the desktop account.
- No trust mutation or missing-anchor rebootstrap occurs during ordinary GET, install health checks or service startup.

Test command groups: **T0 T_LIFECYCLE T_SOCKET T_TRUST T_FULL T_PACKAGE T_SYSTEMD**. Use TEST_MATRIX.md. Add exact newly implemented module names after they exist. Record actual command/result/environment; planned tests or mocks cannot satisfy runtime/vehicle gates.

## Acceptance criteria

- [ ] **P06-A01** — Installed-path integration tests prove the intended authority boundary.
- [ ] **P06-A02** — Unit inventory/rollback checks cover all newly introduced services.
- [ ] **P06-A03** — Health failure is observable and cannot be reported as successful installation.
- [ ] **P06-A04** — Any target-dependent results are recorded at G1, separately from mocked tests.

## Explicit exclusions

- No unrelated manage.sh refactor.
- No bulk chmod/chown repair of unrelated user files.
- No destructive tablet uninstall without a separate maintainer-approved recovery plan.

## Patch and handoff exit

Deliver a downloadable patch for this card/revision, exact actual base and pre/post file hashes, patch SHA-256, required prerequisite patch IDs, and commands from PATCH_WORKFLOW.md using the real filename in ~/Downloads.

Update progress.json criteria with evidence IDs; retain failed/blocked evidence. Record code status separately from boundary status. A code patch may be prepared while hardware is pending, but closure requires the gates above.

Do not commit, push, merge, deploy, switch beta, reboot or mutate owner trust automatically. At a pause, record the last completed criterion, next smallest action, files touched, decisions, exact tree/patch state and tests not run in HANDOFF_LATEST.md. A later agent must be able to continue without this chat.
