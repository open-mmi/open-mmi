# Media sources

Open MMI uses one shared Media page and player shell. Sources can be enabled and a
default chosen under **Settings → Media**. Source preferences are local to the
browser unless a provider requires server-side configuration.

Current sources are:

- Jellyfin;
- Internet Radio;
- USB;
- Bluetooth.

## Jellyfin

Jellyfin is an optional server-backed library and local browser audio source.
Configure it from:

```text
Settings → Media → Jellyfin setup
```

The form can test, save, clear, and restart the dashboard. Stored passwords and
tokens are never returned to the browser.

CLI equivalents:

```bash
open-mmi-config jellyfin status
open-mmi-config jellyfin setup
open-mmi-config jellyfin test
open-mmi-config jellyfin clear
open-mmi-config dashboard restart
```

Persistent values are stored in:

```text
~/.config/open-mmi/dashboard.env
```

The parent directory is mode `0700` and the file is mode `0600`.

### Authentication and scope

Assigned-user login is supported and preferred for a dedicated restricted user:

```text
OPEN_MMI_JELLYFIN_URL
OPEN_MMI_JELLYFIN_USERNAME
OPEN_MMI_JELLYFIN_PASSWORD
```

Token mode remains supported:

```text
OPEN_MMI_JELLYFIN_URL
OPEN_MMI_JELLYFIN_TOKEN
OPEN_MMI_JELLYFIN_USER_ID
OPEN_MMI_JELLYFIN_LIBRARY_ID
```

Token mode takes priority when a token is configured. A server API key is not a
user session, so user scope must be provided or resolved from an exact username.
Unscoped global access requires the explicit
`OPEN_MMI_JELLYFIN_ALLOW_GLOBAL=1` escape hatch and is not the default.

Use `OPEN_MMI_JELLYFIN_INSECURE_TLS=1` only for a trusted local server with a
self-signed or otherwise untrusted certificate.

Search results, streams, and artwork are checked against configured user/library
scope. Responses and proxied media types have bounded allowlists and size limits.
Assigned-user login tokens are short-lived and invalidated/retried once after an
upstream authentication failure.

### Playback and recovery

The dashboard browser plays proxied Jellyfin audio locally. During a provider
outage, the current page and last successful library remain visible while the
provider controller uses bounded recovery. Authentication and missing-
configuration failures do not create continuous retries.

Browser media-session handlers and keyboard fallbacks support play/pause, stop,
previous, and next. Steering-wheel bindings use canonical Open MMI actions and
can fall back through BlueZ, `playerctl`, or synthetic local media keys.

## Internet Radio

Internet Radio uses the community Radio Browser directory. Enable it under
**Settings → Media**, accept the privacy acknowledgement, and select it from the
Media source switcher.

Search and browse support popular, top-rated, recently active, country/language
filters, and browser-local favourites. Favourites and filters remain in local
storage and do not automatically sync between devices.

The browser sends station UUIDs to the local Open MMI server rather than opening
arbitrary catalogue URLs. The server resolves and validates each stream and
redirect, rejects loopback/private/link-local/multicast/reserved/unspecified
addresses by default, connects to the validated numeric address, and preserves
the original hostname for HTTP Host, TLS SNI, and certificate verification.

Optional server configuration:

```bash
export OPEN_MMI_RADIO_BROWSER_URL='https://all.api.radio-browser.info'
export OPEN_MMI_RADIO_USER_AGENT='Open-MMI/0.1 (+https://github.com/open-mmi/open-mmi)'
export OPEN_MMI_RADIO_CATALOG_TIMEOUT='6'
export OPEN_MMI_RADIO_STREAM_TIMEOUT='12'
```

A trusted deployment can explicitly permit private stream targets:

```bash
export OPEN_MMI_RADIO_ALLOW_PRIVATE_STREAMS=1
```

Do not enable that escape hatch on a dashboard exposed to untrusted users.

### Internet Radio privacy acknowledgement

