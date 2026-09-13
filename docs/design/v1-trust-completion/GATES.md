# Qualification gates — these are not code commits

The next maintainer action is G0. A gate records actual evidence; it does not require an artificial runtime change just to create a commit. All target mutations below require a deliberate maintainer qualification action, not merely possession of this plan.

| Gate | Subject | Required before |
| --- | --- | --- |
| G0 | Existing 6b0de79 target baseline | Claiming repaired baseline works on the tablet |
| G1 | P01–P06 feature subject | C7/CAN closure at P07 |
| G2 | P08–P16 confinement/protected-core subject, with compatible independent evidence | Stronger protected-continuity claim |
| G3 | P17–P19 external evidence subject | Independent continuity/compliance/challenge claims |
| G4 | Integrated release candidate and exact nightly subject | Beta promotion/release candidate readiness |
| G5 | Agreed beta soak and exact main/release subject | Final goal/release readiness |

G2 can be prepared after P16, but independent successor compatibility from P17/P18 must exist before tablet activation is represented as externally verifiable. Code dependencies permit implementing those later cards while a hardware boundary is awaiting evidence; do not create a circular demand that P17 code cannot be written until G2 is fully closed.

## G0 — qualify the existing CAN-isolation baseline

### G0a: read-only identity capture on TABLET, still on beta

~~~bash
cd ~/open-mmi
git status --short
git branch --show-current
git rev-parse HEAD
git diff --check
uname -a
systemd --version
ip -Version
tc -Version
~~~

If readable, inspect installed source identity separately:

~~~bash
cd ~/open-mmi
if test -r /opt/open-mmi/.update-source.json; then
    cat /opt/open-mmi/.update-source.json
fi
curl --fail --silent --show-error http://127.0.0.1:8765/api/version
~~~

A stopped service/absent file/API is an observation, not permission to install or change channel. Record checkout branch, installed_commit/installed_version and managed channel/source independently. Reported beta remains unchanged.

Record adapter model/driver, actual configured physical interface and bitrate from existing configuration. Do not publish real VIN or credentials.

### G0b: deliberate qualification migration

Before any install/reboot, the maintainer must choose the target or spare test medium, the exact source commit, backup/recovery route and whether moving beta is intended.

Use TABLET checkout ~/open-mmi and the reviewed existing administrator workflow in scripts/manage.sh. It supports install, update, deploy-local and uninstall; it does not expose a standalone reinstall command. The desktop reinstall action has its own existing route. Do not invent commands from labels.

At this baseline deploy-local is an explicit administrator deployment of a clean named checkout; inspect its current build-environment prerequisites before issuing the exact command. It is a new-baseline operational migration from legacy beta, not a trusted C6 update. The ordinary update command uses the trusted coordinator and must not be weakened to make beta qualify as continuous.

Only after the maintainer deliberately prepares the exact feature checkout and recovery plan may an agent provide a concrete TABLET invocation such as sudo ./scripts/manage.sh deploy-local with its verified prerequisites. Do not run it from an assistant workspace or DEV path and imply the tablet changed.

### G0c: read-only topology observation after the exact feature is installed

The following commands assume the maintainer's reported can0. If inspected active configuration differs, substitute only the actual verified physical interface.

~~~bash
cd ~/open-mmi
systemctl --no-pager --full status open-mmi-can-namespace.service open-mmi-can-private-provision.service open-mmi-can-private-quiesce.service open-mmi-vehicle-can-provision.service
systemctl --user --no-pager --full status canbusd.service
ip -details -json link show dev openmmi-rx
ip -details -json link show dev can0
sudo /sbin/tc -json qdisc show dev openmmi-rx clsact
sudo /sbin/tc -json filter show dev openmmi-rx egress
~~~

Oneshot provision/quiesce units can legitimately be inactive after successful completion. Inspect Result/ExecMainStatus and journal timestamps; do not demand every oneshot be continuously active.

Host can0 lookup is expected to show no such device once isolated. Distinguish that result from permission/tool errors.

Obtain and validate the fixed namespace service PID before using it. No command below creates or repairs a namespace:

~~~bash
can_anchor_pid=$(systemctl show --property=MainPID --value open-mmi-can-namespace.service)
case "$can_anchor_pid" in
    ''|*[!0-9]*) printf '%s\n' 'Invalid namespace PID; stop.' ;;
    *)
        if test "$can_anchor_pid" -gt 1; then
            sudo readlink "/proc/$can_anchor_pid/ns/net"
            sudo nsenter --target "$can_anchor_pid" --net /sbin/ip -details -statistics -json link show dev can0
            sudo nsenter --target "$can_anchor_pid" --net /sbin/ip -details -json link show dev openmmi-rxp
            sudo nsenter --target "$can_anchor_pid" --net /sbin/tc -json qdisc show dev can0 clsact
            sudo nsenter --target "$can_anchor_pid" --net /sbin/tc -json filter show dev can0 egress
            sudo nsenter --target "$can_anchor_pid" --net /usr/bin/cangw -L
            systemctl show --property=MainPID --value open-mmi-can-namespace.service
        else
            printf '%s\n' 'Namespace anchor is not running; stop.'
        fi
        ;;
esac
~~~

