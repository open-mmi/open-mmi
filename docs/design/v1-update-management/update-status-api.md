# Read-only update status API

| Field | Value |
| --- | --- |
| Branch | `v1-update-management` |
| Status | First slice implemented |
| Owners | Dashboard backend, Settings → System |

## Endpoints

### `GET /api/system/update-status`

Returns local and cached information only. It does not contact the network.

The payload contains:

- API version and read-only marker;
- installed managed version and recorded commit;
- configured channel;
- source checkout health, branch, upstream label, cleanliness, and local commit;
- last process-local remote check result;
- readiness state and explicit blockers.

### `POST /api/system/update-check`

Performs one bounded remote check using the installed managed source descriptor.

The request body may only be `{}` or `{ "confirm": true }`. It contains no source, branch, URL, command, path, timeout, or install option.

The endpoint:

- requires a loopback client and same-origin browser request;
- rejects overlapping checks;
- disables Git credential prompts;
- applies local and remote command timeouts;
- uses `git ls-remote --exit-code --refs`;
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
  "channel": "development",
  "source": {
    "configured": true,
    "state": "ready",
    "clean": true,
    "branch": "v1-update-management",
    "expected_branch": "v1-update-management",
    "upstream": "origin/v1-update-management",
    "commit": "abc1234def56"
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
- detached or wrong branch: check blocked;
- network/remote failure: check unavailable;
- different commit with unknown ancestry: remote differs.

No failure is converted to `up-to-date`.