Internet Radio is an optional external-network feature. The dashboard requires a
versioned explicit acknowledgement before the source can be enabled. A material
notice change invalidates the previous acknowledgement.

The notice explains that:

- Radio Browser requests can expose the dashboard server's **public IP address**,
  request times, **search text and country/language filters**, station IDs, the
  Open MMI User-Agent, and the **station-click notification** sent when playback
  begins;
- a station, stream host, CDN, redirect, or analytics provider may receive the
  public IP, timestamps, requested stream, ordinary headers, **connection
  duration and data transferred**, and may infer approximate location from IP;
- Open MMI **does not request GPS location** and does not send Jellyfin
  credentials, library contents, Radio favourites, or a unique Open MMI user ID
  to those services;
- acknowledgement, source preference, favourites, and filters remain in browser
  **local storage** and do not automatically sync.

The acknowledgement key is:

```text
openmmi.media.radio.privacy-consent.v1
```

This control provides transparency and informed choice. Open MMI does not control the privacy,
logging, sharing, or retention practices of Radio Browser mirrors, stations,
stream hosts, CDNs, redirects, or analytics providers.

## USB

USB is a read-only local media source. Open MMI does not mount, unmount, format,
rename, delete, or write to devices. It serves allowlisted audio and sidecar
artwork from readable roots through same-origin playback.

Conventional discovery checks one directory below:

```text
/run/media/$USER
/media/$USER
```

Explicit roots use the Linux path separator:

```bash
export OPEN_MMI_USB_MEDIA_ROOTS='/media/user/MUSIC:/srv/car-music'
```

Controls:

```bash
export OPEN_MMI_USB_AUTO_DISCOVER=0
export OPEN_MMI_USB_DISCOVERY_ROOTS='/run/media/user:/media/user'
export OPEN_MMI_USB_INCLUDE_HIDDEN=1
export OPEN_MMI_USB_READ_METADATA=1
```

`OPEN_MMI_USB_READ_METADATA=1` optionally uses `mutagen` when installed. Filename
and folder metadata remain available without it.

The browser supports folder navigation, recursive tokenised search, sorting,
playback, byte-range seeking, lazy duration discovery, and sidecar artwork named
`cover`, `folder`, `front`, or `album` with JPEG, PNG, or WebP extensions.

Security boundary:

- browser item IDs are opaque and resolved again for every request;
- absolute paths and traversal are rejected;
- symlink components are not followed;
- streaming and artwork use descriptor-relative no-follow opens;
- requests must remain within a currently allowed root;
- hidden entries are omitted unless explicitly enabled;
- no filesystem path is returned to the browser.

## Bluetooth

Bluetooth controls an already-connected remote player through BlueZ
`org.bluez.MediaPlayer1` on the system D-Bus. Open MMI does not pair devices,
request browser Bluetooth permission, change audio routing, or proxy remote audio
through the browser.

Requirements:

- Linux with BlueZ and `busctl`;
- a connected device exposing AVRCP media controls;
- dashboard access to the system D-Bus.

Enable Bluetooth under **Settings → Media**, connect the phone through the
operating system, and start playback. The page displays metadata provided by
BlueZ and exposes allowlisted play/pause, stop, previous, and next controls.

BlueZ does not expose arbitrary seek positioning or artwork through this API, so
progress is read-only and generic artwork is used.

Optional configuration:

```bash
export OPEN_MMI_BLUETOOTH_PLAYER='Pixel'
export OPEN_MMI_BLUETOOTH_DISABLE=1
export OPEN_MMI_BLUETOOTH_DBUS_TIMEOUT=2
```

The browser receives opaque player IDs, not raw BlueZ object paths or Bluetooth
addresses.

## API checks

Provider status can be inspected locally:

```bash
curl 'http://127.0.0.1:8765/api/jellyfin/status'
curl 'http://127.0.0.1:8765/api/radio/status'
curl 'http://127.0.0.1:8765/api/usb/status'
curl 'http://127.0.0.1:8765/api/bluetooth/status'
```

These are operator/development checks. Normal source enablement belongs in
Settings.
