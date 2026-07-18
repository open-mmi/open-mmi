# Open MMI web dashboard

The web dashboard is a local, in-car UI for Open MMI status data. It is designed to be lightweight, readable on a tablet-sized display, and safe by default: the vehicle dashboard remains read-only and consumes the human-readable status snapshot rather than sending CAN control messages.

## Running the dashboard

From the repository root:

```bash
python3 ui/web_dashboard/server.py
```

By default the dashboard listens on `127.0.0.1:8765`.

Open:

```text
http://127.0.0.1:8765/
```

Useful flags:

```bash
python3 ui/web_dashboard/server.py --host 0.0.0.0 --port 8765
python3 ui/web_dashboard/server.py --demo
python3 ui/web_dashboard/server.py --demo --demo-scenario traffic
python3 ui/web_dashboard/server.py --demo --demo-scenario warnings
python3 ui/web_dashboard/server.py --demo --demo-scenario stale
```

If the port is already in use:

```bash
pkill -f "ui/web_dashboard/server.py" || true
python3 ui/web_dashboard/server.py
```

## Pages

The dashboard currently has four main pages:

### Drive

Primary driving view. Shows speed, digital RPM, live/stale state, odometer/range/temperature, and the footer tell-tale strip.

### Climate

Shows climate-related status where available from the snapshot.

### Vehicle

Shows body/vehicle status such as doors, locks, lighting state, and related values where available.

### Media

Optional Jellyfin music page. This is a local dashboard player, not just a remote Jellyfin session monitor. The browser on the dashboard device plays audio locally using a server-side stream proxy, so the Jellyfin API token is not exposed to the frontend.

## Demo mode

Demo mode generates changing synthetic values so the UI can be developed away from the car.

```bash
python3 ui/web_dashboard/server.py --demo --demo-scenario traffic
```

Common scenarios:

```bash
python3 ui/web_dashboard/server.py --demo --demo-scenario traffic
python3 ui/web_dashboard/server.py --demo --demo-scenario warnings
python3 ui/web_dashboard/server.py --demo --demo-scenario reverse
python3 ui/web_dashboard/server.py --demo --demo-scenario doors-open
python3 ui/web_dashboard/server.py --demo --demo-scenario stale
```

Inspect the status payload:

```bash
curl http://127.0.0.1:8765/api/status | python3 -m json.tool
```

For an operator-focused summary of cache recovery, service recovery, Diagnostics, and known limitations, see [`../../docs/runtime-hardening.md`](../../docs/runtime-hardening.md).

## Runtime efficiency and activity counters

The dashboard keeps the existing visible vehicle-status cadence, but avoids duplicate work:

- status requests do not overlap and pause while the document is hidden;
- unchanged vehicle values do not rerun the full DOM render path;
- Media layout fitting is event-driven and stops outside the active Media page;
- tell-tale maintenance and media-key installation do not use permanent background probe timers.

Settings → Diagnostics shows lightweight session counters for status fetches, overlap skips, vehicle renders, unchanged render skips, and Media layout activity. The counters are intended for comparison and troubleshooting; they do not change dashboard behaviour.

## Dashboard server recovery

The long-lived browser reconnects to the local Open MMI dashboard server without discarding the current page. A transport failure stops the high-frequency vehicle-status poller, shows a non-blocking reconnecting banner, and retries `/api/health` with bounded backoff. Server-backed controls are paused while unavailable, but navigation, existing readings, and unsaved form contents remain mounted.

When the server returns, the frontend compares build identities before normal polling resumes. The same build recovers in place; a changed build uses the controlled one-shot frontend reload path. Settings → Diagnostics reports the shared connection state, health-probe count, and recovery count.

## Tell-tale test mode

Tell-tales can be forced in the browser for visual testing. This is frontend-only; it does not modify the backend status snapshot or vehicle state.

Examples:

```text
http://127.0.0.1:8765/?force=left,park,lights
http://127.0.0.1:8765/?force=hazard,bulb,highbeam
http://127.0.0.1:8765/?force=sidelights,dipped,rearfog
http://127.0.0.1:8765/?force=all
```

Keyboard shortcuts while the dashboard is focused:

