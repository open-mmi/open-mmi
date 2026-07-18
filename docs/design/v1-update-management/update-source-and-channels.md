# Update source and channels

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Implemented for read-only checks and administrative channel selection |
| Owners | Installer, update-status backend, `open-mmi-config`, future update coordinator |

## Problem

The installed runtime under `/opt/open-mmi` intentionally does not contain `.git`. A dashboard process running from that directory cannot safely infer the original checkout, branch, upstream, or commit. Searching the filesystem would be unreliable, and accepting those values from the browser would create an arbitrary-command and arbitrary-source boundary.

Channel choice is also different from source discovery. A writable installation descriptor is useful for read-only inspection but must not authorize a future privileged update. Channel selection therefore lives in a separate root-owned policy file containing only a fixed channel name.

## Managed source descriptor

Managed install and update operations write `/opt/open-mmi/.update-source.json` atomically. Version 1 contains:

```json
{
  "schema_version": 1,
  "channel": "nightly",
  "repository_path": "/home/user/src/open-mmi",
  "branch": "v1-update-management",
  "upstream": "origin/v1-update-management",
  "installed_commit": "40-character Git commit",
  "installed_version": "git-describe value"
}
```

The descriptor records what produced the installed tree. The browser can read derived status but cannot modify or override any descriptor value through HTTP. The path and remote URL are not displayed in Settings.

The descriptor's `channel` field is an installation-time copy for diagnostics and compatibility. It is not the authority for channel selection.

## Root-owned channel policy

The selected channel is stored in:

```text
/etc/open-mmi/update-policy.json
```

The fixed schema is:

```json
{
  "schema_version": 1,
  "channel": "nightly",
  "updated_at": "2026-07-18T12:00:00+00:00"
}
```

Only these keys and channel values are accepted:

- `stable`
- `beta`
- `nightly`

The policy contains no repository URL, path, remote, branch, tag pattern, commit, command, service, or environment setting. Production policy must be a root-owned regular file and must not be group- or world-writable. Symlinks, extra fields, unsupported schemas, and unsupported channels fail closed.

Writes use a randomly named temporary file, `fsync`, mode `0644`, atomic replacement, and a directory `fsync`.

## Migration from the first slice

Earlier slices recorded `channel: development`. That label is now the legacy spelling of `nightly`.

A missing policy file is interpreted temporarily as **implicit nightly** so existing installations retain their qualified read-only behaviour. A valid legacy `development` policy is read as `nightly`; the next managed install or update rewrites it atomically with the new label.

An invalid policy never falls back silently to nightly.

## Channel policy

### Nightly

Nightly follows the exact installer-recorded checkout, branch, remote name, and upstream branch.

Requirements:

- valid managed source descriptor;
- repository exists and is a Git worktree;
- current branch equals the recorded branch;
- current commit equals the installed commit for readiness;
- configured remote resolves to a non-empty URL;
- browser supplies none of these values.

The manual check uses the fixed recorded branch ref with `git ls-remote --refs`. It does not fetch. A commit difference is called **update available** only when local Git objects prove forward ancestry; otherwise it remains **remote differs**, **local source ahead**, or **source diverged**.

Nightly may intentionally use a contributor fork or local remote. It is not a release-trust channel and does not imply that builds are produced on a clock-based schedule.

### Beta

Beta is restricted to the official Open MMI repository and the `main` branch/upstream. It considers only version-shaped release tags:

```text
vMAJOR.MINOR.PATCH-alpha.N
vMAJOR.MINOR.PATCH-beta.N
vMAJOR.MINOR.PATCH-rc.N
vMAJOR.MINOR.PATCH
```

The highest semantic version is selected. Stable final tags are included so a beta installation can progress to the final release without changing channel.

Historical tags such as `v1.0.0-backend` and arbitrary tag names are ignored.

### Stable

Stable has the same official-repository and `main` requirements as beta, but accepts only final release tags:

```text
vMAJOR.MINOR.PATCH
```

Prerelease and historical checkpoint tags are ignored.

## Official repository identity

Stable and beta accept only these equivalent official forms:

```text
https://github.com/open-mmi/open-mmi
https://github.com/open-mmi/open-mmi.git
git@github.com:open-mmi/open-mmi.git
ssh://git@github.com/open-mmi/open-mmi.git
```

HTTP, `git://`, filesystem paths, forks, lookalike hosts, and other repository URLs are not trusted for release channels.

This identity is fixed in application code. It is not read from browser input or the policy file.

## Administrative CLI

Status and checks are available without a browser:

```bash
open-mmi-config updates status
open-mmi-config updates check
```

Channel selection is an administrative operation:

```bash
sudo open-mmi-config updates channel nightly
sudo open-mmi-config updates channel beta
sudo open-mmi-config updates channel stable
```

Selection is refused unless the managed source is clean, attached, on the recorded branch, and at the installed commit. Stable and beta additionally require recorded `main` tracking and the official repository.

There is no HTTP channel-change route and no Settings channel selector.

## Release comparison and downgrade boundary

For stable and beta:

- same candidate commit: `up-to-date`;
- higher semantic release: `update-available`;
- lower semantic release: `downgrade-blocked`;
- same version tag identifying a different commit: `release-rewritten`;
- installed version not safely comparable: `remote-different`.

The read-only checker never treats a lower release or rewritten tag as an installable update.

## Current security boundary

This slice establishes source and channel policy for read-only visibility. It does not yet prove release authenticity with signatures or authorize installation.

The future privileged coordinator must independently re-read root-owned policy, validate the official source or an approved signed manifest, enforce downgrade rules, and never treat the writable installation descriptor alone as authority.
