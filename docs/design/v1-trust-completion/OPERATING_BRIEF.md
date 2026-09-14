# Open MMI — operating brief for every agent

Read this file before proposing changes. It preserves the maintainer's explicit operating rules. It is a router into repository truth, not a replacement for that truth.

## Mission and scope

Trust the boundary you reviewed, and require explicit acknowledgement before that boundary can be expanded.

Complete the remaining owner-facing and verification work on owner-trust-controls-ui-v1, then implement the separately scoped stronger-continuity and release milestones in the commit manifest. C6 is an established completed milestone. C7 is not complete. C7.4 prepared-expansion guidance already exists. Do not casually reopen C6 or relabel C7 complete.

This pack is a plan, not authorization to install, switch the tablet, mutate trust, commit, push, merge or publish. The maintainer supplies product/security decisions. Agents implement bounded changes and review evidence. GitHub/repository records are durable memory; CI and scripts perform repeatable checks.

The 25 cards are reviewable work boundaries, not a quota or 25 prewritten patches. Inspect the actual current state first. If a card is already satisfied, attach evidence and mark it complete/superseded rather than implementing it again. If a difficult card needs two patches, use P12a/P12b-style child IDs or revisions, preserve the parent criterion mapping, and explain the reason. Do not erase context by renumbering the plan.

## Machines and paths

| Role | Canonical checkout | Purpose |
| --- | --- | --- |
| DEV MACHINE | ~/github/open-mmi | Source, review, tests, signed commits, CI, isolated synthetic CAN |
| TABLET / OPEN-MMI MACHINE | ~/open-mmi | Deliberate installation, runtime and vehicle qualification |
| Installed application on TABLET | /opt/open-mmi | Active source/venv/runtime; this is not the editable checkout |
| Assistant tool workspace | Environment-provided workspace | Analysis and patch generation only; never pretend it is a user-machine path |
| Downloaded deliverables on DEV | ~/Downloads | Patches and handoff artifacts downloaded by the maintainer |

Never substitute ~/g/open-mmi or an assistant /mnt/data checkout for the DEV path. Label every hardware-sensitive command DEV MACHINE or TABLET. Do not imply that an operation on one system happened on the other.

Use python3, not python. Prefer .venv/bin/python3 for project tests. The earlier evdev import failure was a missing project dependency in the selected environment; the repo .venv resolved it. Do not change product code to accommodate that environment mistake.

Before modifying DEV source:

~~~bash
cd ~/github/open-mmi
git status --short
git branch --show-current
git rev-parse HEAD
git diff --check
~~~

Understand dirty/staged/untracked files, including prompt counts such as !18 ?6, before generating or applying a patch. Do not stash, reset, clean, change ownership or discard work automatically.

## Pinned starting state

- Feature branch: owner-trust-controls-ui-v1.
- Previous validated feature HEAD: 1706d76d426b914f2ff16c63125e3218cb7dd33a.
- CAN isolation HEAD: 6b0de79968a5cfb72773989db4c72989204e3cb6.
- Maintainer reports a good GPG signature, push and green CI for that HEAD.
- Maintainer reports 162 focused tests, 1072 full-suite tests with 1 skipped, and systemd-analyze verify passed.
- Preserve these results. Rerun only when later changes invalidate their scope or a required new gate is not already covered.
- TABLET is reported to remain on beta. Its current installed SHA was not supplied to this session. Keep beta until the maintainer deliberately moves it for qualification.
- G0 hardware qualification of 6b0de79 is the immediate next target action. Source work can be prepared independently, but no tablet transition or qualification result may be assumed.

Do not use a changed-file count as identity. The maintainer described the final CAN change as 24 files; comparison of the entire feature branch with nightly also includes earlier C7 work. Exact commits/diffs are authoritative.

## Fixed trust distinctions

| Concept | Authority/meaning |
| --- | --- |
| Candidate Trust Manifest | Declaration of requested policy; never authority to grant it |
| Accepted owner state | Owner-accepted capability ceiling |
| Transition lineage | Recorded local authority changes; not retroactive proof before genesis |
| Provenance | Which independently pinned signer authenticated the commit/artifact |
| Integrity | Whether verified installed/runtime bytes match the accepted artifact |
| Inspector | Read-only evidence; cannot authorize anything |
| External checker | Independent verification within stated anchors/assumptions |
| Browser | Read-only trust status and local-terminal guidance |
| Local root + TTY | Existing trust mutation surface with exact confirmation |

Equal/narrower transitions may proceed under the defined gate. Expansion must stop for explicit acknowledgement by already-trusted code. A signature does not grant permission. A fresh nonce does not prove a hostile operating system is truthful. A local hash chain does not prove externally witnessed owner consent by itself.

Never introduce generic browser POST trust acceptance, browser-selected candidate paths/refs/commands, automatic bootstrap over corrupt state, --yes confirmation or a reusable expansion token.

Legacy beta -> feature deployment is an operational migration/new baseline. It is not trusted continuity from beta. Preserve history_before_baseline=unverified. Later protected-core enrollment likewise starts a new explicitly bounded guarantee; it does not rewrite C6 history.

## CAN invariant and evidence

vehicle.can.transmit = prohibited / os-enforced means Open MMI must not originate CAN data frames. It does not prohibit the controller participating in link-layer ACK.