| Shortcut | Forced tell-tale |
| --- | --- |
| `Alt+1` | Left indicator |
| `Alt+2` | Right indicator |
| `Alt+3` | Hazards |
| `Alt+4` | Parking brake |
| `Alt+5` | Bulb fault |
| `Alt+6` | Side / position lights |
| `Alt+7` | Dipped beam |
| `Alt+8` | High beam |
| `Alt+9` | Rear fog |
| `Alt+0` | Coolant hot / voltage warning test state |
| `Alt+C` | Clear keyboard-forced states |


## Desktop and startup settings

**Settings → System** selects the remembered Web/TUI interface and whether Open MMI itself opens after graphical login. Enabling it creates `~/.config/autostart/open-mmi.desktop`; the launcher starts the dashboard service on demand before opening the selected interface.

Equivalent commands:

```bash
open-mmi-config launcher default web
open-mmi-config launcher autostart enable
open-mmi-config launcher autostart disable
```

Dashboard service enablement is an advanced CLI-only control:

```bash
open-mmi-config dashboard status
open-mmi-config dashboard start
open-mmi-config dashboard stop
open-mmi-config dashboard restart
open-mmi-config dashboard enable
open-mmi-config dashboard disable
```

## Jellyfin media player

The Jellyfin backend lives in `ui/web_dashboard/jellyfin.py`. The main
`server.py` module owns HTTP routing only and delegates configuration, scoped
catalogue access, authentication, bounded responses, and media proxying to that
provider. The Jellyfin module does not import the dashboard handler, keeping the
provider boundary acyclic and independently testable.

For an installed tablet, configure Jellyfin from **Settings → Media → Jellyfin setup**. The form can test the connection, save server-side credentials, clear them, and restart the dashboard. Stored passwords and tokens are never returned to the browser.

The equivalent CLI workflow is:

```bash
open-mmi-config jellyfin setup
open-mmi-config jellyfin test
open-mmi-config jellyfin status
open-mmi-config dashboard restart
```

Persistent configuration is stored in `~/.config/open-mmi/dashboard.env` with mode `0600`; its parent directory is mode `0700`. The systemd user service loads this file automatically. `open-mmi-config jellyfin clear` removes the persisted credentials.

Environment variables remain supported for checkout/development launches. Keep the API key server-side; do not put it in `app.js`, `index.html`, browser local storage, or any committed file.

```bash
export OPEN_MMI_JELLYFIN_URL='https://jellyfin.example.local:8096'
export OPEN_MMI_JELLYFIN_TOKEN='your-api-key'
python3 ui/web_dashboard/server.py
```

Assigned-user login is also supported. This keeps Jellyfin credentials server-side and avoids exposing them to the browser:

```bash
export OPEN_MMI_JELLYFIN_URL='https://your-jellyfin'
export OPEN_MMI_JELLYFIN_USERNAME='open-mmi'
export OPEN_MMI_JELLYFIN_PASSWORD='...'
```

Token mode still works and takes priority when `OPEN_MMI_JELLYFIN_TOKEN` is set. `OPEN_MMI_JELLYFIN_INSECURE_TLS=1` is only for self-signed or otherwise untrusted local TLS certificates.


For a self-signed or local HTTPS certificate:

```bash
export OPEN_MMI_JELLYFIN_INSECURE_TLS=1
```

Optional filters/configuration:

```bash
export OPEN_MMI_JELLYFIN_DEVICE='Dashboard'
export OPEN_MMI_JELLYFIN_SESSION_ID='session-id'
export OPEN_MMI_JELLYFIN_USER_ID='user-id'
```

One-shot launch example:

```bash
env   OPEN_MMI_JELLYFIN_URL='https://jellyfin.example.local:8096'   OPEN_MMI_JELLYFIN_TOKEN='your-api-key'   OPEN_MMI_JELLYFIN_INSECURE_TLS='1'   python3 ui/web_dashboard/server.py
```

Check server-side configuration without exposing the token:

```bash
curl http://127.0.0.1:8765/api/jellyfin/status | python3 -m json.tool
```

Search test:

```bash
curl 'http://127.0.0.1:8765/api/jellyfin/search?limit=5' | python3 -m json.tool
```

