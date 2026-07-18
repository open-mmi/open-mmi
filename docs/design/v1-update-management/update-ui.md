# Update user interface

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Read-only panel implemented; channel selection remains CLI-only |
| Owners | Settings → System frontend |

## Location

Update management belongs in **Settings → System**, below frontend/server version and desktop-shell health.

## First-slice fields

- Installed version
- Channel
- Available version
- Update status
- Last checked
- Repository health

The panel includes one action:

- **Check for updates**

Opening Settings loads only local/cached status. The network check runs only after explicit user action.

## Wording rules

- `up to date` is shown only when the installed commit exactly equals the tracked remote commit;
- nightly shows `update available` only when ancestry is locally provable; stable/beta require a newer approved semantic release;
- `remote differs` is used when direction is unknown;
- `downgrade blocked` is shown when a release channel would move backwards;
- `release tag changed` is shown when an approved version tag identifies a different commit;
- offline, timeout, invalid source, dirty source, detached HEAD, and branch mismatch are distinct states;
- errors are visible but do not replace or destroy the rest of Settings.

## Interaction rules

- only one check may run at a time;
- the button is disabled and labelled **Checking…** while active;
- server-side values are HTML-escaped;
- no repository path or remote URL is displayed;
- no install, channel-change, rollback, or scheduling control appears in Settings;
- the existing dashboard-connection controller may temporarily disable the action while the local server is offline;
- existing launcher and Jellyfin settings remain independent.

## Administrative channel selection

Settings displays the selected channel but does not change it. Administrators use `sudo open-mmi-config updates channel stable|beta|nightly`. This keeps repository and channel policy outside the browser mutation surface.

## Future execution UI

Only after readiness and coordinator slices exist may the UI add:

- View changes
- Install update
- Update progress stages
- Retry or rollback guidance

The browser will display coordinator state; it will not own the update transaction.
