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

The Media page can connect to Jellyfin using environment variables. Keep the API key server-side; do not put it in `app.js`, `index.html`, or any committed file.

```bash
export OPEN_MMI_JELLYFIN_URL='https://jellyfin.example.local:8096'
export OPEN_MMI_JELLYFIN_TOKEN='your-api-key'
python3 ui/web_dashboard/server.py
```

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

## Development checks

Run these before committing dashboard changes:

```bash
python3 -m py_compile ui/web_dashboard/server.py
node --check ui/web_dashboard/static/app.js
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