The Media page reconnects to Jellyfin without refreshing Chromium. During a provider outage it keeps the existing page and last successful library visible, marks the controls as reconnecting, and retries with bounded backoff. Authentication and missing-configuration states stop continuous retries until the user saves configuration or selects **Retry**. When Jellyfin returns, the active library view refreshes automatically.

<!-- open-mmi-items-4-6:start -->
### Security and library scope

Use a dedicated, non-administrator Jellyfin user with access only to the music
libraries that should be visible in the car. User scope is required by default:

```bash
export OPEN_MMI_JELLYFIN_USER_ID='user-id'
```

A server API key is not a user session, so token mode does not use `/Users/Me`.
Set `OPEN_MMI_JELLYFIN_USER_ID`, or set `OPEN_MMI_JELLYFIN_USERNAME` without a
password to resolve an exact username through the API key. To restrict the Media
page to one Jellyfin library, also set:

```bash
export OPEN_MMI_JELLYFIN_LIBRARY_ID='music-library-id'
```

Search results, audio streams, and artwork are checked against the configured
user/library scope. JSON responses are capped at 4 MiB, proxied artwork is capped
at 8 MiB, and only JPEG, PNG, WebP, GIF, and AVIF image media types are accepted.
Assigned-user login tokens are cached for at most 15 minutes, keyed to the server,
username, password, and device identity, and are invalidated and retried once after
an upstream 401 or 403 response. Legacy server API keys that genuinely need global
access must opt in explicitly:

```bash
export OPEN_MMI_JELLYFIN_ALLOW_GLOBAL=1
```

Global mode is intentionally not the default. Do not use it on a dashboard exposed
to an untrusted network.

Remote session status is also opt-in. Set an exact session ID or exact device/client
name; the dashboard no longer falls back to another user's active session:

```bash
export OPEN_MMI_JELLYFIN_SESSION_ID='session-id'
# or
export OPEN_MMI_JELLYFIN_DEVICE='Dashboard'
```

The dashboard binds to `127.0.0.1` by default. When binding to `0.0.0.0`, protect the
port with a host firewall or an authenticated reverse proxy.

The Media page exposes recently added, favourites, and A–Z through one compact dropdown.
Equivalent API checks are:

```bash
curl 'http://127.0.0.1:8765/api/jellyfin/search?filter=recent&limit=5'
curl 'http://127.0.0.1:8765/api/jellyfin/search?filter=favorites&limit=5'
curl 'http://127.0.0.1:8765/api/jellyfin/search?filter=az&limit=5'
```
<!-- open-mmi-items-4-6:end -->

### Media keys and steering-wheel controls

The Media page registers browser media-session handlers and keyboard fallbacks for:

- play / pause
- stop
- previous track
- next track

Steering-wheel transport bindings use the shared `actions.audio` path. It first controls an actively playing BlueZ AVRCP player directly, then tries `playerctl`, then a connected paused BlueZ player, and finally falls back to a synthetic media key. This keeps Bluetooth pause/play independent of browser focus while preserving local browser and desktop-player controls.

## Keeping secrets out of git

For installed systems, prefer `open-mmi-config jellyfin setup` or the dashboard UI. They write the ignored, user-private `~/.config/open-mmi/dashboard.env`; do not copy that file into the repository.

For checkout-only development, never commit Jellyfin API keys. A local shell env file is fine if it is ignored:

```bash
cat > .env.local <<'EOF'
export OPEN_MMI_JELLYFIN_URL='https://jellyfin.example.local:8096'
export OPEN_MMI_JELLYFIN_TOKEN='your-api-key'
export OPEN_MMI_JELLYFIN_INSECURE_TLS=1
EOF

echo ".env.local" >> .gitignore
```

Before committing or pushing:

```bash
git grep "OPEN_MMI_JELLYFIN_TOKEN"
git grep "first-few-characters-of-your-real-key" || true
grep -R "first-few-characters-of-your-real-key" . --exclude-dir=.git || true
```

The variable name `OPEN_MMI_JELLYFIN_TOKEN` may appear in code or docs. The actual token value must not appear.

## Tell-tale icon attribution

Tell-tale assets live under:

```text
ui/web_dashboard/static/icons/telltales/
```

Keep the attribution/licence notice in:

```text
ui/web_dashboard/static/icons/telltales/NOTICE.md
```

