# Dashboard and Jellyfin service reconnection

| Field | Value |
| --- | --- |
| Branch | `v1-runtime-hardening` |
| Status | Implemented on branch — final current-HEAD device qualification pending |
| Owners | Frontend API client, Media/Jellyfin integration, dashboard service |

## Problem

The dashboard browser is a long-lived application. Local services may restart because of configuration changes, updates, suspend/resume, CAN-interface transitions, or ordinary faults.

Two recovery paths must remain separate:

- the Open MMI dashboard server may disappear and return;
- Jellyfin may disappear and return while the Open MMI server remains healthy.

A Jellyfin restart should not require refreshing Chromium. A dashboard-server restart should reconnect in place and reload only when frontend version reconciliation proves that the Open MMI build changed.

## Goals

- Represent service state explicitly instead of treating every failed request as a generic error.
- Recover Jellyfin browsing and status automatically after the server returns.
- Keep the current Open MMI page and configuration form mounted during provider outages.
- Recover promptly after resume or visibility restoration.
- Use bounded retry rates and avoid timer duplication.
- Avoid full-page reloads for optional-provider outages.

## Non-goals

- Hiding authentication or configuration errors behind infinite retries.
- Guaranteeing uninterrupted media playback across a Jellyfin restart.
- Restarting external Jellyfin infrastructure from Open MMI.
- Reloading Open MMI whenever any media request fails.

## Implementation status

The first implementation slice covers Jellyfin provider recovery:

- one page-owned status/retry controller;
- retry delays of 1, 2, 5, 10, then 15 seconds;
- paused retries while the Media page or document is inactive;
- explicit configuration, authentication, reconnecting, server-error, and ready states;
- last successful library content retained during outages;
- automatic active-library refresh after recovery;
- an explicit Retry control;
- no full-page reload for Jellyfin outages;
- Python, Node, and Playwright regression coverage.

The shared dashboard-server recovery slice is now implemented:

- the shared API client reports transport reachability without treating ordinary HTTP errors as disconnection;
- one dashboard connection controller owns `/api/health` recovery probes and 1, 2, 5, 10, then 15 second backoff;
- the 200 ms vehicle-status poller stops after transport loss and resumes once when the dashboard returns;
- retry timers pause while Chromium is hidden and visibility restoration performs one immediate probe;
- a non-blocking dashboard reconnecting banner preserves the current page and DOM;
- live server-backed controls are temporarily disabled without destroying forms or navigation;
- same-build recovery emits `openmmi:dashboardconnected` for in-place version reconciliation;
- changed-build recovery remains owned by the one-shot frontend-version reload controller;
- Settings → Diagnostics exposes dashboard connection state, probe count, and recovery count;
- Node, Python contract, and Playwright recovery coverage prevent duplicate retry owners and page reloads.

## State model

Each service client should expose a small explicit state machine.

### Dashboard server

```text
connecting -> ready -> reconnecting -> ready
                         |
                         -> unavailable
```

A recovered dashboard connection triggers a fresh `/api/version` comparison. Version reconciliation decides whether a reload is required.

### Jellyfin provider

```text
configuration-missing
connecting
ready
reconnecting
authentication-error
server-error
```

Meaning:

- `configuration-missing`: no usable Jellyfin configuration exists; do not retry continuously.
- `connecting`: first request is in progress.
- `ready`: status and browse requests are succeeding.
- `reconnecting`: a previously healthy service is temporarily unreachable.
- `authentication-error`: credentials or token were rejected; wait for configuration change or explicit retry.
- `server-error`: reachable service returned a persistent non-authentication failure.

## Retry policy

Use one owner per service for retry scheduling. Callers request refreshes through that owner rather than creating independent intervals.

Recommended local-service backoff:

```text
1 s, 2 s, 5 s, 10 s, then 15 s maximum
```

A small jitter may be used, but deterministic tests must be possible with an injected scheduler.

Reset backoff after a successful request. Authentication and missing-configuration states do not continuously retry. A user action, saved configuration, page visibility recovery, or explicit `Retry` action may restart attempts immediately.

## Visibility and suspend/resume

When the document becomes hidden:

- stop nonessential provider retries and browsing refreshes;
- preserve the current state and DOM;
- do not destroy forms or active navigation.

When it becomes visible:

1. make one immediate dashboard health/version request;
2. make one immediate request for the active media provider;
3. resume normal page-owned schedules only after those requests settle;
4. ensure old timers were cancelled rather than duplicated.

