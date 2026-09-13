# Test matrix and command discipline

Use DEV MACHINE ~/github/open-mmi unless a block explicitly says otherwise. All commands below inspect/test source or isolated fixtures; they do not authorize tablet installation or privileged host mutation.

Use .venv/bin/python3 when the repository venv exists. Never substitute python. If the venv is absent, an agent should inspect the current documented setup and propose a local-only environment setup. If setup is deliberately needed:

~~~bash
cd ~/github/open-mmi
python3 -m venv .venv
.venv/bin/python3 -m pip install -e .
~~~

Do this once as needed, not every handoff. Do not install globally or drop the evdev dependency to make imports pass. Build/browser extras belong in that local environment or CI. Record Python executable/version with results.

## T0 — every changed patch

~~~bash
cd ~/github/open-mmi
git status --short
git rev-parse HEAD
git diff --check
.venv/bin/python3 -m compileall -q open_mmi_trust open_mmi_telemetry ui canbusd independent_checker scripts tests tools
bash -n scripts/manage.sh
~~~

For the bootstrap documentation/helper patch alone, use the helper validator/unit tests in the download instructions; the already-qualified product suite is not invalidated.

A runtime patch must run its focused tests and required broader gates. Record source-tree identity before claiming results. No test failure is repaired by relaxing the security assertion without evidence that the expectation itself was wrong.

## T_UI — owner status and setup

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest tests.test_web_dashboard_trust_status tests.test_trust_status_coordinator
node --test tests/js/trust_status.test.js tests/js/system_settings.test.js tests/js/dashboard_connection.test.js
~~~

Add newly created setup-model/lifecycle tests explicitly after they exist. Verify actual module names rather than pasting future filenames into a command.

## T_SOCKET — real local protocol

Run the relevant socket round-trip tests on Linux where AF_UNIX sockets are available. P01/P06 must additionally prove installed root-private state -> privileged service -> unprivileged client in an isolated installation or G1.

Socket mocks verify message handling; they do not prove Unix permissions. A sandbox PermissionError is blocked environment evidence, not PASS and not a reason to make the service public.

## T_CAN — parser and provisioning regressions

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest tests.test_can_namespace tests.test_can_runtime tests.test_canbusd_core tests.test_profile_provision tests.test_vehicle_config_apply tests.test_independent_can_trust tests.test_trust_inspector
~~~

Cover missing/extra/reverse gateways, complete route parsing, wrong/missing tc rules, namespace identity changes, physical hidden state, mode evidence, fail-closed ordering and receipt endpoint metadata.

## T_TRUST — established C6 and Inspector invariants

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 tools/verify_trust_manifest.py
.venv/bin/python3 tools/vendor_bootstrap.py --check
.venv/bin/python3 -m unittest tests.test_trust_manifest tests.test_trust_invariants tests.test_telemetry_guard tests.test_accepted_trust_state tests.test_trust_transition_gate tests.test_trust_lineage tests.test_release_integrity tests.test_release_provenance tests.test_trust_inspector
~~~

GPG key generation/signature tests need functioning gpg/gpg-agent in the test environment. Do not skip provenance tests and claim provenance verified. CI can provide the valid run when an assistant sandbox cannot.

## T_UPDATE — actual managed update surfaces

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest tests.test_update_coordinator tests.test_update_installer tests.test_update_policy tests.test_update_readiness tests.test_update_status tests.test_trust_transition_gate
~~~

New protected-core/deployment/recovery modules add their specific tests. Instrument candidate execution, not just status strings. Cover stale/changed candidates, wrong signer, missing anchors, generation regression, mixed deltas, rejected authorization and crash recovery.

## T_LIFECYCLE — installed artifacts and management

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest tests.test_manage_script tests.test_command_installation tests.test_desktop_entry_installation tests.test_vehicle_config_coordinator tests.test_vehicle_config_apply tests.test_release_integrity tests.test_powerd_integration
~~~

Socket and systemd-tmpfiles-/proc requirements need a suitable Linux host. Classify unsupported assistant environments as blocked; do not assert target failures from them.

## T_IDENTITY and T_PERSIST

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest tests.test_vehicle_identity_remote_resolution tests.test_network_egress tests.test_telemetry_guard
.venv/bin/python3 -m unittest tests.test_persistence_enforcement tests.test_trust_inspector
~~~

P08/P09 additionally require effective isolation tests, with synthetic identity values and assertion that forbidden requests reach no remote call site.

## T_INDEPENDENT

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest tests.test_independent_trust_checker tests.test_independent_can_trust
~~~

Later independent bundle/checkpoint/metadata tests are added using the actual implemented module names. Test without the target Open MMI package and with target-controlled executable/import traps. A trusted external anchor must be supplied by the owner; never invent a signer fingerprint.

## T_FULL — full source suite after meaningful code changes

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 -m unittest discover -s tests
npm run test:frontend
.venv/bin/python3 tools/verify_css_split.py
~~~