The dashboard currently uses instrument-cluster style tell-tales for indicators, hazard, parking brake, bulb failure, high beam, dipped beam, side/position lights, and rear fog. Some assets are vendored locally and embedded as data URLs in the frontend to avoid runtime loading failures on the car tablet.

Before adding or replacing icons, confirm the source licence and update `NOTICE.md` with the file name, source URL, author, and licence.

## Frontend module boundaries

The browser loads small platform modules before the main dashboard application:

- `static/api.js` owns same-origin JSON request behaviour.
- `static/dashboard-connection.js` owns shared dashboard reachability and bounded same-build recovery.
- `static/frontend-version.js` owns loaded/server build comparison, safe one-shot reloads, visibility-aware checking, and the update-ready notice.
- `static/system-settings.js` owns local System/Jellyfin configuration rendering and the read-only software-update panel.
- `static/runtime-diagnostics.js` owns the three-second, Diagnostics-only system-runtime polling lifecycle and conservative clock/thermal state derivation.
- `static/preferences.js` owns safe JSON persistence and the dashboard settings key.
- `static/clock.js` owns the persistent header clock, minute-boundary scheduling, and clock-specific Display preferences.
- `static/status.js` owns the shared status snapshot and fixed 200 ms `/api/status` polling lifecycle. It is DOM-independent and exposes subscriptions for later frontend modules.
- `static/navigation.js` owns quick-page state, Home/menu construction, pager controls, keyboard navigation, and page-change events.
- `static/overlays.js` owns door/reverse detection, dismissal lifecycle, and the two full-screen vehicle alerts.
- `static/vehicle.js` owns vehicle/climate field derivation, unit conversion, health, doors, tachometer state, coolant/voltage enhancements, and the first-stage tell-tale rendering path.
- `static/media.js` owns media-source preferences, source switching, the source bar, placeholders, and Media settings.
- `static/media-jellyfin.js` owns the shared local player shell, Jellyfin browsing/search, playback, viewport fitting, and media-session key integration.
- `static/media-radio.js` owns Internet Radio privacy consent, filter/favourite state, the Radio adapter, and source-aware player integration.
- `static/media-usb.js` owns USB browsing, folder navigation, duration discovery, and the USB adapter.
- `static/media-bluetooth.js` owns Bluetooth status polling, optimistic transport state, progress presentation, and BlueZ control requests.
- `static/app.js` owns the Settings shell, decoded vehicle-state diagnostics, advanced tell-tales, and the remaining cross-cutting dashboard enhancements.

The dashboard CSS keeps its six cascade-preserving legacy modules and loads the clock as a separate extension directly from `index.html`:

- `static/styles-core.css` contains the original shell, vehicle cards, RPM and early tell-tale rules.
- `static/styles-media-layout.css` contains the base Jellyfin/player layout and Media containment fixes.
- `static/styles-shell.css` contains tell-tales, Home, Settings, overlays and display-mode rules.
- `static/styles-media-sources.css` contains the source shell, Radio controls and privacy dialog.
- `static/styles-diagnostics.css` contains browser performance diagnostics.
- `static/styles-media-final.css` contains USB, Bluetooth, final media-control and vehicle-correction rules.
- `static/styles-clock.css` contains the shared header clock and responsive clock layout without changing the checksum-protected legacy CSS split.
- `static/styles-runtime-hardening.css` contains the controlled frontend-update notice without changing the checksum-protected legacy CSS split.

## Frontend build identity and cache recovery

The server resolves one build identity from `OPEN_MMI_BUILD_ID`, `/opt/open-mmi/.version`, a development checkout, or the installed package fallback. `GET /api/version` exposes that identity with `Cache-Control: no-store`.

`/` and `/index.html` are generated with the same identity in a meta element and in every local JavaScript and CSS URL. Matching versioned asset URLs are served as immutable; unversioned compatibility URLs must revalidate. The browser checks the endpoint after startup, connectivity recovery, visibility recovery, and at a low visible-page interval. A changed build triggers one controlled reload. Active editing defers the reload and presents a **Reload now** action, while session storage prevents repeated reloads for the same target build. Clearing the managed Chromium profile is not part of the supported update process.

