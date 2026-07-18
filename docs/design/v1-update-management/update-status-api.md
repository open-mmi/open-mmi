# Read-only update status API

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | Read-only status plus trusted channel policy implemented |
| Owners | Dashboard backend, Settings → System |

## Endpoints

### `GET /api/system/update-status`

Returns local and cached information only. It does not contact the network.

The payload contains:

- API version and read-only marker;
- installed managed version and recorded commit;
- configured channel and policy state;
- source checkout health, branch, upstream label, cleanliness, local commit, and channel trust result;
- last process-local remote check result;
- readiness state and explicit blockers.

### `POST /api/system/update-check`

Performs one bounded remote check using the installed managed source descriptor and root-owned channel policy.

The request body may only be `{}` or `{ "confirm": true }`. It contains no source, branch, URL, command, path, timeout, or install option.

The endpoint:

- requires a loopback client and same-origin browser request;
- rejects overlapping checks;
- disables Git credential prompts;
- applies local and remote command timeouts;
- uses fixed `git ls-remote` branch or release-tag queries selected by policy;
- does not fetch, merge, reset, checkout, install, restart, or elevate privilege;
- returns safe errors without Git stderr, credentials, or remote URLs.

## Example shape

```json
{
  "api_version": 1,
  "read_only": true,
  "installed": {
    "managed": true,
    "version": "v1-runtime-hardening-42-gabc1234",
    "commit": "abc1234def56"
  },
  "channel": "nightly",
  "policy": {
    "state": "configured",
    "implicit": false,
    "updated_at": "2026-07-18T12:00:00+00:00"
  },
  "source": {
    "configured": true,
    "state": "ready",
    "clean": true,
    "branch": "v1-update-management",
    "expected_branch": "v1-update-management",
    "upstream": "origin/v1-update-management",
    "commit": "abc1234def56",
    "trusted": true
  },
  "update": {
    "state": "not-checked",
    "checked_at": null,
    "available_version": "",
    "available_commit": "",
    "remote_differs": null,
    "update_available": null,
    "error": ""
  },
  "readiness": {
    "state": "ready",
    "blockers": []
  }
}
```

## Cache semantics

The first slice retains the last result in dashboard-process memory. Restarting the dashboard resets `last checked` to `never`. Persistent update state belongs to the future coordinator and must not be introduced implicitly through browser storage.

## Error semantics

- no source descriptor: source not configured;
- malformed descriptor: source invalid;
- missing checkout or Git: repository unavailable;
- detached, wrong branch, channel/source mismatch, or untrusted release remote: check blocked;
- network/remote failure: check unavailable;
- nightly commit with unknown ancestry: remote differs;
- lower release candidate: downgrade blocked;
- a version tag that moved to another commit: release tag changed;
- malformed or untrusted root policy: check blocked.

No failure is converted to `up-to-date`.


## Channel-specific queries

- `nightly` queries only the recorded `refs/heads/<branch>`.
- `beta` queries only fixed `refs/tags/v*` candidates and filters approved alpha/beta/rc/final version forms.
- `stable` queries the same fixed tag namespace but accepts final `vMAJOR.MINOR.PATCH` tags only.

No request field can select a channel, repository, ref, or tag pattern.

## Candidate preparation

`POST /api/system/update-prepare` accepts exactly `{"confirm": true}` and
forwards a fixed prepare request to the local coordinator. It returns persistent
coordinator state but exposes no staging path or remote URL. This operation may
download and validate a candidate in root-owned staging; it does not install,
restart services, or modify the live checkout or installation.
