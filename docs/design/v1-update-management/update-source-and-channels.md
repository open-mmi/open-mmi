# Update source and channels

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Accepted; development-source descriptor implemented in first slice |
| Owners | Installer, update-status backend, future update coordinator |

## Problem

The installed runtime under `/opt/open-mmi` intentionally does not contain `.git`. A dashboard process running from that directory cannot safely infer the original checkout, branch, upstream, or commit. Searching the filesystem would be unreliable and accepting those values from the browser would create an arbitrary-command and arbitrary-source boundary.

## Managed source descriptor

Managed install and update operations write `/opt/open-mmi/.update-source.json` atomically. Version 1 contains:

```json
{
  "schema_version": 1,
  "channel": "development",
  "repository_path": "/home/user/src/open-mmi",
  "branch": "v1-update-management",
  "upstream": "origin/v1-update-management",
  "installed_commit": "40-character Git commit",
  "installed_version": "git-describe value"
}
```

The descriptor is written by the managed installer/update path. The browser can read the resulting status but cannot modify or override these values through HTTP.

The path is local installation metadata, not a network source. The UI does not need to display the full path or remote URL.

The current `/opt/open-mmi` tree is user-manageable, so this descriptor is sufficient for unprivileged read-only inspection only. A future privileged coordinator must use root-owned policy or independently validate an approved release/channel manifest rather than treating this file alone as authorization.

## Initial channel

The first slice supports one explicit channel value:

- `development` — a recorded local checkout tracking one recorded upstream branch.

This matches the repository-driven update process already used by `manage.sh update` without pretending that release channels exist before their policy is defined.

## Planned channels

Later policy may add:

- `stable` — approved release tags or signed release manifests;
- `beta` — approved prerelease tags or manifests;
- `development` — a named tracked branch.

Channel selection will be an administrative operation. The Web UI will never accept an arbitrary URL or free-form ref.

## Repository health

The read-only model distinguishes:

- ready;
- local changes;
- source commit differs from the installed commit;
- detached HEAD;
- different branch;
- repository unavailable;
- source descriptor missing or invalid.

A check may still report the tracked remote commit when local uncommitted changes exist, but future installation must remain blocked until readiness policy explicitly handles that state.

## Remote comparison

The initial checker uses `git ls-remote --refs` with the recorded remote name and branch. It does not fetch or change repository refs.

Comparison states:

- `up-to-date` — installed commit equals tracked remote commit;
- `update-available` — the remote commit already exists locally and Git proves the installed commit is its ancestor;
- `local-ahead` — Git proves the reverse ancestry;
- `diverged` — both objects exist but neither is an ancestor;
- `remote-different` — commits differ but direction cannot be proven without fetching;
- `unavailable` — remote could not be reached or returned an invalid response.

This prevents a local unpublished commit or remote rewrite from being mislabelled as a safe forward update.