The maintained A/B observation was approximately:

| Mode | Frames in 10 seconds | Unique IDs | 0x65F | TX |
| --- | ---: | ---: | --- | --- |
| Listen-only ON | 7352 | 1 | Absent | Not used as proof here |
| Listen-only OFF | 2237 | 27 | Present | Remained zero |

Do not reopen listen-only as the default solution without new contrary evidence. TX remained zero is useful observation, but alone does not demonstrate inability to transmit.

The physical can0/controller is in a private systemd-owned network namespace and is ACK-capable. canbusd reads the host endpoint openmmi-rx. Its peer is openmmi-rxp in the private namespace. There is exactly one gateway from physical CAN toward the private peer; no reverse route. Both host receive endpoint and physical controller have egress DROP. Physical CAN must not remain host-visible.

Physical CAN stays DOWN while namespace, proxy, egress barriers and gateway are established and verified. Never delete-then-add enforcement on a live physical link.

Correct units:

- systemd/system/open-mmi-vehicle-can-provision.service — existing host orchestrator.
- systemd/system/open-mmi-can-namespace.service.
- systemd/system/open-mmi-can-private-provision.service.
- systemd/system/open-mmi-can-private-quiesce.service.

There is no open-mmi-can-host-provision.service.

canbusd now reports interface plus physical_interface and receive_interface. An old expectation was corrected; that was not an architecture failure.

Independent live CAN checker migration remains a specific review item. Static code/unit verification, synthetic network tests and real vehicle qualification are different evidence levels. Do not close CAN enforcement until applicable live checks and G1 pass.

Host-originated frame blocking tests belong on an isolated synthetic/bench setup. Never probe a live vehicle by injecting arbitrary frames.

## Persistent boundaries and release flow

Remote vehicle identity resolution remains its own closure item. Existing guards are useful but owner acknowledgement does not prove enforcement. New code must demonstrate actual supported identity/data flow.

Preserve profile-driven vehicle knowledge and canonical event/status/action registries. Generated documentation is generated; do not hand-edit it. Keep normal vehicle setup UI-first and mutation/recovery commands in their proper administrator context.

Required release progression is feature qualification -> authorized nightly integration -> exact nightly CI -> nightly tablet/vehicle qualification -> migration/integrity/provenance checks -> beta promotion/soak -> main/release readiness, following docs/branch-workflow.md and docs/release-checklist.md.

Git beta is not the managed updater beta channel. Do not infer one from the other. Record checkout branch, installed metadata and update policy separately.

## Patch and Git discipline

Provide a downloadable patch and a fresh handoff for each card. Include exact base commit, prerequisite patches, changed-file pre/post hashes, patch SHA-256, tests run, expected checkpoints and exact commands referencing ~/Downloads. PATCH_WORKFLOW.md is mandatory.

No sudo git. Agents may perform read-only Git inspection and produce/check patches. The maintainer signs commits with git commit -S only when they explicitly reach that step. Do not commit/push/open/merge a PR or publish on their behalf by default. Do not repeat a patch already represented by the actual working tree.

The agent must say exactly what is unverified. No invented filenames, commands, machine actions, test counts, signer keys, commit IDs or hardware outcomes.

## Rolling checkpoints are required

Follow [CHECKPOINTING.md](CHECKPOINTING.md). Save an initial recovery checkpoint before implementation, then update and publish it after coherent edit/test batches and before long operations or large context reads. Checkpoint as the next action after at most two edit/test cycles or roughly 15 minutes of active work. Do not rely on a final handoff turn or wait for a chat-limit warning.

Keep HANDOFF_LATEST.md, progress.json, evidence and all unfinished source changes recoverable outside a temporary assistant workspace. A checkpoint must distinguish generated, saved, downloaded, applied and committed work; it must not claim that an incomplete boundary passed. Checkpoints do not require or authorize Git commits/pushes.

After a cutoff, the next agent resumes from the latest saved bundle and reconciles actual DEV state. If no durable checkpoint exists, report what may be lost instead of inventing the missing work. Preserve the distinction between cumulative recovery patches and incremental patches for the user's current tree.

## Where to read next

| Work | Read first |
| --- | --- |
| Current task and resume | CURRENT_STATE.md, progress.json, HANDOFF_LATEST.md, chosen commit card, CHECKPOINTING.md |
| Trust semantics | docs/trust-architecture.md, SECURITY.md, open_mmi_trust/ modules |
| Owner UI | ui/web_dashboard/trust_status.py, ui/trust_status_coordinator.py, static Trust/System settings, UI tests |
| CAN enforcement | ui/can_namespace.py, provisioning/apply paths, exact systemd units, independent CAN checker |
| Vehicle/profile changes | docs/vehicle-integration-standard.md, catalogue, selected profile, fixtures/evidence, conformance/replay |
| Update/deployment | ui/update_installer.py, ui/update_coordinator.py, scripts/manage.sh, update-management design |
| Release | docs/branch-workflow.md, docs/release-checklist.md, CI |
| Evidence/commands | TEST_MATRIX.md, GATES.md, EVIDENCE_PROTOCOL.md, PATCH_WORKFLOW.md |

The single handoff sentence: preserve the established architecture, work from ~/github/open-mmi with python3, respect DEV-versus-TABLET boundaries, and never substitute an assumption for an established repo/runtime fact.