Record the namespace identity/PID before and after. A restart during collection makes the combined observation unverified. Exact independent parsing/identity binding is P02; these manual observations are not a substitute for completing that checker.

Required observations:

- Installed identity is the intended 6b0de79 runtime, with feature configuration and correct units.
- Host has openmmi-rx; physical can0 is hidden there and present privately.
- Actual canbusd loaded evidence uses receive_interface=openmmi-rx and physical_interface=can0; the owner-visible configured interface remains can0.
- Physical controller is ACK-capable, not relying on LISTEN-ONLY.
- Both egress DROP rules are present/effective; only physical -> openmmi-rxp gateway exists.
- Live decoded vehicle data updates; expected diversity and relevant 0x65F presence are evaluated against the reported vehicle/network.
- Dashboard data is fresh; service/adapter failure is surfaced.
- No host-originated CAN data frames observed escaping; inability to transmit additionally requires controlled independent negative testing on an isolated bench, not arbitrary live-vehicle injections.

Repeat applicable observation after deliberately authorized clean install/reinstall, cold reboot, adapter disconnect/reconnect and suspend/resume. Do not uninstall the live tablet without the maintainer's explicit preservation/recovery decision.

At 6b0de79 the old independent CAN checker is known incompatible. Record that gap as pending P02; do not restore listen-only or claim its old check passed. G0 establishes preliminary operational baseline; final CAN closure additionally requires P02/P03 and G1.

## G1 — installed C7 and repaired CAN boundary

Use the exact tested P01–P06 code subject on TABLET after deliberate deployment. Required:

1. Unprivileged dashboard receives the same scoped evidence as the privileged status coordinator without direct private-file access.
2. Missing socket/permissions/restart gives UNVERIFIED, then recovers with no stale PASS.
3. New/legacy baseline guidance follows actual CLI prerequisites; root+TTY confirmation remains required.
4. Accepted state, lineage, integrity and provenance can be established on the correct reviewed baseline; telemetry remains denied unless independently authorized.
5. Prepared equal/narrower and expansion guidance is correct; stale candidate acknowledgement cannot enable install.
6. P02 independent checker verifies actual namespace/barriers/gateway after cold boot, reconnect and suspend/resume.
7. Controlled isolated negative CAN transmission test demonstrates both barriers with independently observed outcomes; vehicle test demonstrates useful reception.
8. Install/reinstall/rollback preserves protected data and service lifecycle.
9. 800×480 UI, decoded state and update/recovery behaviors are non-stale.

G1 evidence must identify the subject installed commit and machine. This gate is needed for P07; baseline unit totals alone do not satisfy it.

## G2 — confinement and protected-core continuity

Use a disposable Linux host/VM before target deployment. Required:

- P08 identity path analysis and P09 effective network/persistence confinement.
- Unchanged manifest plus altered protected core/units/dependency causes an explicit old-side review.
- No candidate privileged hook executes before acceptance; successor deployment is old-code-owned.
- Every durability/crash/recovery matrix row is exercised, including restart with fresh process state.
- Explicit C6-to-successor enrollment preserves original anchors and marks earlier protected history unverified.
- Once activated, every managed update route blocks missing/corrupt successor state; no old-engine fallback.
- Independent successor verification is compatible before completing the externally verifiable claim.

On TABLET, only perform activation/reboot fault tests after the maintainer approves a concrete backup/recovery plan. A virtual fixture is not a vehicle qualification.

## G3 — independent recovery, compliance and challenge

Run from a separately trusted environment with separately retained checker/owner anchors. Required:

- Target package is absent from verifier imports and cannot execute.
- Retained checkpoint and external owner-witness evidence detect rewritten local history and unproven expansions.
- Wiped/restored target verification works from retained artifacts; missing anchors remain UNVERIFIED.
- Official provenance and reviewed SI compliance are distinct.
- Fresh challenge binds target/release/evidence; replay/no response/unsupported transport is not a pass.
- Any approved production challenge transport has separate controlled hardware evidence; synthetic-only support is labeled.

A signed target-controlled checker or a nonce on the target screen alone does not satisfy this gate.

## G4 — feature/merged-nightly and release-candidate qualification

- Exact subject CI, Python matrix, JS/browser/package/registry/synthetic/recovery tests pass.
- Signed metadata, artifact/dependency hashes, checker bundle and installed inventory agree.
- Feature evidence is mapped to the actual integrated nightly commit; refresh impacted tests and required nightly tablet checks.
- Requalify live CAN, UI, power/reconnect, update transitions, migration and rollback on the nightly target.
- Preserve the configured tablet channel until deliberate promotion/testing.
- No required unresolved identity/CAN/trust blocker remains.

## G5 — beta soak and final readiness

Follow repository branch policy exactly: nightly -> beta, agreed soak, tested beta -> main. The maintainer defines soak duration and authorizes promotions/publication.

Record exact code/artifact subjects, CI, target qualification, migration/recovery instructions, externally retained anchors and final claim coverage. Any new runtime change during soak invalidates its affected qualification; an evidence-only record does not automatically invalidate unchanged runtime tests.

A gate with blocked/not_run/unverified required evidence cannot be marked passed. Optional measured boot and full OS reproducibility are exclusions, not silently failed required gates.
