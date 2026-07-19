# V1 update-management qualification

| Field | Value |
| --- | --- |
| Source branch | `v1-update-management` |
| Intended target | `main` |
| Implementation status | Complete for confirmed manual nightly updates |
| Merge status | Held on branch for continued device qualification |
| Recorded device baseline | `v1-foundation-alpha-78-ga2690db` |

This record separates implemented behaviour from the evidence still required
before merging. Qualify the exact SHA that will be merged; a later commit needs
its own final automated and installed-device pass.

## Locked scope

- The browser and CLI may check, prepare, and install a forward nightly
  candidate selected entirely from managed policy.
- Every preparation and installation is initiated manually and confirmed
  separately.
- Stable and beta release discovery remains read-only; installation is
  deliberately unauthorized.
- Scheduling, unattended updates, browser channel selection, arbitrary sources,
  downgrades, and caller-selected/manual rollback are not part of this branch.
- Failed installation health checks use only the transaction-owned automatic
  restoration path.

## Evidence already observed

- [x] Repeated browser-driven forward updates completed on the primary
  development device, including alpha-70 → alpha-73, alpha-74 → alpha-76,
  alpha-76 → alpha-77, and alpha-77 → alpha-78.
- [x] The alpha-78 transaction completed from
  `8caa45dc181517a345349d0712c7cacbb04752d7` to
  `a2690db3f54a0fccae45d4032a5db8cdfc3b7055`.
- [x] After alpha-78, the installed descriptor, source checkout, local branch,
  and tracked remote all reported the same commit.
- [x] Readiness reported no blockers and `install_allowed: true` after the
  alpha-78 update.
- [x] The coordinator, dashboard, and CAN daemon remained active after the
  update; `/api/version` reported matching build and frontend identities.
- [x] Failed API-health qualification exercised automatic restoration and
  reported `rollback verified` while retaining the previous installed build.
- [x] Source mismatch blocked preparation until the checkout again matched the
  installed commit.
- [x] Coordinator socket authorization was verified after refreshing the
  account's `open-mmi-update` group membership.
- [x] Artifact cleanup left no terminal staging transaction and retained only
  the two newest rollback archives after repeated updates.
- [x] Python, Node, Playwright, package, and live-dashboard CI gates have passed
  on the branch commits used for installed-device qualification.

## Final merge-candidate gates

### Automated

- [ ] GitHub CI is green on the exact candidate SHA.
- [ ] Python unit tests pass on every configured interpreter.
- [ ] Node and Playwright coverage pass, including the managed update controls.
- [ ] The wheel contains update modules and both privileged console entry
  points install correctly.
- [ ] CSS verification and the live dashboard probe pass.
- [ ] The candidate worktree is clean after testing.

```text
Update-management candidate SHA: ____________________
```

### Installation lifecycle

- [ ] Perform a fresh install into a clean login account.
- [ ] Log out and back in after the installer first adds the account to
  `open-mmi-update`; confirm browser readiness becomes `ready` without `sudo`.
- [ ] Upgrade from the current `main` checkpoint.
- [ ] Reinstall the same build.
- [ ] Confirm uninstall removes the coordinator, installer unit, policy file,
  command links, and managed runtime artifacts without deleting user config.
- [ ] Cold reboot after a completed update and confirm coordinator readiness,
  dashboard health, CAN daemon health, and matching build identity.

### Transaction and recovery

- [ ] Suspend and resume once with a prepared candidate; confirm persistent
  state still permits only that verified candidate.
- [ ] Repeat one controlled post-install health failure on the exact candidate
  and confirm automatic restoration, matching previous build identity, and
  active services.
- [ ] Confirm a second preparation/install request cannot overlap an active
  transaction.
- [ ] Recheck staging cleanup and the two-rollback retention bound.
- [ ] Confirm offline checking, insufficient disk, unsafe power, and thermal
  limits fail closed where they can be tested safely.

### User interface

- [ ] Check, prepare, and install from Settings without terminal assistance
  after initial account authorization is active.
- [ ] Confirm action feedback stays beside the update controls and is not
  duplicated.
- [ ] Confirm everyday fields remain clear and repository/readiness diagnostics
  remain available under **Technical details**.
- [ ] Confirm the changed-build frontend reload occurs once without deleting
  the Chromium profile or cache.

## Evidence commands

Run after the final installed update:

```bash
open-mmi-config updates coordinator
open-mmi-config updates status
open-mmi-config updates readiness

git status --branch --short
git rev-parse HEAD

systemctl --user is-active \
  open-mmi-dashboard.service \
  canbusd.service

curl --fail --show-error \
  http://127.0.0.1:8765/api/version
```

Record the output with the candidate SHA. Do not promote stable/beta execution
or unattended updating merely to complete this checklist; those are separate
security and release-engineering projects.