The release that first introduces this controller needs one reload if an older pre-controller page is already open; that older page has no code capable of detecting the new build. This is a one-time migration condition. Subsequent updates must reload automatically without clearing the browser profile.

Diagnostics updates its existing value nodes in place. It does not rebuild the full Diagnostics panel for each 200 ms status publication; a structural rebuild is reserved for changes to the decoded-path set.

## Read-only software update visibility

Managed install and update operations record `/opt/open-mmi/.update-source.json` with the original source checkout, tracked branch/upstream, installed commit, installed version, and the channel active at install time. The installed runtime does not contain `.git`, so this explicit descriptor prevents unreliable filesystem discovery and prevents the browser from selecting an arbitrary update source.

The selected channel is separate root-owned policy in `/etc/open-mmi/update-policy.json`. Its fixed schema contains only `stable`, `beta`, or `development`; it contains no path, URL, branch, ref, tag pattern, or command. Existing first-slice installations without this file operate as implicit development until the next managed update creates it.

`GET /api/system/update-status` reads local installation, policy, repository health, and the last process-local check result. It performs no network operation. **Settings → System → Software updates** displays the installed version, selected channel, available version, state, last check, and repository health.

**Check for updates** calls same-origin `POST /api/system/update-check` with a fixed confirmation object. Development uses the recorded branch with bounded `git ls-remote`; beta and stable use only fixed semantic tag queries against the official Open MMI repository. The checker does not fetch, merge, reset, install, restart, or elevate privilege. Unknown ancestry, untrusted remotes, downgrades, and rewritten tags are reported conservatively. Network failure is never presented as up to date.

Settings has no channel editor. Administrators use:

```bash
open-mmi-config updates status
open-mmi-config updates check
sudo open-mmi-config updates channel development
sudo open-mmi-config updates channel beta
sudo open-mmi-config updates channel stable
```

Update management remains read-only. It has no install button, scheduler, privileged coordinator, readiness enforcement, or rollback action. Design records live in [`docs/design/v1-update-management/`](../../docs/design/v1-update-management/README.md).

`static/styles.css` remains as an import-only compatibility manifest. `tools/verify_css_split.py` locks the module order and verifies that their concatenated bytes remain identical to the pre-split stylesheet, preventing accidental cascade changes during this structural phase.

The platform modules resolve `window.fetch` and `window.localStorage` at call time. This keeps performance instrumentation compatible and lets the dashboard fail safely when browser storage is unavailable or restricted.

The extracted player exposes temporary compatibility accessors for the Radio, USB, and Bluetooth adapters while the remaining frontend cleanup is completed. The player state itself remains single-owned by `media-jellyfin.js`; adapters do not create duplicate queues or playback state.

Browser-level coverage lives in `tests/browser/` and runs in Chromium through Playwright. The suite executes the real HTML, CSS and JavaScript assets in browser order with deterministic same-origin API fixtures. It covers navigation and keyboard controls, live status rendering, door/reverse overlay lifecycles, settings, clock and media-source persistence, 800×480 vehicle-display containment, a narrow portrait layout, and uncaught page/console errors. Screenshots and traces are retained on CI failures.

## Development checks

Run these before committing dashboard changes:

```bash
python3 -m py_compile ui/update_policy.py ui/web_dashboard/server.py ui/web_dashboard/versioning.py ui/web_dashboard/runtime_diagnostics.py ui/web_dashboard/update_status.py ui/web_dashboard/bluetooth.py ui/web_dashboard/jellyfin.py ui/web_dashboard/radio.py ui/web_dashboard/usb.py
find ui/web_dashboard/static -maxdepth 1 -name '*.js' -print0 \
  | xargs -0 -n1 node --check
node --test tests/js/*.test.js
npm ci
npx playwright install chromium
npm run test:browser
python3 -m unittest discover -s tests
python3 ui/web_dashboard/server.py --demo --demo-scenario warnings
```

Then open:

```text
http://127.0.0.1:8765/?force=all
```

## Design constraints

- Keep vehicle/CAN integration read-only in the dashboard.
- Keep secrets in environment variables or local ignored files only.
- Prefer small, reversible UI passes.
- Keep Drive/Climate/Vehicle stable when working on Media.
- Keep footer tell-tales in fixed slots to avoid jumping or flicker.
- Keep pages inside the rounded dashboard shell on tablet-sized displays.

