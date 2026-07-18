# Frontend versioning and cache recovery

| Field | Value |
| --- | --- |
| Branch | `v1-runtime-hardening` |
| Status | Implemented on branch — installed automatic refresh qualified |
| Owners | Dashboard server, static frontend, installer/update lifecycle |

## Problem

The managed Chromium profile is intentionally persistent. That preserves settings and avoids first-run behaviour, but it also means stable asset URLs such as `/navigation.js` or `/media.js` can survive an Open MMI update in browser cache.

During desktop-shell qualification, the repository files, deployed files, and server-served files matched while the tablet still executed older frontend behaviour until its managed browser cache was cleared. A correct installation must not require profile deletion or manual cache maintenance.

A separate rough edge occurs when dashboard configuration restarts the local server: the browser remains open, but the user may need to refresh manually before new server or frontend state is visible.

## Current behaviour

- The dashboard serves a static `index.html` through `SimpleHTTPRequestHandler`.
- JavaScript and CSS use stable filenames.
- JSON API responses are marked `Cache-Control: no-store`.
- Static HTML, JavaScript, and CSS do not currently have a build identity shared between server and browser.
- The installer records a deployed source version in `/opt/open-mmi/.version`.

## Goals

- Every running frontend can identify the build that loaded it.
- The server exposes its current build identity through an uncached endpoint.
- Updated JavaScript and CSS receive a new URL identity.
- A browser connected across a server restart reloads once when the build changed.
- Temporary server downtime does not create a reload loop.
- Normal user preferences stored in browser storage survive the reload.
- The update path never requires clearing the managed browser profile.

## Non-goals

- Replacing the managed browser profile on every release.
- Disabling all browser caching globally.
- Reloading Open MMI merely because Jellyfin or another optional provider restarted.
- Treating the Python package version alone as a unique development-build identifier.

## Build identity

The dashboard server needs one authoritative runtime build identity. Resolution should be deterministic and work in both installed and development environments.

Recommended precedence:

1. an explicit `OPEN_MMI_BUILD_ID` environment value;
2. the deployed version file used by `manage.sh`;
3. repository `git describe --tags --always` when running from a checkout;
4. the Python package version with a clear development suffix as a final fallback.

The identity is opaque to frontend logic. It may be a release tag, a `git describe` value, or a short commit identifier. Frontend code compares exact strings and does not attempt semantic-version ordering.

## Server contract

Add an uncached endpoint:

```text
GET /api/version
```

Example response:

```json
{
  "build_id": "v1-foundation-alpha-41-g17845be",
  "frontend_id": "v1-foundation-alpha-41-g17845be",
  "api_version": 1
}
```

Requirements:

- `Cache-Control: no-store`;
- loopback and same-origin behaviour consistent with the existing dashboard API;
- no repository path or secret values;
- stable keys covered by contract tests.

`build_id` identifies the deployed server build. `frontend_id` allows a future split between backend and frontend packaging without changing the endpoint shape.

## Asset identity and cache policy

The server should return HTML that references JavaScript and CSS with the current frontend identity, for example:

```text
/navigation.js?v=<frontend_id>
/styles-shell.css?v=<frontend_id>
```

The exact injection mechanism is an implementation detail, but the generated HTML must contain one consistent identity for every mutable frontend asset.

Recommended cache policy:

| Resource | Policy |
| --- | --- |
| `/` and `/index.html` | `no-store` |
| `/api/version` | `no-store` |
| Other JSON control/status APIs | existing `no-store` policy |
| Versioned JavaScript and CSS | cacheable, immutable for that versioned URL |
| Unversioned JavaScript and CSS compatibility URLs | revalidate before reuse |
| Proxied media artwork and streams | retain provider-specific policy |

Query strings are acceptable because the local server resolves the path separately from the query. A content-hashed filename scheme may replace them later, but is not required for this branch.

## Loaded frontend identity

The HTML response should expose its `frontend_id` to the bootstrap code without another cached file being required. Suitable mechanisms include a generated meta element or a small inline assignment.

The value must be readable by Diagnostics and by the version-reconciliation controller.

## Version reconciliation

The browser should request `/api/version`:

- after initial bootstrap;
- after dashboard API connectivity recovers;
- when the document becomes visible after suspend or backgrounding;
- when the browser reports the network is online;
- periodically at a low frequency while visible, such as once per minute.

When the loaded frontend identity differs from the server `frontend_id`:

1. mark the UI as update-ready;
2. avoid reloading while a configuration form contains unsaved input or an editable control is active;
3. reload automatically when the page is safe to reload;
4. provide a visible `Reload now` action when reload is deferred;
5. attach the target build identity to the reload URL;
6. use `sessionStorage` to record the attempted target identity;
7. refuse to reload repeatedly for the same target identity within one page-recovery cycle.