This is important for a vehicle tablet that may resume after sitting in a hot or suspended state.

## Jellyfin UI behaviour

During `reconnecting`:

- keep the Media page and its navigation mounted;
- retain the last successful library content where safe;
- visibly mark it as stale or reconnecting;
- disable actions that require a live server;
- keep Settings → Media credential fields intact;
- do not rebuild the configuration panel on each retry;
- provide an explicit retry action.

When the provider returns:

- refresh status and the currently visible library view;
- clear the reconnecting message;
- restore controls without navigating away;
- do not reload the Open MMI page.

For authentication failure:

- show a specific credentials/configuration message;
- stop high-frequency retries;
- keep secrets server-side;
- resume after credentials are changed or the user retries.

## Dashboard server recovery

The browser cannot complete API requests while the Open MMI server is restarting, but it can keep the existing DOM visible.

The frontend should:

- detect transport failures in the shared API client;
- show a non-blocking `Dashboard reconnecting` state;
- stop the high-frequency status poller while unavailable;
- retry `/api/health` through one bounded-backoff owner;
- notify feature clients when the shared connection returns;
- trigger version reconciliation before normal polling continues.

If the build is unchanged, normal status and provider refreshes resume without reload. If the build changed, the frontend-versioning design controls one safe reload.

## Request classification

The shared API layer should distinguish:

- network/unreachable errors;
- request timeout;
- HTTP authentication/authorization failure;
- HTTP client/configuration error;
- HTTP server error;
- valid response with provider state such as `configured: false`.

Features should not parse error-message strings to decide their state.

## Timer ownership

- Dashboard connectivity: one shared controller.
- Vehicle status polling: one shared status client.
- Jellyfin status/retry: one Jellyfin controller, active only when needed.
- Media layout: event-driven and page-owned; not part of reconnection polling.
- Configuration forms: no recurring reconstruction timer.

Every controller must provide an explicit stop/dispose operation for tests and page lifecycle changes.

## State preservation

Routine reconnection must preserve:

- active top-level page;
- selected Settings category;
- typed but unsaved Jellyfin values;
- current media source selection;
- current search text and filter where practical;
- browser-local dashboard preferences.

The last successful provider payload may remain visible, but the UI must label it stale while disconnected.

## User messages

Use specific, calm states:

```text
Dashboard reconnecting…
Jellyfin reconnecting…
Jellyfin credentials were rejected.
Jellyfin is not configured.
Jellyfin is available again.
```

Do not instruct the user to refresh the browser as the normal recovery path.

## Tests

### Node

- state-machine transitions for first connection, loss, recovery, auth failure, and missing configuration;
- exact retry/backoff scheduling;
- one retry owner with no duplicate timers;
- hidden-page suspension and visible-page immediate retry;
- typed configuration input remains mounted during retries;
- successful recovery refreshes the active view without reload;
- Jellyfin failure never invokes frontend version reload.

### Python/server

- Jellyfin status responses distinguish not configured, authentication failure, unreachable service, and success without exposing secrets;
- timeout and upstream error mapping remains stable;
- dashboard health and version endpoints remain available independently of Jellyfin state.

### Playwright

- load Media, stop the fake Jellyfin service, observe reconnecting state, restart it, and recover without page reload;
- keep Settings → Media input focused and preserve typed text across more than one retry interval;
- restart the Open MMI server with the same build and recover without reload;
- restart it with a different build and verify the separate one-reload version path;
- simulate suspend/visibility restoration and verify one immediate recovery request without duplicated polling.

## Acceptance criteria

- Restarting Jellyfin no longer requires a manual Chromium refresh.
- Provider outages do not navigate away from Media or rebuild credential forms.
- Same-build dashboard restarts recover in place.
- Changed-build dashboard restarts defer to the controlled frontend reload design.
- Retry work stops while hidden and resumes once without timer multiplication.

## Implementation outcome and deviations

The implementation kept dashboard and Jellyfin recovery separate as designed. Dashboard transport reachability is centralised in one controller, while Jellyfin owns provider-specific configuration and authentication states. The high-frequency status poller stops during a real transport outage and resumes after version reconciliation. Ordinary HTTP failures do not mark the whole dashboard offline.

The final merge candidate still requires the real-device same-build restart and Jellyfin restart checks in [`../../runtime-hardening-qualification.md`](../../runtime-hardening-qualification.md).