## Future maps page

Maps should follow the same constraints as the Jellyfin page:

- separate page/module;
- server-side provider configuration;
- no provider keys in frontend code;
- local/offline-first tiles and routing where practical;
- read-only vehicle integration;
- no impact on Drive/Climate/Vehicle layout.

Possible future environment shape:

```bash
OPEN_MMI_MAP_PROVIDER=osmscout
OPEN_MMI_MAP_TILE_URL='http://127.0.0.1:8553/tiles/{z}/{x}/{y}.png'
OPEN_MMI_MAP_ROUTING_URL='http://127.0.0.1:8553'
OPEN_MMI_GPS_SOURCE=gpsd
OPEN_MMI_GPSD_HOST=127.0.0.1
OPEN_MMI_GPSD_PORT=2947
```

<!-- OPENMMI_WEB_SETTINGS_DOCS_START -->
## Thermal and power diagnostics

**Settings → Diagnostics → Thermal and power** reads a local, read-only runtime endpoint and shows:

- current and configured CPU clock ranges;
- one-minute load context;
- the platform thermal zone nearest or beyond a reported active, passive, hot, or critical trip;
- AC connection, battery capacity, and charging state;
- session-only observed clock and temperature ranges;
- expandable per-core, thermal-zone, cooling-device, power-supply, and Intel `pstate` detail.

The dashboard does not change governors, turbo, thermal trips, charging policy, or fan state. Polling runs only while Diagnostics is selected and the page is visible. Low clocks at low load are treated as normal idle behaviour; a clock constraint requires repeated high-load samples, and temperature is named as the cause only when a thermal trip is active too. Reported battery-side power is not charger capacity.

## Settings and local preferences

The Settings page is local to the dashboard/browser and is designed for display behaviour, not vehicle control.

Current Settings areas:

- Units: speed/distance display can be shown as mph/mi or km/h/km; temperature display can be shown as °C or °F.
- Display: normal, dim and boost modes are available for different cabin/tablet lighting conditions.
- Display: reduced animation can be enabled for older tablets or lower-distraction use.
- Display: the shared local clock can be shown or hidden, switched between 24-hour and 12-hour time, and optionally display the date.
- Display: tell-tale test lights the existing footer tell-tale icons through the normal frontend render path. It is frontend-only and does not write to `/api/status` or transmit anything to the car.
- Diagnostics: shows thermal/power runtime state, live decoded vehicle state, and optional raw/debug detail for development.
- Media: documents the server-side Jellyfin integration path.
- Reverse assist: provides a placeholder overlay path for later PDC/camera work.

These preferences are stored in browser local storage under the dashboard settings key. They change presentation only; backend decoding and vehicle state remain unchanged.

## Read-only operation

The web dashboard is a read-only MMI surface. It polls local decoded state and renders it for the driver/passenger display. It should not be used as a path for CAN transmit, actuator control, coding, adaptation, or security access.

For live vehicle testing, use listen-only CAN wiring and removable harness/adaptor setups. Do not cut or permanently modify the vehicle loom for dashboard testing.
<!-- OPENMMI_WEB_SETTINGS_DOCS_END -->

<!-- open-mmi-internet-radio-start -->
## Internet Radio source

The Internet Radio backend lives in `ui/web_dashboard/radio.py`. The main
`server.py` module owns HTTP routing only and delegates catalogue access, stream
validation, pinned connections, redirects, and audio proxying to that provider.
The Radio module does not import the dashboard handler, keeping the provider
boundary acyclic and independently testable.

The existing Media source selector now supports **Internet Radio** through the
community Radio Browser directory. Enable it in **Settings → Media**, then select
**Internet Radio** on the Media page. Search is live and the browse menu offers
popular, top-rated, recently active, and browser-local favourite stations. Country
and language selectors appear beneath the browse control. On first use, the country
follows the browser locale when it contains a region; choosing **All countries**
overrides that default.

Use the star beside the playback controls to add or remove the current station. Radio
favourites and country/language preferences are stored in browser local storage and
do not sync between devices.