After reload, the newly generated HTML and versioned asset URLs must load the target frontend identity. If they do not, Diagnostics should show the mismatch and the browser should stop automatic retries rather than loop.

## Dashboard-server restart behaviour

A server restart without a build change should reconnect in place and must not reload the page.

A server restart with a build change should:

1. recover API connectivity;
2. read `/api/version`;
3. perform the controlled reload path once;
4. show the new frontend and server identities in Diagnostics.

Jellyfin restarts are handled by the service-reconnection design and never trigger this version reload by themselves.

## State preservation

Persistent dashboard preferences already stored in browser storage should survive automatically.

Transient state should be treated deliberately:

- current page: restore after reload where practical;
- media search/filter: optional restoration;
- active playback: do not promise seamless continuation in this branch;
- unsaved credentials or settings: defer automatic reload and show an update-ready message;
- open modal/overlay: may close on reload unless it represents unsaved user input.

## Diagnostics

System Diagnostics should display:

```text
Loaded frontend: <frontend_id>
Dashboard server: <build_id>
Version state:    Current | Update ready | Mismatch after reload
```

This makes stale-client reports diagnosable without comparing file hashes over SSH.

## Failure handling

- `/api/version` unavailable: keep the current UI, report server reconnecting, and retry with backoff.
- malformed response: record a diagnostics error and do not reload.
- mismatch during unsaved input: defer and notify.
- mismatch persists after one reload: stop automatic reloads and show a clear manual recovery message.
- development fallback identity unavailable: use an explicit `unknown-dev` value and disable mismatch reload rather than looping.

## Tests

### Python/server

- build identity precedence;
- `/api/version` response shape and `no-store` header;
- `/` and `/index.html` cache policy;
- generated HTML contains one consistent version token;
- mutable asset URLs include that token;
- versioned and unversioned static paths resolve correctly;
- no secrets or local paths appear in the version response.

### Node

- equal identities do not reload;
- mismatch schedules one reload;
- repeated mismatch for the same target cannot loop;
- malformed or unavailable version responses do not reload;
- hidden documents do not poll continuously;
- visibility recovery requests a fresh version;
- unsaved editable forms defer reload;
- deferred reload can be accepted explicitly.

### Playwright

- serve build A, load dashboard, restart as build B, and verify one controlled reload;
- verify changed JavaScript is executed without clearing the browser profile;
- restart with the same build and verify no reload;
- simulate temporary downtime and verify recovery without a loop;
- preserve local preferences across the update reload;
- keep unsaved system-setting input until the user accepts reload.

## Implementation status

The first runtime-hardening implementation slice now provides:

- authoritative build identity resolution;
- uncached `/api/version`;
- no-store generated HTML with consistently versioned local JavaScript and CSS;
- immutable caching for matching versioned asset URLs and revalidation for compatibility URLs;
- startup, visibility, online, and dashboard-connectivity version checks;
- one-shot target-build reload protection through session storage;
- deferred reload with a visible action while editable or explicitly dirty controls are active;
- loaded/server identity and reconciliation state in Diagnostics;
- Python, Node, browser-contract, packaging, and Playwright regression coverage.

The first installed update that introduces this controller cannot be initiated by a frontend that was loaded before the controller existed. That one migration requires a normal or forced reload once; every later build is expected to reconcile automatically from the already-installed controller.

The initial tablet qualification confirmed that the new frontend loaded after that one-time migration. It also exposed a Diagnostics regression: the live panel was rebuilding its DOM on every 200 ms status publication. Diagnostics now keeps stable field nodes and changes text only when values change; a structural rebuild occurs only when the set of decoded paths changes.

A later installed update with the controller already active refreshed automatically, and the associated CI run passed. No managed-profile or cache deletion was required.

## Acceptance criteria

- A normal `manage.sh update` cannot leave Chromium executing the prior frontend indefinitely.
- No cache-directory deletion is part of the supported update procedure.
- Same-build server restarts recover without page reload.
- Changed-build server restarts cause no more than one automatic reload.
- Diagnostics exposes enough identity information to distinguish deployment and browser-cache problems.


## Settings placement

The user-facing dashboard version, server version, and update state are shown under **Settings → System**, matching the conventional location users expect for software and update information. Diagnostics retains the lower-level loaded/server comparison for troubleshooting.

The System panel uses a distinct ready marker from its loading placeholder so unrelated settings renders cannot leave the page stuck on “loading desktop shell status”.
