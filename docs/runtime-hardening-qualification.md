# V1 runtime-hardening qualification

| Field | Value |
| --- | --- |
| Source branch | `v1-runtime-hardening` |
| Intended target | `main` |
| Implementation status | Complete on branch |
| Merge status | Pending final qualification |
| Next milestone | `v1-update-management` |

This checklist closes the runtime-hardening branch. Check each item against the
exact SHA that will be merged; do not qualify one commit and merge another.

## Evidence already observed

- [x] The desktop-shell checkpoint passed a cold-condition vehicle test before
  runtime hardening began.
- [x] A later installed frontend update refreshed itself without clearing the
  managed Chromium profile or pressing `Ctrl+Shift+R`.
- [x] CI passed after the frontend-versioning and stable-Diagnostics follow-up.
- [x] Thermal and power Diagnostics rendered successfully on more than one Linux
  hardware platform.
- [x] Automated Python, Node, Playwright and package-content coverage exists for
  the runtime-hardening slices.

These observations support the design, but they do not replace the final
current-HEAD checks below.

## Automated gates on the merge candidate

- [ ] GitHub CI is green for Python 3.9 and the current Python matrix.
- [ ] Node tests are green.
- [ ] Playwright tests are green.
- [ ] CSS and frontend-boundary checks are green.
- [ ] Wheel/package-content verification is green.
- [ ] Dashboard smoke/live probe is green.
- [ ] `git status --short` is empty after tests.
- [ ] Record the candidate SHA:

```text
Runtime-hardening candidate SHA: ____________________
```

## Installed update and version recovery

- [ ] Update an installed tablet while the managed Chromium window remains open.
- [ ] Confirm the page performs at most one automatic reload for the changed
  build.
- [ ] Confirm Settings → System shows matching dashboard and server versions.
- [ ] Confirm Diagnostics shows matching loaded frontend and dashboard server.
- [ ] Confirm no Chromium profile or cache directory was deleted.
- [ ] Confirm active form editing defers a changed-build reload and **Reload now**
  completes it.

## Same-build dashboard recovery

Run:

```bash
systemctl --user restart open-mmi-dashboard.service
```

- [ ] The current page and unsaved Settings input remain mounted.
- [ ] **Dashboard reconnecting…** appears and clears automatically.
- [ ] Chromium does not reload for the same build.
- [ ] Vehicle polling resumes once.
- [ ] Diagnostics recovery count increases once.
- [ ] Provider-owned disabled controls remain disabled after recovery.

## Jellyfin recovery

- [ ] Open Media and load a library.
- [ ] Restart or temporarily stop Jellyfin without restarting Open MMI.
- [ ] Existing Media content remains visible and is labelled reconnecting.
- [ ] Chromium does not reload.
- [ ] Retry rate remains bounded.
- [ ] Jellyfin returns to ready automatically and refreshes the active library.
- [ ] Missing configuration and rejected credentials do not create endless
  retries.
- [ ] Typed Jellyfin settings survive the outage.

## Touch-only interface recovery

On the target Linux Mint tablet:

- [ ] Open **Open MMI Interface Chooser**.
- [ ] Select Terminal UI and remember it.
- [ ] Confirm the live TUI opens, not an idle shell in `/opt/open-mmi`.
- [ ] Close the TUI using only window/touch controls.
- [ ] Confirm the chooser reopens.
- [ ] Select Web Dashboard and remember it.
- [ ] Confirm Chromium opens and the next normal Open MMI launch uses Web.
- [ ] Confirm cancelling recovery opens Web once rather than stranding the user.

## Diagnostics and efficiency

- [ ] Thermal/power Diagnostics displays available values and degrades missing
  sensors to `Unavailable`.
- [ ] Leaving Diagnostics stops `/api/system/diagnostics/runtime` polling.
- [ ] Hiding and restoring Chromium produces one immediate Diagnostics refresh,
  not duplicate timers.
- [ ] Diagnostics fields do not flash or rebuild during live updates.
- [ ] With stable vehicle data, unchanged render skips rise faster than full
  vehicle renders.
- [ ] Media layout counters stop rising after leaving Media.
- [ ] Status overlap skips remain normally zero.
- [ ] No material new idle CPU load is introduced by Diagnostics or recovery
  controllers.

## Vehicle qualification

Start from a cooled tablet and normal morning cabin conditions:

- [ ] Vehicle running and CAN active.
- [ ] Dashboard responsive for the full drive.
- [ ] CPU clocks move normally above the configured minimum.
- [ ] CPU/process use remains stable rather than increasing with uptime.
- [ ] Charging behaviour is normal for the installation temperature.
- [ ] Jellyfin credential focus and keyboard navigation remain correct.
- [ ] Suspend/resume does not create duplicate polling or permanent reconnecting
  state.

Hot-condition behaviour is a known installation constraint. Do not bypass
firmware protection or deliberately approach hot/critical trips merely to pass
this checklist. Confirm only that Diagnostics reports the condition honestly and
that cooling guidance is documented.

## Installation lifecycle

- [ ] Fresh install.
- [ ] Update from the merged desktop-shell checkpoint.
- [ ] Reinstall.
- [ ] Uninstall removes launcher, chooser, desktop entries and installed assets.
- [ ] Installed `/opt/open-mmi/.version` matches the candidate build.
- [ ] `/usr/local/bin` command links resolve into `/opt/open-mmi/venv/bin`.

## Documentation and merge

- [ ] Review [`runtime-hardening.md`](runtime-hardening.md).
- [ ] Review [`vehicle-tablet-installation.md`](vehicle-tablet-installation.md).
- [ ] Review known/deferred items in the branch design index.
- [ ] Update the design index with the final merge commit or release tag after
  merge.
- [ ] Create a rollback tag before merging.
- [ ] Merge the exact qualified SHA into `main`.