The dashboard sends only station UUIDs to its own server. The browser never receives
or opens arbitrary catalogue stream URLs directly. Before proxying a station, the
server resolves the stream host and rejects loopback, private, link-local, multicast,
reserved, and unspecified addresses. The outbound socket connects directly to the
validated numeric address while retaining the original hostname for the HTTP Host
header, TLS SNI, and certificate verification. Every redirect is resolved, validated,
and pinned independently before it is followed, closing the validation/connect DNS
rebinding gap.

Optional configuration:

```bash
export OPEN_MMI_RADIO_BROWSER_URL='https://all.api.radio-browser.info'
export OPEN_MMI_RADIO_USER_AGENT='Open-MMI/0.1 (+https://github.com/open-mmi/open-mmi)'
export OPEN_MMI_RADIO_CATALOG_TIMEOUT='6'
export OPEN_MMI_RADIO_STREAM_TIMEOUT='12'
```

Private-network station targets are blocked by default. A trusted deployment that
intentionally uses a private stream can opt in explicitly:

```bash
export OPEN_MMI_RADIO_ALLOW_PRIVATE_STREAMS=1
```

Do not enable that escape hatch on a dashboard exposed to untrusted users.

API checks:

```bash
curl 'http://127.0.0.1:8765/api/radio/status'
curl 'http://127.0.0.1:8765/api/radio/search?filter=popular&limit=5'
curl 'http://127.0.0.1:8765/api/radio/search?q=bbc&country=GB&language=english&limit=5'
curl 'http://127.0.0.1:8765/api/radio/options'
```
<!-- open-mmi-internet-radio-end -->

<!-- open-mmi-radio-privacy-consent-start -->
### Internet Radio privacy acknowledgement

Internet Radio is an optional external-network feature. The dashboard requires a
versioned, explicit acknowledgement before it can be enabled in **Settings →
Media**. A material change to the notice version invalidates the old acknowledgement
and disables Radio until the updated notice is accepted.

The in-dashboard notice explains, in plain language, that:

- Radio Browser directory requests can expose the dashboard server's public IP,
  request times, search text, selected country/language filters, station IDs, the
  Open MMI application User-Agent, and the station-click request made when playback
  starts.
- The selected station, its stream host, CDN, redirects, or analytics providers may
  receive the dashboard server's public IP, timestamps, requested stream, ordinary
  HTTP headers, connection duration, and transferred byte counts. They may infer an
  approximate location from the public IP and control their own retention/sharing.
- Open MMI does not send Jellyfin credentials, Jellyfin library contents, Radio
  favourites, GPS coordinates, or a unique Open MMI user identifier to those
  services. Browser locale may choose an initial country filter, and that filter is
  sent in directory searches.
- The acknowledgement, source preference, favourites, and country/language filters
  remain in browser local storage and do not automatically sync between devices.

The acknowledgement is stored under
`openmmi.media.radio.privacy-consent.v1` with the current notice version and an
acceptance timestamp. Users can review the notice at any time from the Radio row in
Settings and can choose **Disable Radio and forget acknowledgement**.

This acknowledgement is a transparency and informed-choice control; it is not a
claim that external providers retain no logs. Open MMI does not control the privacy,
retention, or sharing practices of Radio Browser mirrors, station operators, stream
hosts, CDNs, redirects, or analytics providers.
<!-- open-mmi-radio-privacy-consent-end -->

<!-- open-mmi-usb-media-start -->
## USB media

The USB backend lives in `ui/web_dashboard/usb.py`. The main `server.py` module
owns HTTP routing only and delegates root discovery, browsing, opaque identifiers,
descriptor-safe opening, range handling, and streaming to that provider. The USB
module does not import the dashboard handler, keeping the filesystem boundary
acyclic and independently testable.

USB Media is a read-only local source. The dashboard never mounts, unmounts,
formats, renames, deletes, or writes to a device. It only exposes supported audio
files from readable roots through same-origin browser playback.

The server automatically looks one directory below these conventional per-user
mount locations:

```text
/run/media/$USER
/media/$USER
```

You can provide one or more explicit roots with the Linux path separator (`:`):

```bash
export OPEN_MMI_USB_MEDIA_ROOTS='/media/pitto/MUSIC:/srv/car-music'
python3 ui/web_dashboard/server.py
```

Useful controls:

```bash
# Disable conventional mount discovery and use explicit roots only.
export OPEN_MMI_USB_AUTO_DISCOVER=0

# Override the directories whose immediate children are treated as discovered roots.
export OPEN_MMI_USB_DISCOVERY_ROOTS='/run/media/pitto:/media/pitto'

# Include dotfiles and dot-directories. Hidden entries are omitted by default.
export OPEN_MMI_USB_INCLUDE_HIDDEN=1

# Optional tag/duration extraction when the third-party mutagen package is installed.
# It is disabled by default; filename/folder metadata remains available without it.
export OPEN_MMI_USB_READ_METADATA=1
```

Enable **USB** from Settings → Media after the server reports a readable root.
The browser can navigate folders, search recursively from the current folder,
sort folders/files, play supported audio, seek with byte-range requests, and use
sidecar album art named `cover`, `folder`, `front`, or `album` with JPEG, PNG, or
WebP extensions.

Browse rows resolve missing durations lazily with the browser's metadata loader. Only two local metadata probes run concurrently, results are cached by opaque item ID, and playback metadata updates the matching row as a fallback. Enabling `OPEN_MMI_USB_READ_METADATA=1` remains optional and can populate tags and durations server-side when `mutagen` is installed.

USB search is tokenised and separator-insensitive: spaces, underscores, hyphens, and folder boundaries can all separate search terms. Every entered term must match the track name or its relative folder path. USB folder navigation is shown only while USB is the active Media source.

Security boundary:

- browser-visible item IDs are opaque and resolved afresh on every request;
- absolute paths and `..` traversal are rejected;
- symlink components are never followed;
- stream and artwork files are opened relative to directory descriptors with
  `O_NOFOLLOW`, so replacing a checked path with a symlink cannot escape the root;
- every browse, artwork, and stream request must remain within a currently allowed root;
- hidden entries are omitted unless explicitly enabled;
- only allowlisted audio and image extensions are served;
- no filesystem path is returned to the browser.

Quick checks:

```bash
curl 'http://127.0.0.1:8765/api/usb/status'
curl 'http://127.0.0.1:8765/api/usb/browse?filter=browse&limit=10'
```
<!-- open-mmi-usb-media-end -->

<!-- open-mmi-bluetooth-media-start -->
## Bluetooth media source

The Bluetooth backend lives in `ui/web_dashboard/bluetooth.py`. The main
`server.py` module owns only the HTTP status/control routes and delegates BlueZ
access, opaque player IDs, cached status, request validation, and allowlisted
controls to the provider.

Bluetooth Media controls an already-connected phone or remote player through
BlueZ's `org.bluez.MediaPlayer1` interface on the system D-Bus. The dashboard
does not pair devices, request browser Bluetooth permission, change PipeWire or
PulseAudio routes, or copy the remote audio stream into the browser. Audio keeps
playing through the operating system's configured Bluetooth input/profile.

Requirements:

- Linux with BlueZ and `busctl` available.
- A connected device exposing AVRCP media controls.
- The dashboard server must run with access to the system D-Bus.

Enable **Bluetooth** under **Settings → Media**, connect the phone using the
operating system, then start playback on the phone. The dashboard displays the
track title, artist, album, duration, position, device name, and remote player
name when BlueZ provides them. Play/pause, stop, previous, and next are sent back
to the selected BlueZ player.

BlueZ's remote `MediaPlayer1` API does not expose arbitrary seek positioning or
artwork, so the progress bar is read-only and generic artwork is used.

Optional configuration:

```bash
# Prefer a player whose device name, player name, or BlueZ object path contains
# this case-insensitive text when more than one remote player is connected.
export OPEN_MMI_BLUETOOTH_PLAYER='Pixel'

# Disable the source backend explicitly.
export OPEN_MMI_BLUETOOTH_DISABLE=1

# Override the D-Bus command timeout (0.25 to 8 seconds).
export OPEN_MMI_BLUETOOTH_DBUS_TIMEOUT=2
```

API checks:

```bash
curl 'http://127.0.0.1:8765/api/bluetooth/status'
```

Controls require a current opaque `player_id` from the status response and a
same-origin JSON POST. Raw BlueZ object paths and Bluetooth addresses are never
returned to the browser.
<!-- open-mmi-bluetooth-media-end -->
