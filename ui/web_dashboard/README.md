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

## Jellyfin media player

The Jellyfin backend lives in `ui/web_dashboard/jellyfin.py`. The main
`server.py` module owns HTTP routing only and delegates configuration, scoped
catalogue access, authentication, bounded responses, and media proxying to that
provider. The Jellyfin module does not import the dashboard handler, keeping the
provider boundary acyclic and independently testable.

The Media page can connect to Jellyfin using environment variables. Keep the API key server-side; do not put it in `app.js`, `index.html`, or any committed file.

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

This is intended to support keyboard media keys, desktop/system media controls, and steering-wheel integrations that emit normal media key events.

## Keeping secrets out of git

Never commit Jellyfin API keys. A local env file is fine if it is ignored:

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
- `static/preferences.js` owns safe JSON persistence and the dashboard settings key.
- `static/status.js` owns the shared status snapshot and fixed 200 ms `/api/status` polling lifecycle. It is DOM-independent, exposes subscriptions for later frontend modules, and keeps rendering callbacks in `app.js` during the migration.
- `static/app.js` owns DOM rendering and feature controllers.

The platform modules resolve `window.fetch` and `window.localStorage` at call time. This keeps performance instrumentation compatible and lets the dashboard fail safely when browser storage is unavailable or restricted.

## Development checks

Run these before committing dashboard changes:

```bash
python3 -m py_compile ui/web_dashboard/server.py ui/web_dashboard/bluetooth.py ui/web_dashboard/jellyfin.py ui/web_dashboard/radio.py ui/web_dashboard/usb.py
find ui/web_dashboard/static -maxdepth 1 -name '*.js' -print0 \
  | xargs -0 -n1 node --check
node --test tests/js/*.test.js
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
## Settings and local preferences

The Settings page is local to the dashboard/browser and is designed for display behaviour, not vehicle control.

Current Settings areas:

- Units: speed/distance display can be shown as mph/mi or km/h/km; temperature display can be shown as °C or °F.
- Display: normal, dim and boost modes are available for different cabin/tablet lighting conditions.
- Display: reduced animation can be enabled for older tablets or lower-distraction use.
- Display: tell-tale test lights the existing footer tell-tale icons through the normal frontend render path. It is frontend-only and does not write to `/api/status` or transmit anything to the car.
- Diagnostics: shows live decoded state and optional raw/debug detail for development.
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
