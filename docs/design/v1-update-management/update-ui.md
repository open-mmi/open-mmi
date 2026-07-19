# Update user interface

| Field | Value |
| --- | --- |
| Originating branch | `v1-update-management` (merged into `main`) |
| Status | Confirmed managed nightly execution implemented; channel selection remains CLI-only |
| Owners | Settings → System frontend |

## Location

Update management belongs in **Settings → System**, below frontend/server version and desktop-shell health.

## Fields

- Installed version
- Channel
- Available version
- Update status
- Last checked
- Update progress or last-update state
- Prepared or last-update version, when one exists

Repository health and installation readiness remain available under a closed
**Technical details** disclosure. Equivalent low-level blockers are collapsed
into one user-facing reason so internal readiness codes do not appear as
duplicate failures.

The panel includes three fixed actions:

- **Check for updates**
- **Prepare update**
- **Install update**

Opening Settings loads only local/cached status. The network check runs only after explicit user action.

Completed and failed coordinator records remain visible as transaction history.
The panel labels their state and target as **Last update** and
**Last update version** so an out-of-band administrative deployment is not
mistaken for a pending UI update.

## Wording rules

- `up to date` is shown only when the installed commit exactly equals the tracked remote commit;
- nightly shows `update available` only when ancestry is locally provable; stable/beta require a newer approved semantic release;
- `remote differs` is used when direction is unknown;
- `downgrade blocked` is shown when a release channel would move backwards;
- `release tag changed` is shown when an approved version tag identifies a different commit;
- offline, timeout, invalid source, dirty source, detached HEAD, and branch mismatch are distinct states;
- errors are visible but do not replace or destroy the rest of Settings.

## Interaction rules

- only one check or update transaction may run at a time;
- active controls are disabled and labelled with the current operation;
- preparation and installation require separate browser confirmations;
- preparation is enabled only for a reported forward candidate when readiness passes;
- source mismatch or local changes block the check and keep preparation disabled even if an earlier readiness snapshot was ready;
- installation is enabled only for persistent `prepared` state when the coordinator authorizes nightly execution;
- coordinator state is polled during the operation and survives dashboard restart;
- server-side values are HTML-escaped;
- no repository path or remote URL is displayed;
- no channel-change, caller-selected rollback, or scheduling control appears in Settings;
- the existing dashboard-connection controller may temporarily disable the action while the local server is offline;
- update-action feedback is rendered inside the Software updates section beside the controls that produced it;
- action feedback is rendered once below the update controls and matching raw status errors are suppressed;
- technical source and readiness diagnostics remain available without dominating the default view;
- existing launcher and Jellyfin settings remain independent.

## Administrative channel selection

Settings displays the selected channel but does not change it. Administrators use `sudo open-mmi-config updates channel stable|beta|nightly`. This keeps repository and channel policy outside the browser mutation surface.

## Managed branch changes

Settings follows only the branch recorded by the managed installation. A
manual `git switch` intentionally produces a branch mismatch and disables
browser update actions. To adopt a different development branch, an
administrator deploys that branch once with `sudo ./scripts/manage.sh update`;
future forward commits on that recorded nightly branch may then use the browser
flow. Returning to `main` requires the same one-time administrative deployment.

There is no browser branch selector. Listing branches from a live remote would
not by itself make them trusted; any future selector needs a separately
reviewed allowlist and source-authorization design.

## Execution ownership

The browser displays coordinator state; it does not own the transaction. A
dashboard disconnect during installation is expected because the installed
service restarts. The browser reconnects and reads root-owned persistent state
instead of inferring success from the HTTP request. Automatic rollback remains
installer-owned and there is no browser-selected rollback target.