Use full existing CI as the final automated gate for a runtime patch/phase. Do not repeatedly run the unchanged 6b0de79 baseline. After a new code change, the old full-suite count is historical and cannot certify the modified tree.

## T_BROWSER — real dashboard

~~~bash
cd ~/github/open-mmi
npm run test:browser
~~~

Use npm ci only when the locked browser environment needs installation or its lock changed. Install the Playwright browser through the project's normal dev/CI setup if absent; do not add a product dependency to accommodate a missing test browser. Use OPEN_MMI_PLAYWRIGHT_EXECUTABLE only for a verified existing supported executable.

The configured project is dashboard-800x480. Retain failure screenshots/traces and check normal navigation, overlays, Trust states, stale/recovered service, update guidance and existing media/vehicle features.

## T_PACKAGE — clean build/install

Use the current CI packaging job and tools/verify_wheel.py as the authoritative executable recipe. Inspect their current command-line interfaces before generating a per-card copy/paste block.

Build to a clean output directory from the reviewed source, verify wheel contents, install the specific wheel into a disposable venv and check imports/console entry points/assets. Do not accidentally test an editable source import instead of the installed package.

Cover both /opt/open-mmi source and active site-packages plus deployed privileged system/user units. New helper/schema/static files must be included where required. No use of sudo pip or global installation.

## T_SYSTEMD — syntax and effective unit policy

Run systemd-analyze verify on the exact changed unit set in a matching prepared installation/test root, with referenced executables available. On TABLET after a deliberate install, inspect the actual deployed /etc/systemd/system and /etc/systemd/user units and effective drop-ins.

Missing executables or unavailable /proc/systemd facilities are environmental blockers, not proof that a unit is valid or invalid. Do not suppress diagnostics to obtain a green result. Syntax verification and effective runtime sandbox behavior are separate evidence.

## T_SYNTH — isolated CAN fixture

Use a dedicated disposable Linux VM or bench interface owned by the test. Confirm the selected interfaces cannot be the live vehicle interface before allowing any test transmission. No arbitrary production CAN IDs.

The harness must observe actual one-way reception, host/physical egress denial, absence of reverse routes, filter counters and safe failure/recovery ordering. Negative TX tests are checker-owned; production Open MMI gains no send surface. Record driver/kernel/iproute2/can-utils and namespace identities. Reboot/hotplug effects require separate runs.

No generic privileged setup script is supplied by this plan because safe interface ownership is environment-specific. P02/P09/P23 agents must generate a concrete reviewed fixture and cleanup list before asking the maintainer to run privileged synthetic setup.

## T_ISOLATION — effective confinement

Use actual installed units in a disposable environment. Try forbidden external connections, undeclared file writes, identity reads and unauthorized Unix-socket operations from the corresponding process identities. Positive media/store behavior must still work. Test inherited descriptors and override/drop-in changes.

Do not run negative confinement probes against the user's entire desktop or live tablet configuration by default.

## T_RECOVERY — restart/power-loss state machine

Inject failures at every persistent transition in disposable fixtures, restart fresh processes and then qualify selected actual VM power-loss/reboot cases. Check bytes, signatures, accepted state, lineage, protected anchor, token consumption and visible blocked/recovery state.

A unit test that raises an exception in one process is not proof of durable recovery after reboot.

## T_SUPPLY — later release artifact gates

Once P20–P22 implement the named tools, verify lock hashes, offline builds/installation, SBOM completeness, signed metadata, platform compatibility, action pins and artifact substitution. The responsible agent must give exact commands using those actual tools. Until they exist, this group is a required outcome, not a fictitious command.

## T_DOC — handoff and reference integrity

~~~bash
cd ~/github/open-mmi
python3 docs/design/v1-trust-completion/helpers/check_handoff.py
python3 -m unittest discover -s docs/design/v1-trust-completion/helpers -p 'test_*.py'
git diff --check
~~~

Also check referenced current paths and generated-doc policy. For canonical registry changes, run the existing generators and conformance/replay checks:

~~~bash
cd ~/github/open-mmi
.venv/bin/python3 tools/generate_vehicle_action_docs.py --check
.venv/bin/python3 tools/generate_vehicle_event_docs.py --check
.venv/bin/python3 tools/generate_vehicle_status_docs.py --check
.venv/bin/python3 tools/generate_vehicle_catalogue_docs.py --check
.venv/bin/python3 -m ui.config_cli vehicle-setup conform --root .
.venv/bin/python3 -m ui.config_cli vehicle-setup qualification report --root .
.venv/bin/python3 -m ui.config_cli vehicle-setup replay --root . seat-leon-1p-pq35
~~~

## Testing economics

Run cheap targeted tests while iterating, then the required full/CI gates on the final patch subject. Reuse valid evidence rather than repeating it between chats. When a new failure appears, minimize/reproduce it, fix it in scope, and rerun the affected plus required final gates. Never count planned, blocked or skipped tests as observed success.
